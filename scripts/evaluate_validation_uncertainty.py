"""Incertidumbre de la mejora frente al ingenuo en la validación anual.

Solo lee las predicciones de validación ya guardadas; no entrena ni consulta el test.

Diseño fijado antes de calcular (10/11/2026):
- Candidatos: cada experimento y arquitectura, con los tamaños seleccionados por el protocolo
  (mayor mejora media en los cuatro cortes; empate exacto a favor de 32).
- Bootstrap circular por bloques dentro de cada año, bloques de longitud igual al horizonte,
  10.000 réplicas y semilla fija. Las mismas fechas remuestreadas para todos los candidatos
  (comparación emparejada). Estadístico: media de las cuatro mejoras anuales de un horizonte.
- A +252 un año de validación equivale aproximadamente a una sola observación independiente,
  así que no se remuestrea: solo se muestran las cuatro mejoras anuales.
- Diebold-Mariano a +5 y +63 sobre los cuatro años concatenados: diferencia de errores
  absolutos red − ingenuo, varianza de Newey-West (Bartlett, retardo h − 1), corrección de
  Harvey-Leybourne-Newbold y valor p bilateral con aproximación normal.
"""

import glob
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.prepare_windows import HORIZONTES, ROOT

CORTES = (2018, 2019, 2020, 2021)
EXPERIMENTOS = ("E1", "E2")
ARQUITECTURAS = ("RNN", "LSTM", "GRU")
REPLICAS = 10_000
SEMILLA = 20261110


def cargar(experimento):
    """Errores absolutos por fecha de cada ajuste, sin duplicados."""
    ajustes = {}
    for carpeta in sorted(glob.glob(str(ROOT / "reports/experimentos" / experimento / "validacion" / "*"))):
        r = json.loads(Path(carpeta, "registro.json").read_text(encoding="utf-8"))
        clave = (r["arquitectura"], r["horizonte"], r["unidades"], r["corte"])
        p = pd.read_csv(Path(carpeta, "predicciones.csv"))
        if clave in ajustes:
            if not np.array_equal(ajustes[clave].prediccion_red, p.prediccion_red):
                raise ValueError(f"Ajustes duplicados con predicciones distintas: {clave}")
            continue
        ajustes[clave] = p
    esperados = {(a, h, u, c) for a in ARQUITECTURAS for h in HORIZONTES for u in (32, 64) for c in CORTES}
    if set(ajustes) != esperados:
        raise ValueError(f"{experimento}: faltan o sobran ajustes.")
    return ajustes


def mejora(red, ingenuo):
    return 100 * (1 - red.mean(axis=-1) / ingenuo.mean(axis=-1))


def indices_bloques(rng, n, bloque, replicas):
    inicios = rng.integers(0, n, size=(replicas, math.ceil(n / bloque)))
    return ((inicios[:, :, None] + np.arange(bloque)) % n).reshape(replicas, -1)[:, :n]


def diebold_mariano(d, h):
    n = len(d)
    centrada = d - d.mean()
    varianza = centrada @ centrada / n
    for k in range(1, h):
        varianza += 2 * (1 - k / h) * (centrada[k:] @ centrada[:-k]) / n
    estadistico = d.mean() / math.sqrt(varianza / n)
    estadistico *= math.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    return estadistico, math.erfc(abs(estadistico) / math.sqrt(2))


def main():
    rng = np.random.default_rng(SEMILLA)
    candidatos = {}
    for e in EXPERIMENTOS:
        ajustes = cargar(e)
        for a in ARQUITECTURAS:
            for h in HORIZONTES:
                medias = {u: np.mean([mejora(ajustes[a, h, u, c].error_absoluto_red.to_numpy(),
                                             ajustes[a, h, u, c].error_absoluto_ingenuo.to_numpy()) for c in CORTES])
                          for u in (32, 64)}
                u = 32 if medias[32] >= medias[64] else 64
                candidatos[e, a, h] = (u, {c: ajustes[a, h, u, c] for c in CORTES})
    nombres = [(e, a) for e in EXPERIMENTOS for a in ARQUITECTURAS]
    for h in HORIZONTES:
        print(f"\n=== Horizonte +{h} ===")
        base = candidatos["E2", "LSTM", h][1]
        for c in CORTES:
            for e, a in nombres:
                p = candidatos[e, a, h][1][c]
                if not p.fecha_origen.equals(base[c].fecha_origen):
                    raise ValueError("Los candidatos no comparten fechas de validación.")
        if h == max(HORIZONTES):
            for e, a in nombres:
                u, ps = candidatos[e, a, h]
                anuales = [mejora(ps[c].error_absoluto_red.to_numpy(), ps[c].error_absoluto_ingenuo.to_numpy()) for c in CORTES]
                print(f"{e} {a:4s} u{u}: media {np.mean(anuales):7.2f} %  anuales " + " / ".join(f"{x:+.2f}" for x in anuales))
            print("Sin bootstrap: cada año aporta aproximadamente una observación independiente a este horizonte.")
            continue
        indices = {c: indices_bloques(rng, len(base[c]), h, REPLICAS) for c in CORTES}
        replicas = {}
        for e, a in nombres:
            u, ps = candidatos[e, a, h]
            anuales = [mejora(ps[c].error_absoluto_red.to_numpy()[indices[c]],
                              ps[c].error_absoluto_ingenuo.to_numpy()[indices[c]]) for c in CORTES]
            replicas[e, a] = np.mean(anuales, axis=0)
            puntual = np.mean([mejora(ps[c].error_absoluto_red.to_numpy(), ps[c].error_absoluto_ingenuo.to_numpy()) for c in CORTES])
            d = np.concatenate([(ps[c].error_absoluto_red - ps[c].error_absoluto_ingenuo).to_numpy() for c in CORTES])
            dm, valor_p = diebold_mariano(d, h)
            bajo, alto = np.percentile(replicas[e, a], [2.5, 97.5])
            print(f"{e} {a:4s} u{u}: mejora {puntual:7.2f} %  IC95 [{bajo:7.2f}, {alto:7.2f}]  "
                  f"P(>0) {np.mean(replicas[e, a] > 0):.3f}  DM {dm:+.2f} (p {valor_p:.3f})")
        for e, a in nombres:
            if (e, a) == ("E2", "LSTM"):
                continue
            dif = replicas["E2", "LSTM"] - replicas[e, a]
            bajo, alto = np.percentile(dif, [2.5, 97.5])
            print(f"  E2 LSTM - {e} {a:4s}: IC95 [{bajo:7.2f}, {alto:7.2f}]  P(>0) {np.mean(dif > 0):.3f}")


if __name__ == "__main__":
    main()
