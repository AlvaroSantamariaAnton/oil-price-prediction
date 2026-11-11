"""Evaluación única del test (orígenes desde el 02/01/2023).

Promedia las tres semillas de cada arquitectura y horizonte guardadas en reports/experimentos/final/,
compara con el ingenuo del protocolo y con el ingenuo con futuros y escribe:
- reports/evaluacion_test.csv: tabla por horizonte y predictor (n, MSE, MAE, RMSE, mejoras, parámetros,
  tiempo, cobertura y anchura del intervalo, acierto direccional, Diebold-Mariano e IC95 por bloques);
- reports/figuras/E14-E16/test/: las mismas seis figuras que en validación, por año de origen.
Los márgenes del intervalo son los de validación (reports/margenes_validacion.json), fijados antes del
test. Este script se ejecuta una sola vez, cuando el usuario lo decide.
"""

import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.evaluate_validation_uncertainty import ARQUITECTURAS, REPLICAS, SEMILLA, diebold_mariano, indices_bloques
from scripts.plot_validation import dibujar
from scripts.prepare_windows import HORIZONTES, ROOT

FINAL = ROOT / "reports/experimentos/final"
DESTINO_TABLA = ROOT / "reports/evaluacion_test.csv"
DESTINO_FIGURAS = ROOT / "reports/figuras/E14-E16/test"


def cargar_final():
    config = json.loads((FINAL / "config.json").read_text(encoding="utf-8"))
    ajustes = {}
    for carpeta in sorted(glob.glob(str(FINAL / "*" / "registro.json"))):
        r = json.loads(Path(carpeta).read_text(encoding="utf-8"))
        clave = (r["arquitectura"], r["horizonte"], r["semilla"])
        if clave in ajustes:
            raise ValueError(f"Ajuste final duplicado: {clave}")
        if r["unidades"] != config["unidades"][r["arquitectura"]][str(r["horizonte"])]:
            raise ValueError(f"Tamaño distinto del configurado: {clave}")
        ajustes[clave] = (r, pd.read_csv(Path(carpeta).parent / "predicciones_test.csv"))
    esperados = {(a, h, s) for a in config["arquitecturas"] for h in config["horizontes_fechas_brent"]
                 for s in config["semillas"]}
    if set(ajustes) != esperados:
        raise ValueError("Faltan o sobran ajustes finales.")
    return config, ajustes


def tabla_promediada(config, ajustes, a, h):
    partes = [ajustes[a, h, s][1] for s in config["semillas"]]
    base = partes[0][["fecha_origen", "fecha_objetivo", "brent_objetivo", "prediccion_ingenua",
                      "prediccion_ingenua_futuros"]].copy()
    for p in partes[1:]:
        if not p[base.columns].equals(base):
            raise ValueError(f"Las semillas no comparten orígenes ni referencias en {a} +{h}.")
    base["prediccion"] = np.mean([p.prediccion_red.to_numpy() for p in partes], axis=0)
    for col in ("fecha_origen", "fecha_objetivo"):
        base[col] = pd.to_datetime(base[col])
    base["corte"] = base.fecha_origen.dt.year
    base["error"] = (base.prediccion - base.brent_objetivo).abs()
    base["error_ingenuo"] = (base.prediccion_ingenua - base.brent_objetivo).abs()
    base["error_futuros"] = (base.prediccion_ingenua_futuros - base.brent_objetivo).abs()
    if base[["prediccion", "prediccion_ingenua", "prediccion_ingenua_futuros"]].isna().any().any():
        raise ValueError("Predicción ausente en el test.")
    return base


