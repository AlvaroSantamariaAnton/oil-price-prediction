"""Promedio de semillas en la validación anual y selección entre familias de réplicas.

Cada familia indica qué réplicas (una por semilla) se promedian en cada horizonte:
- precio: E1, una sola semilla (registro; sus ocho GRU +5 repetidos son idénticos y cuentan una vez).
- cambio: E2, E3 y E4 en los tres horizontes.
- porcentaje: E5, E6 y E7 (descartada según su regla; se muestra como registro).
- cambio_tasa_menor: +5 de E2–E4 y +63/+252 de E8–E10 (tasa 0,0001).
- variaciones: E11, E12 y E13 en los tres horizontes (entradas de precio en variación diaria).
- futuros: E14, E15 y E16 (como variaciones, con el cambio medido desde el ingenuo con futuros).
La selección compara los candidatos de `variaciones` y `futuros` (regla de E14–E16); las familias
anteriores quedaron superadas y se muestran como registro. Para cada candidato se informa también
de la mejora frente al ingenuo con futuros.
Solo lee predicciones de validación ya guardadas; no entrena ni consulta el test.
Las reglas están fijadas en docs/protocolo_experimento.md.
"""

import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.evaluate_validation_uncertainty import (ARQUITECTURAS, CORTES, REPLICAS, SEMILLA, diebold_mariano,
                                                     indices_bloques, mejora)
from scripts.prepare_windows import HORIZONTES, ROOT, SNAPSHOT

CAMBIO = ("E2", "E3", "E4")
FAMILIAS = {
    "precio": {h: ("E1",) for h in HORIZONTES},
    "cambio": {h: CAMBIO for h in HORIZONTES},
    "porcentaje": {h: ("E5", "E6", "E7") for h in HORIZONTES},
    "cambio_tasa_menor": {5: CAMBIO, 63: ("E8", "E9", "E10"), 252: ("E8", "E9", "E10")},
    "variaciones": {h: ("E11", "E12", "E13") for h in HORIZONTES},
    "futuros": {h: ("E14", "E15", "E16") for h in HORIZONTES},
}
OBJETIVO = {"precio": "precio", "cambio": "cambio", "porcentaje": "porcentaje", "cambio_tasa_menor": "cambio", "variaciones": "cambio",
            "futuros": "cambio"}
ENTRADAS = {"variaciones": "variaciones", "futuros": "variaciones"}
BASE = {"futuros": "futuros"}
SELECCION = ("variaciones", "futuros")


def ingenuo_futuros():
    from src.oil_price_prediction.train_validation import ingenuo_con_futuros
    serie = ingenuo_con_futuros(ROOT / "data/processed" / SNAPSHOT)
    serie.index = serie.index.astype(str)
    return serie


def cargar(familia):
    predicciones, tiempos = {}, {}
    for h, replicas in FAMILIAS[familia].items():
        semillas = set()
        for e in replicas:
            config = json.loads((ROOT / "reports/experimentos" / e / "config.json").read_text(encoding="utf-8"))
            if (config.get("objetivo", "precio") != OBJETIVO[familia] or h not in config["horizontes_fechas_brent"]
                    or config.get("entradas", "niveles") != ENTRADAS.get(familia, "niveles")
                    or config.get("base", "spot") != BASE.get(familia, "spot")):
                raise ValueError(f"{e} no corresponde a la familia {familia} a +{h}.")
            semillas.add(config["semilla"])
            for carpeta in sorted(glob.glob(str(ROOT / "reports/experimentos" / e / "validacion" / f"*_h{h:03d}_*"))):
                r = json.loads(Path(carpeta, "registro.json").read_text(encoding="utf-8"))
                clave = (e, r["arquitectura"], h, r["unidades"], r["corte"])
                tabla = pd.read_csv(Path(carpeta, "predicciones.csv"))
                if r["horizonte"] != h:
                    raise ValueError(f"Ajuste inesperado: {clave}")
                if clave in predicciones:
                    # Repetición idéntica (GRU +5 de E1): se conserva la primera ejecución.
                    if not np.array_equal(predicciones[clave].prediccion_red, tabla.prediccion_red):
                        raise ValueError(f"Ajuste duplicado con predicciones distintas: {clave}")
                    continue
                predicciones[clave] = tabla
                tiempos[r["arquitectura"]] = tiempos.get(r["arquitectura"], 0.0) + r["segundos_entrenamiento"]
        if len(semillas) != len(replicas):
            raise ValueError(f"{familia} +{h}: se repite una semilla.")
    if len(predicciones) != 24 * sum(len(r) for r in FAMILIAS[familia].values()):
        raise ValueError(f"{familia}: faltan ajustes.")
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


