"""Reentrenar los modelos de la aplicación con datos hasta hoy, con el método del ajuste final del estudio.

Encadena, con las mismas reglas que el estudio (reports/experimentos/final/config.json):
1. descarga en vivo de FRED, Yahoo, OPEP (obligatoria) y BCE, guardada en data/raw/<instante>_reentreno/;
2. tabla diaria a las 09:00 con el calendario del Brent de FRED (sin ampliar: las etiquetas salen de FRED);
3. ventanas, particiones con frontera = hoy (etiqueta publicada antes de la frontera, purga y último 15 %
   para la parada temprana) y escaladores ajustados con las ventanas de aprendizaje, en
   data/processed/<versión>/;
4. los nueve ajustes de la arquitectura seleccionada (3 horizontes × 3 semillas) con `ajustar`;
5. exportación a ONNX en dist/reentrenos/<versión>/modelo/ (lista para scripts/publicar_hf.py) e
   informe de cordura: MAE en el tramo de parada temprana frente al ingenuo con futuros y previsión de
   hoy del modelo nuevo y del estudio, con y sin la cesta OPEP.

El modelo reentrenado no tiene test propio. El tramo de parada temprana se solapa con el test del
estudio y además decide la época: su MAE es una comprobación de cordura, no una evaluación.

Con --reproducir-estudio usa el paquete fijo y la frontera 02/01/2023: los datos preparados deben ser
idénticos a los del estudio y los modelos y sus predicciones de test, a los de reports/experimentos/final/.

    poetry run python -m src.oil_price_prediction.reentrenar --reproducir-estudio
    poetry run python -m src.oil_price_prediction.reentrenar
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile

import numpy as np
import pandas as pd
import torch

from scripts.export_onnx import a_onnx, escalador_publicable, evaluacion_test, intervalo
from scripts.prepare_daily_inputs import FRED, YAHOO, construir_tabla, fuentes_paquete
from scripts.prepare_scalers import DESTINOS_FINAL, escribir_escalado
from scripts.prepare_splits import particionar_final
from scripts.prepare_windows import HORIZONTES, ROOT, SNAPSHOT, preparar_indice
from src.oil_price_prediction.actualizar import ZONA, calendario, cargar_modelo, fuentes_en_vivo
from src.oil_price_prediction.actualizar import predecir as prever
from src.oil_price_prediction.train_final import CARPETA as FINAL
from src.oil_price_prediction.train_final import leer_configuracion
from src.oil_price_prediction.train_validation import Regresor, ajustar, cargar_datos, predecir, tasa_del_horizonte

FRONTERA_ESTUDIO = pd.Timestamp("2023-01-02")
DATOS_ESTUDIO = ROOT / "data/processed" / SNAPSHOT
ARCHIVOS_DATOS = ("entradas_diarias.csv", "ventanas_objetivos.csv", "particiones_final.csv")
ESCALADO = DESTINOS_FINAL["variaciones"]


def escribir_csv(tabla, destino, **opciones):
    with tempfile.NamedTemporaryFile(dir=destino.parent, delete=False) as archivo:
        temporal = Path(archivo.name)
    try:
        tabla.to_csv(temporal, **opciones)
        os.replace(temporal, destino)
    finally:
        temporal.unlink(missing_ok=True)


def fecha(valor):
    return None if pd.isna(valor) else pd.Timestamp(valor).date().isoformat()


def preparar_datos(fuentes, brent, frontera, carpeta, snapshot, fase):
    """Tabla diaria, ventanas, particiones y escaladores, leyendo cada paso del disco como los scripts del estudio."""
    carpeta.mkdir(parents=True, exist_ok=True)
    tabla = construir_tabla(fuentes, brent.index)
    escribir_csv(tabla, carpeta / "entradas_diarias.csv", index_label="fecha", date_format="%Y-%m-%d")
    diario = pd.read_csv(carpeta / "entradas_diarias.csv", usecols=["fecha"], parse_dates=["fecha"])
    indice = preparar_indice(brent, pd.DatetimeIndex(diario["fecha"]))
    escribir_csv(indice, carpeta / "ventanas_objetivos.csv", index=False, date_format="%Y-%m-%d")
    diario = pd.read_csv(carpeta / "entradas_diarias.csv", usecols=["fecha", "brent_disponible"],
                         index_col="fecha", parse_dates=["fecha"])
    ventanas = pd.read_csv(carpeta / "ventanas_objetivos.csv",
                           usecols=["horizonte", "fecha_origen", "etiqueta_disponible_desde"],
                           parse_dates=["fecha_origen", "etiqueta_disponible_desde"])
    particiones, resumen = particionar_final(ventanas, diario, frontera, exigir_test=fase == "final")
    escribir_csv(particiones, carpeta / "particiones_final.csv", index=False, date_format="%Y-%m-%d")
    print(resumen.to_string(index=False))
    diario = pd.read_csv(carpeta / "entradas_diarias.csv", index_col="fecha", parse_dates=["fecha"])
    particiones = pd.read_csv(carpeta / "particiones_final.csv", parse_dates=["fecha_origen"])
    escribir_escalado(diario, particiones, carpeta / ESCALADO, "variaciones", fase, (frontera.year,),
                      "test" if fase == "final" else None, snapshot)
    return resumen


def comparar_datos(carpeta):
    """Compara byte a byte los CSV y el contenido de cada miembro del ZIP con los datos del estudio."""
    diferencias = [n for n in ARCHIVOS_DATOS if (carpeta / n).read_bytes() != (DATOS_ESTUDIO / n).read_bytes()]
    # Los ZIP no son idénticos byte a byte (guardan la hora de escritura): se comparan sus miembros.
    with ZipFile(carpeta / ESCALADO) as nuevo, ZipFile(DATOS_ESTUDIO / ESCALADO) as estudio:
        miembros = sorted(nuevo.namelist())
        if miembros != sorted(estudio.namelist()):
            diferencias.append(f"{ESCALADO}: miembros distintos")
        else:
            diferencias += [f"{ESCALADO}:{m}" for m in miembros if nuevo.read(m) != estudio.read(m)]
    return diferencias


def entrenar(c, arquitectura, h, semilla, carpeta, snapshot, fase):
    """Un ajuste con los mismos pasos y el mismo orden de semillas que scripts/train_final.py."""
    unidades = c["unidades"][arquitectura][str(h)]
    tasa = tasa_del_horizonte(c["tasa_aprendizaje"], h)
    # `_corte` es el año de la frontera: la etiqueta del corte en las particiones y los escaladores.
    datos, fechas, test, escalador, bases = cargar_datos(c["_corte"], h, c["objetivo"], c["entradas"], c["base"],
                                                         fase=fase, carpeta=carpeta, snapshot=snapshot)
    bases_tramo = {k: torch.from_numpy(v).cuda() for k, v in bases.items()}
    torch.manual_seed(semilla)
    modelo = Regresor(arquitectura, len(escalador["orden_entradas"]), unidades).cuda()
    datos = {k: (x.cuda(), y.cuda()) for k, (x, y) in datos.items()}
    historial, mejor, segundos = ajustar(modelo, datos, dict(c, tasa_aprendizaje=tasa), c["objetivo"], bases_tramo)
    salidas = {k: predecir(modelo, x, c["tamano_lote"]).cpu().numpy() for k, (x, _) in datos.items()}
    objetivos = {k: y.cpu().numpy() for k, (_, y) in datos.items()}
    entradas = {k: x.cpu().numpy() for k, (x, _) in datos.items()}
    return dict(modelo=modelo.cpu(), historial=historial, mejor=mejor, segundos=segundos, fechas=fechas,
                test=test, escalador=escalador, bases=bases, salidas=salidas, objetivos=objetivos,
                entradas=entradas, unidades=unidades, tasa=tasa)


def reproducir(c, arquitectura, solo_datos):
    """Comprobación: con el paquete y la frontera del estudio, todo debe coincidir con el ajuste final."""
    carpeta = ROOT / "data/processed/reproduccion-estudio"
    if carpeta.exists():
        shutil.rmtree(carpeta)
    fuentes, fechas = fuentes_paquete()
    brent = fuentes["brent"].loc[fechas.min():fechas.max()]
    preparar_datos(fuentes, brent, FRONTERA_ESTUDIO, carpeta, SNAPSHOT, "final")
    informe = {"datos_distintos": comparar_datos(carpeta), "modelos": []}
    print("Datos preparados idénticos a los del estudio." if not informe["datos_distintos"]
          else f"Datos distintos: {informe['datos_distintos']}")
    if not solo_datos:
        for h in c["horizontes_fechas_brent"]:
            for semilla in c["semillas"]:
                r = entrenar(c, arquitectura, h, semilla, carpeta, SNAPSHOT, "final")
                patron = f"*_{arquitectura}_h{h:03d}_u{r['unidades']:03d}_semilla{semilla}"
                originales = list(FINAL.glob(patron))
                if len(originales) != 1:
                    raise ValueError(f"Se esperaba un ajuste final {patron}.")
                original = originales[0]
                pesos = torch.load(original / "modelo.pt", map_location="cpu")
                nuevos = r["modelo"].state_dict()
                pesos_iguales = all(torch.equal(pesos[k], nuevos[k]) for k in pesos) and pesos.keys() == nuevos.keys()
                previas = pd.read_csv(original / "predicciones_test.csv", parse_dates=["fecha_origen"])
                nuevas = r["salidas"]["test"] + r["bases"]["test"]
                # cargar_datos deja las fechas como texto (CSV sin parse_dates): se comparan como fechas.
                fechas_iguales = previas.fecha_origen.reset_index(drop=True).equals(
                    pd.to_datetime(r["fechas"]["test"].fecha_origen).reset_index(drop=True))
                # El CSV guarda el float32 en decimal: se compara tras volver a float32.
                identicas = fechas_iguales and np.array_equal(previas.prediccion_red.to_numpy(dtype="float32"), nuevas)
                diferencia = float(np.abs(previas.prediccion_red.to_numpy() - nuevas).max()) if fechas_iguales else None
                registro = json.loads((original / "registro.json").read_text(encoding="utf-8"))
                fila = dict(ajuste=original.name, horizonte=h, semilla=semilla, pesos_identicos=pesos_iguales,
                            predicciones_test_identicas=identicas, diferencia_maxima_usd=diferencia,
                            mejor_epoca=r["mejor"], mejor_epoca_estudio=registro["mejor_epoca"],
                            epocas=int(len(r["historial"])), epocas_estudio=registro["epocas"])
                informe["modelos"].append(fila)
                print(f"+{h} semilla {semilla}: pesos {'idénticos' if pesos_iguales else 'DISTINTOS'}; "
                      f"predicciones de test {'idénticas' if identicas else 'DISTINTAS'} "
                      f"(diferencia máxima {diferencia} USD); mejor época {r['mejor']} (estudio {registro['mejor_epoca']})")
    destino = ROOT / "dist/reentrenos/reproduccion-estudio"
    destino.mkdir(parents=True, exist_ok=True)
    informe["coincide"] = not informe["datos_distintos"] and all(
        m["pesos_identicos"] and m["predicciones_test_identicas"] for m in informe["modelos"])
    (destino / "informe_reproduccion.json").write_text(json.dumps(informe, indent=2, ensure_ascii=False), encoding="utf-8")
    print(destino / "informe_reproduccion.json")
    if not informe["coincide"]:
        print("La reproducción NO coincide con el estudio: revisar antes de reentrenar.")
        sys.exit(1)
    print("Reproducción completa: coincide con el estudio." if not solo_datos else "Datos comprobados (sin entrenar).")


def descargar(hoy, frontera):
    instante = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    carpeta = ROOT / "data/raw" / f"{instante}_reentreno"
    carpeta.mkdir(parents=True)
    fuentes, avisos = fuentes_en_vivo("2000-01-01", hoy.isoformat(), carpeta, opep_obligatoria=True)
    for nombre in ("brent", *FRED, "tipo_bce", "cesta_opep"):
        fuentes[nombre].to_csv(carpeta / f"{nombre}.csv", index_label="Date")
    for nombre in YAHOO:
        fuentes["yahoo"][nombre].to_csv(carpeta / f"yahoo_{nombre}.csv", index_label="Date")
    (carpeta / "manifest.json").write_text(json.dumps(dict(
        status="complete", creado_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"), inicio="2000-01-01",
        fin=hoy.isoformat(), frontera=frontera.date().isoformat(), avisos=avisos,
        nota="Descarga en vivo para el reentrenamiento; los proveedores pueden revisar datos."), indent=2,
        ensure_ascii=False), encoding="utf-8")
    return carpeta, fuentes, avisos


def resumen_tramo(filas):
    return dict(n=int(len(filas)), inicio=fecha(filas.fecha_origen.min()), fin=fecha(filas.fecha_origen.max()),
                ultimo_objetivo=fecha(filas.fecha_objetivo.max()))


def prevision_hoy(fuentes, origen, carpetas):
    """Previsión del origen con cada modelo, con todas las fuentes y sin la cesta OPEP (como en GitHub Actions)."""
    fechas = calendario(fuentes["brent"].loc["2000-01-01":].index, origen)
    sin_opep = dict(fuentes, cesta_opep=pd.Series(dtype=float, index=pd.DatetimeIndex([]), name="cesta_opep"))
    salida = {}
    for nombre, carpeta in carpetas.items():
        _, config = cargar_modelo(carpeta, None)
        precios = {}
        for variante, f in (("con_opep", fuentes), ("sin_opep", sin_opep)):
            _, r = prever(f, fechas, origen, Path(carpeta), config)
            precios[variante] = {str(p["horizonte"]): p["precio"] for p in r["previsiones"]}
            base = r["base"]["valor"]
        salida[nombre] = dict(version=config["version"], base=base, **precios,
                              diferencia_sin_opep={h: precios["sin_opep"][h] - precios["con_opep"][h]
                                                   for h in precios["con_opep"]})
    return salida


def git():
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    cambios = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, text=True)
    return commit, [linea[3:] for linea in cambios.splitlines()]


def reentrenar(c, arquitectura, a):
    hoy = datetime.now(ZONA).date()
    frontera = pd.Timestamp(a.frontera) if a.frontera else pd.Timestamp(hoy)
    version = a.version or f"reentreno-{frontera.date().isoformat()}"
    salida = ROOT / "dist/reentrenos" / version
    procesados = ROOT / "data/processed" / version
    for carpeta in (salida, procesados):
        if carpeta.exists():
            if not a.sobrescribir:
                raise SystemExit(f"Ya existe {carpeta}; usar --sobrescribir para repetir esta versión.")
            shutil.rmtree(carpeta)
    crudos, fuentes, avisos = descargar(hoy, frontera)
    snapshot = crudos.name
    brent = fuentes["brent"].loc["2000-01-01":frontera]
    c = dict(c, _corte=frontera.year)
    resumen = preparar_datos(fuentes, brent, frontera, procesados, snapshot, "reentreno")
    commit, cambios = git()
    if cambios:
        print(f"Aviso: archivos versionados modificados sin commit: {cambios}")
    (salida / "modelo").mkdir(parents=True)
    (salida / "ajustes").mkdir()
    estudio_dir, estudio_cfg = cargar_modelo(a.modelo_estudio, None)
    for clave, valor in (("horizontes", c["horizontes_fechas_brent"]), ("ventana", c["ventana_fechas_brent"]),
                         ("objetivo", c["objetivo"]), ("base", c["base"]), ("entradas", c["entradas"]),
                         ("arquitectura", arquitectura), ("semillas", c["semillas"])):
        if estudio_cfg[clave] != valor:
            raise ValueError(f"El modelo del estudio difiere en {clave}.")
    import onnxruntime as ort
    modelos, tramos, cordura, onnx_max, gpu_max = [], {}, {}, 0.0, 0.0
    for h in c["horizontes_fechas_brent"]:
        cambios_interno = []
        for semilla in c["semillas"]:
            r = entrenar(c, arquitectura, h, semilla, procesados, snapshot, "reentreno")
            nombre = f"{arquitectura}_h{h:03d}_semilla{semilla}"
            ajuste = salida / "ajustes" / nombre
            ajuste.mkdir()
            torch.save(r["modelo"].state_dict(), ajuste / "modelo.pt")
            r["historial"].to_csv(ajuste / "epocas.csv", index=False)
            parametros = sum(p.numel() for p in r["modelo"].parameters())
            registro = dict(id=nombre, fase="reentreno", version=version, snapshot=snapshot, frontera=fecha(frontera),
                            arquitectura=arquitectura, unidades=r["unidades"], horizonte=h, semilla=semilla,
                            tasa_aprendizaje=r["tasa"], parametros=parametros, mejor_epoca=r["mejor"],
                            epocas=int(len(r["historial"])), mae_interno_minimo=float(r["historial"].mae_interno.min()),
                            segundos_entrenamiento=r["segundos"], python=platform.python_version(),
                            torch=torch.__version__, cuda=torch.version.cuda, dispositivo=torch.cuda.get_device_name(),
                            script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), commit=commit,
                            cambios_sin_commit=cambios,
                            tramos={k: resumen_tramo(f) for k, f in r["fechas"].items()})
            (ajuste / "registro.json").write_text(json.dumps(registro, indent=2, allow_nan=False), encoding="utf-8")
            if semilla == c["semillas"][0]:
                (salida / "modelo" / f"escalador_h{h:03d}.json").write_text(
                    json.dumps(escalador_publicable(r["escalador"]), indent=2), encoding="utf-8")
                tramos[str(h)] = registro["tramos"]
                objetivo_interno, fechas_interno = r["objetivos"]["interno"], r["fechas"]["interno"]
            archivo = salida / "modelo" / f"{nombre}.onnx"
            r["modelo"].eval()
            a_onnx(r["modelo"], archivo, len(r["escalador"]["orden_entradas"]))
            sesion = ort.InferenceSession(str(archivo), providers=["CPUExecutionProvider"])
            onnx_salida = sesion.run(None, {"ventanas": r["entradas"]["interno"]})[0]
            # La aplicación predice en CPU: ONNX se compara con PyTorch en CPU. La salida en GPU usa TF32 en
            # cuDNN (activado por defecto) y difiere más, sobre todo a +252; se registra aparte.
            cpu = predecir(r["modelo"], torch.from_numpy(r["entradas"]["interno"]), c["tamano_lote"]).numpy()
            onnx_max = max(onnx_max, float(np.abs(onnx_salida - cpu).max()))
            gpu_max = max(gpu_max, float(np.abs(r["salidas"]["interno"] - cpu).max()))
            cambios_interno.append(r["salidas"]["interno"])
            modelos.append(dict(archivo=archivo.name, horizonte=h, semilla=semilla, unidades=r["unidades"],
                                parametros=parametros, mejor_epoca=r["mejor"], epocas=registro["epocas"],
                                mae_interno_semilla=registro["mae_interno_minimo"],
                                sha256=hashlib.sha256(archivo.read_bytes()).hexdigest()))
            print(f"+{h} semilla {semilla}: mejor época {r['mejor']} de {registro['epocas']}; "
                  f"MAE interno {registro['mae_interno_minimo']:.3f} USD")
        # La salida es el cambio frente a la base y el objetivo, el cambio real: el error está en USD.
        # La base es el ingenuo con futuros (o el spot sin futuro), así que su error es |cambio real|.
        media = np.mean(cambios_interno, axis=0)
        mae_red = float(np.abs(media - objetivo_interno).mean())
        mae_ref = float(np.abs(objetivo_interno).mean())
        cordura[str(h)] = dict(n=int(len(objetivo_interno)), inicio=fecha(fechas_interno.fecha_origen.min()),
                               fin=fecha(fechas_interno.fecha_origen.max()),
                               origenes_desde_test_estudio=int((pd.to_datetime(fechas_interno.fecha_origen) >= FRONTERA_ESTUDIO).sum()),
                               mae_red_media_semillas=mae_red, mae_ingenuo_con_futuros=mae_ref,
                               mejora_pct_frente_futuros=100 * (1 - mae_red / mae_ref))
    origen = pd.Timestamp(hoy) - pd.offsets.BDay(0)
    config = dict(
        version=version, arquitectura=arquitectura, horizontes=c["horizontes_fechas_brent"],
        ventana=c["ventana_fechas_brent"], objetivo=c["objetivo"], base=c["base"], entradas=c["entradas"],
        variables_en_variacion=estudio_cfg["variables_en_variacion"], semillas=c["semillas"],
        prediccion=estudio_cfg["prediccion"], base_descripcion=estudio_cfg["base_descripcion"],
        intervalo=dict(intervalo(arquitectura), nota="Márgenes del estudio; no se recalibran al reentrenar."),
        entrenamiento=dict(frontera=fecha(frontera), snapshot=snapshot, datos=procesados.relative_to(ROOT).as_posix(),
                           metodo="mismo método que el ajuste final del estudio (reports/experimentos/final/config.json)",
                           tramos=tramos, commit=commit, cambios_sin_commit=cambios, avisos_descarga=avisos),
        evaluacion_test=dict(evaluacion_test(arquitectura), version_evaluada=estudio_cfg["version"],
                             nota=("Esta versión no tiene test propio: las cifras son del test del estudio y miden la "
                                   "fiabilidad del método, no de estos pesos.")),
        modelos=modelos)
    (salida / "modelo" / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    hoy_prev = prevision_hoy(fuentes, origen, {"nuevo": salida / "modelo", "estudio": estudio_dir})
    config["comprobacion_cordura"] = dict(
        descripcion=("Comprobación de cordura, no evaluación: el tramo de parada temprana (último 15 % de los orígenes "
                     "con etiqueta conocida) decide la época de cada semilla y se solapa con el test del estudio."),
        tramo_interno=cordura, onnx_frente_pytorch_cpu_max=onnx_max, pytorch_gpu_frente_cpu_max=gpu_max,
        prevision_hoy=dict(origen=fecha(origen), **hoy_prev),
        resumen_web=dict(frontera=fecha(frontera), interno=cordura,
                         opep=dict(origen=fecha(origen), diferencias=hoy_prev["nuevo"]["diferencia_sin_opep"])))
    (salida / "modelo" / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    informe = dict(version=version, frontera=fecha(frontera), datos=resumen.astype(str).to_dict("records"),
                   **config["comprobacion_cordura"])
    (salida / "informe_cordura.json").write_text(json.dumps(informe, indent=2, ensure_ascii=False), encoding="utf-8")
    imprimir_informe(config["comprobacion_cordura"], version)
    print(f"Revisar el informe y, si es razonable, publicar:\n  poetry run python -m scripts.publicar_hf "
          f"--repo AvaroSantamaria/brent-rnn --carpeta {(salida / 'modelo').relative_to(ROOT).as_posix()}")


def imprimir_informe(r, version):
    print(f"\nInforme de cordura de {version} (no es una evaluación: ver descripción)")
    print(f"Tramo interno: ONNX frente a PyTorch en CPU, diferencia máxima {r['onnx_frente_pytorch_cpu_max']:.2e}; "
          f"PyTorch en GPU (TF32) frente a CPU, {r['pytorch_gpu_frente_cpu_max']:.2e}")
    for h, t in r["tramo_interno"].items():
        print(f"  +{h}: tramo interno {t['inicio']} a {t['fin']} ({t['n']} orígenes, {t['origenes_desde_test_estudio']} "
              f"desde 2023); MAE red {t['mae_red_media_semillas']:.3f}, ingenuo con futuros "
              f"{t['mae_ingenuo_con_futuros']:.3f} ({t['mejora_pct_frente_futuros']:+.2f} %)")
    p = r["prevision_hoy"]
    print(f"Previsión del {p['origen']}:")
    for nombre in ("nuevo", "estudio"):
        m = p[nombre]
        texto = "; ".join(f"+{h} {m['con_opep'][h]:.2f} (sin OPEP {m['sin_opep'][h]:.2f}, {m['diferencia_sin_opep'][h]:+.2f})"
                          for h in m["con_opep"])
        print(f"  {m['version']}: base {m['base']:.2f}; {texto}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reproducir-estudio", action="store_true",
                        help="Comprobación con el paquete y la frontera 02/01/2023 frente a reports/experimentos/final/")
    parser.add_argument("--solo-datos", action="store_true", help="Con --reproducir-estudio: comprobar solo los datos")
    parser.add_argument("--version", help="Nombre de la versión (por defecto, reentreno-<frontera>)")
    parser.add_argument("--frontera", help="Fecha de corte YYYY-MM-DD (por defecto, hoy en Madrid)")
    parser.add_argument("--modelo-estudio", default=str(ROOT / "dist/huggingface/modelo"),
                        help="Carpeta del modelo del estudio exportado (scripts/export_onnx.py)")
    parser.add_argument("--sobrescribir", action="store_true", help="Repetir una versión ya preparada en local")
    a = parser.parse_args()
    c = leer_configuracion()
    arquitectura = c["seleccionada"]
    if tuple(c["horizontes_fechas_brent"]) != HORIZONTES:
        parser.error("Los horizontes de la configuración final no coinciden con los de las ventanas.")
    if not (a.reproducir_estudio and a.solo_datos) and not torch.cuda.is_available():
        parser.error("Se requiere CUDA disponible, como en el ajuste final del estudio.")
    if a.reproducir_estudio:
        reproducir(dict(c, _corte=FRONTERA_ESTUDIO.year), arquitectura, a.solo_datos)
    else:
        if a.solo_datos:
            parser.error("--solo-datos solo se usa con --reproducir-estudio.")
        reentrenar(c, arquitectura, a)


if __name__ == "__main__":
    main()