def fila(nombre, h, t, columna_prediccion, columna_error, rng, extra):
    error = t[columna_error].to_numpy()
    real = np.sign(t.brent_objetivo - t.prediccion_ingenua)
    previsto = np.sign(t[columna_prediccion] - t.prediccion_ingenua)
    validos = real != 0
    resultado = dict(horizonte=h, predictor=nombre, n=len(t), mse=float(np.mean((t[columna_prediccion] - t.brent_objetivo) ** 2)),
                     mae=float(error.mean()))
    resultado["rmse"] = resultado["mse"] ** 0.5
    for referencia, col in (("ingenuo", "error_ingenuo"), ("futuros", "error_futuros")):
        ref = t[col].to_numpy()
        resultado[f"mejora_frente_{referencia}"] = float(100 * (1 - error.mean() / ref.mean()))
        if columna_error == col:
            continue
        indices = indices_bloques(rng, len(t), h, REPLICAS)
        muestras = 100 * (1 - error[indices].mean(axis=1) / ref[indices].mean(axis=1))
        resultado[f"ic95_frente_{referencia}"] = [float(x) for x in np.percentile(muestras, [2.5, 97.5])]
        resultado[f"p_dm_frente_{referencia}"] = diebold_mariano(error - ref, h)[1]
    resultado["acierto_direccional"] = float(np.mean(previsto[validos] == real[validos])) if columna_prediccion != "prediccion_ingenua" else None
    resultado.update(extra)
    return resultado


def main():
    config, ajustes = cargar_final()
    datos_margenes = json.loads((ROOT / "reports/margenes_validacion.json").read_text(encoding="utf-8"))
    if datos_margenes["familia"] != "futuros":
        raise ValueError("Los márgenes no corresponden a la familia seleccionada.")
    margenes = {(m["arquitectura"], m["horizonte"]): m["margen"] for m in datos_margenes["margenes"].values()}
    tamanos = {(a, h): config["unidades"][a][str(h)] for a in ARQUITECTURAS for h in HORIZONTES}
    if any(m["unidades"] != tamanos[m["arquitectura"], m["horizonte"]] for m in datos_margenes["margenes"].values()):
        raise ValueError("Los márgenes se calcularon con otros tamaños.")
    tablas = {(a, h): tabla_promediada(config, ajustes, a, h) for a in ARQUITECTURAS for h in HORIZONTES}
    rng = np.random.default_rng(SEMILLA)
    filas = []
    for h in HORIZONTES:
        t = tablas[config["seleccionada"], h]
        filas.append(fila("Ingenuo", h, t, "prediccion_ingenua", "error_ingenuo", rng, {}))
        filas.append(fila("Ingenuo con futuros", h, t, "prediccion_ingenua_futuros", "error_futuros", rng, {}))
        for a in ARQUITECTURAS:
            t = tablas[a, h]
            registros = [ajustes[a, h, s][0] for s in config["semillas"]]
            dentro = t.error <= margenes[a, h]
            filas.append(fila(a, h, t, "prediccion", "error", rng, dict(
                unidades=tamanos[a, h], parametros_por_modelo=registros[0]["parametros"],
                segundos_entrenamiento_3_semillas=float(sum(r["segundos_entrenamiento"] for r in registros)),
                margen_usd=margenes[a, h], anchura_intervalo_usd=2 * margenes[a, h],
                cobertura_intervalo=float(dentro.mean()),
                cobertura_por_anio={int(k): float(v) for k, v in dentro.groupby(t.corte).mean().items()},
                seleccionada=a == config["seleccionada"])))
    tabla = pd.DataFrame(filas)
    tabla.to_csv(DESTINO_TABLA, index=False)
    columnas = ["horizonte", "predictor", "n", "mae", "rmse", "mejora_frente_ingenuo", "mejora_frente_futuros",
                "acierto_direccional", "cobertura_intervalo"]
    with pd.option_context("display.width", 200, "display.float_format", "{:.3f}".format):
        print(tabla[columnas].to_string(index=False))
    dibujar(tablas, tamanos, config["seleccionada"], margenes, DESTINO_FIGURAS, "Test 2023–2026 (E14-E16)",
            "media de 3 semillas")
    print(DESTINO_TABLA)
    print(DESTINO_FIGURAS)


if __name__ == "__main__":
    main()