def evaluar_familia(familia, futuros):
    predicciones, tiempos = cargar(familia)
    resultados = {}
    print(f"=== {familia}: " + "; ".join(f"+{h} {', '.join(r)}" for h, r in FAMILIAS[familia].items()) + " ===")
    for a in ARQUITECTURAS:
        tamanos, anuales_sel, frente_futuros = {}, {}, {}
        for h in HORIZONTES:
            replicas = FAMILIAS[familia][h]
            medias = {}
            for u in (32, 64):
                anuales = [mejora(*promediar(predicciones, replicas, a, h, u, c)[:2]) for c in CORTES]
                medias[u] = (np.mean(anuales), anuales)
            u = 32 if medias[32][0] >= medias[64][0] else 64
            tamanos[h], anuales_sel[h] = u, medias[u][1]
            datos = {c: promediar(predicciones, replicas, a, h, u, c) for c in CORTES}
            individuales = [np.mean([mejora(datos[c][2][i], datos[c][1]) for c in CORTES])
                            for i in range(len(replicas))]
            frente_futuros[h] = []
            for c in CORTES:
                tabla = predicciones[replicas[0], a, h, u, c]
                f = futuros.reindex(tabla.fecha_origen.astype(str)).to_numpy()
                if np.isnan(f).any():
                    raise ValueError("Falta el ingenuo con futuros en un origen de validación.")
                frente_futuros[h].append(mejora(datos[c][0], np.abs(f - tabla.brent_objetivo.to_numpy())))
            print(f"{a:4s} +{h:<3d} 32: {medias[32][0]:7.2f}  64: {medias[64][0]:7.2f}  -> {u}  anuales "
                  + " / ".join(f"{x:+.2f}" for x in medias[u][1])
                  + "  | cada semilla " + " / ".join(f"{x:+.2f}" for x in individuales)
                  + f"  | frente a futuros {np.mean(frente_futuros[h]):+.2f}")
        puntuacion = np.mean(sum(anuales_sel.values(), []))
        print(f"{a:4s} frente al ingenuo con futuros: global {np.mean(sum(frente_futuros.values(), [])):+.2f} %  "
              + "  ".join(f"+{h} {np.mean(v):+.2f}" for h, v in frente_futuros.items()))
        resultados[familia, a] = dict(puntuacion=puntuacion, tamanos=tamanos, tiempo=tiempos[a],
                                      predicciones=predicciones, familia=familia)
        print(f"{a:4s} GLOBAL {puntuacion:7.2f} %  tamaños {tamanos}  pares positivos "
              f"{sum(x > 0 for x in sum(anuales_sel.values(), []))}/12  tiempo {tiempos[a]:.2f} s\n")
    return resultados


def main():
    rng = np.random.default_rng(SEMILLA)
    resultados = {}
    futuros = ingenuo_futuros()
    for familia in FAMILIAS:
        resultados.update(evaluar_familia(familia, futuros))
    candidatos = {k: v for k, v in resultados.items() if k[0] in SELECCION}
    mejor = max(candidatos, key=lambda k: candidatos[k]["puntuacion"])
    empatados = [k for k in candidatos if candidatos[mejor]["puntuacion"] - candidatos[k]["puntuacion"] <= 1]
    elegido = min(empatados, key=lambda k: candidatos[k]["tiempo"])
    print(f"Mejor puntuación: {mejor}; dentro de 1 pp: {empatados}; elegido: {elegido}")
    r = candidatos[elegido]
    for h in HORIZONTES:
        if h == max(HORIZONTES):
            continue
        u = r["tamanos"][h]
        datos = {c: promediar(r["predicciones"], FAMILIAS[r["familia"]][h], elegido[1], h, u, c)[:2] for c in CORTES}
        indices = {c: indices_bloques(rng, len(datos[c][0]), h, REPLICAS) for c in CORTES}
        muestras = np.mean([mejora(datos[c][0][indices[c]], datos[c][1][indices[c]]) for c in CORTES], axis=0)
        dm, valor_p = diebold_mariano(np.concatenate([datos[c][0] - datos[c][1] for c in CORTES]), h)
        bajo, alto = np.percentile(muestras, [2.5, 97.5])
        print(f"{elegido} promedio +{h} u{u}: IC95 [{bajo:.2f}, {alto:.2f}]  P(>0) {np.mean(muestras > 0):.3f}  "
              f"DM {dm:+.2f} (p {valor_p:.3f})")


if __name__ == "__main__":
    main()
