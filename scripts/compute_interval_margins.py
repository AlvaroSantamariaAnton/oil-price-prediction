"""Márgenes de los intervalos al 80 % con la validación de la familia seleccionada.

Para cada arquitectura y horizonte se usa el tamaño elegido por la regla del promedio de semillas
en la familia `variaciones` (E11–E13). El margen es el percentil 80 de los errores absolutos de la
predicción promediada en los cuatro años de validación. El intervalo de una predicción es
precio previsto ± margen, en USD/barril. Solo lee validación; no entrena ni consulta el test.
"""

import json

import numpy as np

from scripts.evaluate_seed_ensemble import FAMILIAS, cargar, promediar
from scripts.evaluate_validation_uncertainty import ARQUITECTURAS, CORTES, mejora
from scripts.prepare_windows import HORIZONTES, ROOT

FAMILIA = "variaciones"
NIVEL = 80
DESTINO = ROOT / "reports" / "margenes_validacion.json"


def main():
    predicciones, _ = cargar(FAMILIA)
    salida = {"familia": FAMILIA, "replicas": {str(h): list(r) for h, r in FAMILIAS[FAMILIA].items()},
              "nivel": NIVEL, "unidad": "USD/barril", "margenes": {}}
    for a in ARQUITECTURAS:
        for h in HORIZONTES:
            replicas = FAMILIAS[FAMILIA][h]
            medias = {u: np.mean([mejora(*promediar(predicciones, replicas, a, h, u, c)[:2]) for c in CORTES])
                      for u in (32, 64)}
            u = 32 if medias[32] >= medias[64] else 64
            errores = {c: promediar(predicciones, replicas, a, h, u, c)[0] for c in CORTES}
            ingenuo = np.concatenate([promediar(predicciones, replicas, a, h, u, c)[1] for c in CORTES])
            todos = np.concatenate(list(errores.values()))
            margen = float(np.percentile(todos, NIVEL))
            cobertura = {c: float(np.mean(errores[c] <= margen)) for c in CORTES}
            salida["margenes"][f"{a}_h{h:03d}"] = dict(
                arquitectura=a, horizonte=h, unidades=u, margen=margen, n=len(todos),
                cobertura_por_corte=cobertura, margen_ingenuo=float(np.percentile(ingenuo, NIVEL)))
            print(f"{a:4s} +{h:<3d} u{u}: margen {margen:6.2f} USD (n {len(todos)})  ingenuo {np.percentile(ingenuo, NIVEL):6.2f}"
                  "  cobertura por año " + " / ".join(f"{100 * x:.0f}%" for x in cobertura.values()))
    DESTINO.write_text(json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8")
    print(DESTINO)


if __name__ == "__main__":
    main()
