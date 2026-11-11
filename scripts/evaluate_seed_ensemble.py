"""Promedio de semillas en la validación anual y selección entre familias de réplicas.

Familias: objetivo `cambio` (E2, E3, E4) y objetivo `porcentaje` (E5, E6, E7).
Solo lee predicciones de validación ya guardadas; no entrena ni consulta el test.
Las reglas están fijadas en docs/protocolo_experimento.md («Promedio de semillas» y «E5»).
"""

import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.evaluate_validation_uncertainty import (ARQUITECTURAS, CORTES, REPLICAS, SEMILLA, diebold_mariano,
                                                     indices_bloques, mejora)
from scripts.prepare_windows import HORIZONTES, ROOT

FAMILIAS = {"cambio": ("E2", "E3", "E4"), "porcentaje": ("E5", "E6", "E7")}


def cargar(objetivo, replicas):
    predicciones, tiempos, semillas = {}, {}, set()
    for e in replicas:
        config = json.loads((ROOT / "reports/experimentos" / e / "config.json").read_text(encoding="utf-8"))
        if config["objetivo"] != objetivo:
            raise ValueError(f"{e} no tiene el objetivo {objetivo}.")
        semillas.add(config["semilla"])
        for carpeta in glob.glob(str(ROOT / "reports/experimentos" / e / "validacion" / "*")):
            r = json.loads(Path(carpeta, "registro.json").read_text(encoding="utf-8"))
            clave = (e, r["arquitectura"], r["horizonte"], r["unidades"], r["corte"])
            if clave in predicciones:
                raise ValueError(f"Ajuste duplicado: {clave}")
            predicciones[clave] = pd.read_csv(Path(carpeta, "predicciones.csv"))
            tiempos[r["arquitectura"]] = tiempos.get(r["arquitectura"], 0.0) + r["segundos_entrenamiento"]
    if len(semillas) != len(replicas) or len(predicciones) != 72 * len(replicas):
        raise ValueError("Faltan ajustes o se repite una semilla.")
    return predicciones, tiempos


def promediar(predicciones, replicas, a, h, u, c):
    partes = [predicciones[e, a, h, u, c] for e in replicas]
    base = partes[0]
    for p in partes[1:]:
        if not (p.fecha_origen.equals(base.fecha_origen) and p.brent_objetivo.equals(base.brent_objetivo)):
            raise ValueError("Las réplicas no comparten fechas u objetivos.")
    prediccion = np.mean([p.prediccion_red.to_numpy() for p in partes], axis=0)
    return (np.abs(prediccion - base.brent_objetivo.to_numpy()), base.error_absoluto_ingenuo.to_numpy(),
            [np.abs(p.prediccion_red.to_numpy() - base.brent_objetivo.to_numpy()) for p in partes])


def evaluar_familia(objetivo, replicas):
    predicciones, tiempos = cargar(objetivo, replicas)
    resultados = {}
    print(f"=== Objetivo {objetivo} ({', '.join(replicas)}) ===")
    for a in ARQUITECTURAS:
        tamanos, anuales_sel = {}, {}
        for h in HORIZONTES:
            medias = {}
            for u in (32, 64):
                anuales = [mejora(*promediar(predicciones, replicas, a, h, u, c)[:2]) for c in CORTES]
                medias[u] = (np.mean(anuales), anuales)
            u = 32 if medias[32][0] >= medias[64][0] else 64
            tamanos[h], anuales_sel[h] = u, medias[u][1]
            datos = {c: promediar(predicciones, replicas, a, h, u, c) for c in CORTES}
            individuales = [np.mean([mejora(datos[c][2][i], datos[c][1]) for c in CORTES])
                            for i in range(len(replicas))]
            print(f"{a:4s} +{h:<3d} 32: {medias[32][0]:7.2f}  64: {medias[64][0]:7.2f}  -> {u}  anuales "
                  + " / ".join(f"{x:+.2f}" for x in medias[u][1])
                  + "  | cada semilla " + " / ".join(f"{x:+.2f}" for x in individuales))
        puntuacion = np.mean(sum(anuales_sel.values(), []))
        resultados[objetivo, a] = dict(puntuacion=puntuacion, tamanos=tamanos, tiempo=tiempos[a],
                                       predicciones=predicciones, replicas=replicas)
        print(f"{a:4s} GLOBAL {puntuacion:7.2f} %  tamaños {tamanos}  pares positivos "
              f"{sum(x > 0 for x in sum(anuales_sel.values(), []))}/12  tiempo {tiempos[a]:.2f} s\n")
    return resultados


def main():
    rng = np.random.default_rng(SEMILLA)
    resultados = {}
    for objetivo, replicas in FAMILIAS.items():
        resultados.update(evaluar_familia(objetivo, replicas))
    mejor = max(resultados, key=lambda k: resultados[k]["puntuacion"])
    empatados = [k for k in resultados if resultados[mejor]["puntuacion"] - resultados[k]["puntuacion"] <= 1]
    elegido = min(empatados, key=lambda k: resultados[k]["tiempo"])
    print(f"Mejor puntuación: {mejor}; dentro de 1 pp: {empatados}; elegido: {elegido}")
    r = resultados[elegido]
    for h in HORIZONTES:
        if h == max(HORIZONTES):
            continue
        u = r["tamanos"][h]
        datos = {c: promediar(r["predicciones"], r["replicas"], elegido[1], h, u, c)[:2] for c in CORTES}
        indices = {c: indices_bloques(rng, len(datos[c][0]), h, REPLICAS) for c in CORTES}
        muestras = np.mean([mejora(datos[c][0][indices[c]], datos[c][1][indices[c]]) for c in CORTES], axis=0)
        dm, valor_p = diebold_mariano(np.concatenate([datos[c][0] - datos[c][1] for c in CORTES]), h)
        bajo, alto = np.percentile(muestras, [2.5, 97.5])
        print(f"{elegido} promedio +{h} u{u}: IC95 [{bajo:.2f}, {alto:.2f}]  P(>0) {np.mean(muestras > 0):.3f}  "
              f"DM {dm:+.2f} (p {valor_p:.3f})")


if __name__ == "__main__":
    main()
