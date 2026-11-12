"""Actualización diaria de la aplicación: datos, entradas, predicción con ONNX y JSON para la web.

Reproduce las reglas del estudio sin PyTorch:
1. obtiene las fuentes (descarga en vivo o, con --paquete, el paquete fijo del estudio);
2. construye la tabla a las 09:00 con el calendario del Brent de FRED, ampliado con días de lunes a
   viernes hasta la fecha de origen (FRED publica el spot con retraso);
3. pasa los precios a variaciones, escala con los escaladores publicados y toma la ventana de 60 fechas;
4. calcula la base (ingenuo con futuros; si falta, el último spot admisible);
5. predice con las tres semillas de cada horizonte (ONNX) y escribe prediccion.json.
Los modelos se leen de una carpeta local (--modelo) o de un repositorio de Hugging Face (--repo-modelo).
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo

import numpy as np
import onnxruntime as ort
import pandas as pd

from scripts.prepare_daily_inputs import FRED, YAHOO, cesta_opep, construir_tabla, deposito_bce, fuentes_paquete
from scripts.prepare_scalers import a_variaciones
from src.oil_price_prediction.referencias import ingenuo_con_futuros_tabla

ROOT = Path(__file__).resolve().parents[2]
ZONA = ZoneInfo("Europe/Madrid")
SERIES_FRED = {"DCOILBRENTEU": "brent", "DCOILWTICO": "wti", "DHHNGSP": "gas_natural", "DEXUSEU": "usd_por_eur",
               "DEXCHUS": "cny_por_usd", "VIXCLS": "vix"}
SERIES_YAHOO = {"BZ=F": "brent_fut", "CL=F": "wti_fut", "HG=F": "cobre", "GC=F": "oro", "DX-Y.NYB": "indice_dolar"}


def fuentes_en_vivo(inicio, fin, carpeta):
    """Descarga las mismas fuentes que el estudio (FRED, Yahoo, OPEP y tabla del BCE)."""
    from scripts import download_raw_data as raw
    from scripts.download_all_data import ECB_URL, OPEC_URL, obtener
    fuentes = {"yahoo": {}}
    for serie, nombre in SERIES_FRED.items():
        df = raw.descargar_fuente("fred", serie, nombre, inicio, fin)
        raw.validar_fuente(df, inicio, fin)
        fuentes[nombre] = df[nombre]
    for serie, nombre in SERIES_YAHOO.items():
        df = raw.descargar_fuente("yahoo", serie, nombre, inicio, fin)
        raw.validar_fuente(df, inicio, fin)
        fuentes["yahoo"][nombre] = df
    (carpeta / "opep.xml").write_bytes(obtener(OPEC_URL))
    (carpeta / "bce.html").write_bytes(obtener(ECB_URL))
    fuentes["cesta_opep"] = cesta_opep(carpeta / "opep.xml")
    fuentes["tipo_bce"] = deposito_bce(carpeta / "bce.html")
    if set(fuentes) != {"brent", *FRED, "yahoo", "cesta_opep", "tipo_bce"} or set(fuentes["yahoo"]) != set(YAHOO):
        raise ValueError("Faltan fuentes.")
    return fuentes


def calendario(indice_brent, origen):
    """Índice del Brent de FRED hasta el origen, ampliado con días de lunes a viernes."""
    fechas = indice_brent[indice_brent <= origen]
    extra = pd.bdate_range(fechas.max() + pd.Timedelta(days=1), origen) if fechas.max() < origen else []
    return fechas.append(pd.DatetimeIndex(extra)).rename("fecha")


def ventana_escalada(tabla, escalador, origen, longitud):
    variables = [c.removesuffix("_disponible") for c in tabla if c.endswith("_disponible")]
    valores = tabla[variables]
    if escalador.get("entradas") == "variaciones":
        if escalador["variables_en_variacion"] != [v for v in escalador["variables_en_variacion"] if v in variables]:
            raise ValueError("Variables en variación desconocidas.")
        valores = a_variaciones(valores)
    indicadores = valores.notna().astype(int)
    indicadores.columns = [f"{v}_disponible" for v in variables]
    escaladas = ((valores - pd.Series(escalador["media"])) / pd.Series(escalador["divisor"])).fillna(0)
    completa = escaladas.join(indicadores)[escalador["orden_entradas"]]
    posicion = completa.index.get_loc(origen)
    if posicion < longitud - 1:
        raise ValueError("No hay historia suficiente para la ventana.")
    return completa.iloc[posicion - longitud + 1:posicion + 1].to_numpy(dtype="float32")[None]


def cargar_modelo(modelo, repo):
    if repo:
        from huggingface_hub import snapshot_download
        modelo = snapshot_download(repo_id=repo, repo_type="model")
    carpeta = Path(modelo)
    return carpeta, json.loads((carpeta / "config.json").read_text(encoding="utf-8"))


def frescura(tabla, origen):
    fila = tabla.loc[origen]
    salida = {}
    for v in [c.removesuffix("_disponible") for c in tabla if c.endswith("_disponible")]:
        origen_v = fila[f"{v}_origen"]
        salida[v] = dict(disponible=bool(fila[f"{v}_disponible"]), estado=str(fila[f"{v}_estado"]),
                         observacion=None if pd.isna(origen_v) else pd.Timestamp(origen_v).date().isoformat(),
                         edad_dias_habiles=None if pd.isna(fila[f"{v}_edad"]) else int(fila[f"{v}_edad"]))
    return salida


def predecir(fuentes, fechas, origen, carpeta_modelo, config):
    tabla = construir_tabla(fuentes, fechas)
    if origen not in tabla.index:
        raise ValueError("La fecha de origen no está en el calendario.")
    referencias = ingenuo_con_futuros_tabla(tabla.reset_index())
    spot = tabla.at[origen, "brent"]
    con_futuros = referencias.loc[origen]
    if pd.isna(spot):
        raise ValueError("No hay Brent spot admisible en el origen.")
    base = float(con_futuros) if not pd.isna(con_futuros) else float(spot)
    previsiones = []
    for h in config["horizontes"]:
        escalador = json.loads((carpeta_modelo / f"escalador_h{h:03d}.json").read_text(encoding="utf-8"))
        x = ventana_escalada(tabla, escalador, origen, config["ventana"])
        salidas = {}
        for m in [m for m in config["modelos"] if m["horizonte"] == h]:
            sesion = ort.InferenceSession(str(carpeta_modelo / m["archivo"]), providers=["CPUExecutionProvider"])
            salidas[m["semilla"]] = float(sesion.run(None, {"ventanas": x})[0][0])
        cambio = float(np.mean(list(salidas.values())))
        precio = base + cambio
        margen = config["intervalo"]["margenes"][str(h)]
        previsiones.append(dict(
            horizonte=h, fecha_objetivo=(origen + pd.offsets.BDay(h)).date().isoformat(), precio=precio,
            intervalo=[precio - margen, precio + margen], margen=margen,
            variacion_frente_base=cambio, variacion_pct_frente_base=100 * cambio / base,
            ingenuo=float(spot), ingenuo_con_futuros=None if pd.isna(con_futuros) else float(con_futuros),
            cambio_por_semilla=salidas))
    # Futuro de Brent en la fecha del spot (último cierre observado en o antes de ella), para explicar la base.
    futuro_base = futuro_base_fecha = None
    if not pd.isna(con_futuros):
        cierres = (tabla.loc[tabla.brent_fut_Close_disponible == 1, ["brent_fut_Close_origen", "brent_fut_Close"]]
                   .drop_duplicates("brent_fut_Close_origen").set_index("brent_fut_Close_origen").brent_fut_Close.sort_index())
        anteriores = cierres[cierres.index <= tabla.at[origen, "brent_origen"]]
        futuro_base, futuro_base_fecha = float(anteriores.iloc[-1]), pd.Timestamp(anteriores.index[-1]).date().isoformat()
    return tabla, dict(
        base=dict(valor=base, tipo="futuros" if not pd.isna(con_futuros) else "spot", spot=float(spot),
                  futuro_base=futuro_base, futuro_base_fecha=futuro_base_fecha,
                  spot_fecha=pd.Timestamp(tabla.at[origen, "brent_origen"]).date().isoformat(),
                  futuro=None if pd.isna(tabla.at[origen, "brent_fut_Close"]) else float(tabla.at[origen, "brent_fut_Close"]),
                  futuro_fecha=None if pd.isna(tabla.at[origen, "brent_fut_Close_origen"])
                  else pd.Timestamp(tabla.at[origen, "brent_fut_Close_origen"]).date().isoformat()),
        previsiones=previsiones)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modelo", default=str(ROOT / "dist/huggingface/modelo"), help="Carpeta local del modelo")
    parser.add_argument("--repo-modelo", help="Repositorio de Hugging Face del modelo (sustituye a --modelo)")
    parser.add_argument("--origen", help="Fecha de predicción YYYY-MM-DD (por defecto, hoy en Madrid; fin de semana: viernes)")
    parser.add_argument("--paquete", action="store_true", help="Usar el paquete fijo del estudio en lugar de descargar")
    parser.add_argument("--salida", default=str(ROOT / "dist/huggingface/datos/prediccion.json"))
    parser.add_argument("--repo-datos", help="Repositorio de datos de Hugging Face donde publicar el JSON")
    a = parser.parse_args()
    hoy = datetime.now(ZONA).date()
    origen = pd.Timestamp(a.origen) if a.origen else pd.Timestamp(hoy) - pd.offsets.BDay(0)
    if origen.weekday() >= 5:
        parser.error("La fecha de origen debe ser de lunes a viernes.")
    carpeta_modelo, config = cargar_modelo(a.modelo, a.repo_modelo)
    with tempfile.TemporaryDirectory() as tmp:
        if a.paquete:
            fuentes, fechas_paquete = fuentes_paquete()
            fechas = calendario(fechas_paquete, origen)
        else:
            fuentes = fuentes_en_vivo("2000-01-01", hoy.isoformat(), Path(tmp))
            fechas = calendario(fuentes["brent"].loc["2000-01-01":].index, origen)
        tabla, resultado = predecir(fuentes, fechas, origen, carpeta_modelo, config)
    brent = fuentes["brent"].dropna()
    futuro = fuentes["yahoo"]["brent_fut"]["brent_fut_Close"].dropna()
    salida = dict(
        generado_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"), origen=origen.date().isoformat(),
        hora_referencia="09:00 Europe/Madrid", fuente_datos="paquete del estudio" if a.paquete else "descarga en vivo",
        modelo=dict(version=config["version"], arquitectura=config["arquitectura"], semillas=config["semillas"],
                    entrenamiento=config["entrenamiento"]["frontera"], nivel_intervalo=config["intervalo"]["nivel"]),
        **resultado, fuentes=frescura(tabla, origen),
        historico=dict(brent_spot=[[d.date().isoformat(), round(float(v), 2)] for d, v in brent[brent.index <= origen].items()],
                       # Solo cierres ya conocidos a las 09:00 del origen (Yahoo puede dar la sesión en curso).
                       brent_futuro=[[d.date().isoformat(), round(float(v), 2)] for d, v in futuro[futuro.index < origen].items()]))
    destino = Path(a.salida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Origen {salida['origen']}; base {resultado['base']['valor']:.2f} USD ({resultado['base']['tipo']})")
    for p in resultado["previsiones"]:
        print(f"  +{p['horizonte']} ({p['fecha_objetivo']}): {p['precio']:.2f} USD "
              f"[{p['intervalo'][0]:.2f}, {p['intervalo'][1]:.2f}]")
    print(destino)
    if a.repo_datos:
        if a.paquete:
            parser.error("No se publican previsiones calculadas con el paquete del estudio.")
        publicar(a.repo_datos, destino, salida["origen"])


def publicar(repo, archivo, origen):
    """Sube la previsión vigente (prediccion.json) y una copia en historial/<origen>.json."""
    from huggingface_hub import CommitOperationAdd, HfApi
    api = HfApi()
    api.create_repo(repo, repo_type="dataset", exist_ok=True)
    info = api.create_commit(repo_id=repo, repo_type="dataset", commit_message=f"Previsión del {origen}", operations=[
        CommitOperationAdd(path_in_repo="prediccion.json", path_or_fileobj=str(archivo)),
        CommitOperationAdd(path_in_repo=f"historial/{origen}.json", path_or_fileobj=str(archivo))])
    print(info.commit_url)


if __name__ == "__main__":
    main()
