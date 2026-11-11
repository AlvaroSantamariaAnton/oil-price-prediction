"""Entrenar un ajuste final (corte 2023) y guardar sus predicciones de test sin calcular métricas.

Lee la configuración única de reports/experimentos/final/config.json (familia E14–E16 con las tres
semillas y los tamaños seleccionados en validación) y guarda cada ajuste en
reports/experimentos/final/<id>/. La evaluación del test se hace después, una sola vez, con un
script aparte.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch

from scripts.prepare_windows import ROOT, SNAPSHOT, VENTANA
from src.oil_price_prediction.train_validation import (BASES, ESCALADOS_FINAL, REDES, Regresor, a_precio, ajustar,
                                                      cargar_datos, predecir, tasa_del_horizonte)

CARPETA = ROOT / "reports/experimentos/final"
CORTE = 2023
# Campos que deben coincidir con la configuración de cada réplica de validación (E14–E16).
COMUNES = ["objetivo", "entradas", "base", "snapshot", "biblioteca", "dispositivo", "ventana_fechas_brent",
           "horizontes_fechas_brent", "arquitecturas", "capas_recurrentes", "parada_temprana", "escalado",
           "perdida", "optimizador", "tasa_aprendizaje", "tamano_lote"]


def leer_configuracion():
    c = json.loads((CARPETA / "config.json").read_text(encoding="utf-8"))
    familia = [json.loads((ROOT / "reports/experimentos" / e / "config.json").read_text(encoding="utf-8"))
               for e in c["familia_validacion"]]
    for f in familia:
        distintos = [k for k in COMUNES if f.get(k) != c.get(k)]
        if distintos:
            raise ValueError(f"La configuración final difiere de {f['experimento']} en {distintos}.")
    if sorted(f["semilla"] for f in familia) != sorted(c["semillas"]):
        raise ValueError("Las semillas finales no coinciden con las de la familia de validación.")
    compatibles = {"snapshot": SNAPSHOT, "ventana_fechas_brent": VENTANA, "biblioteca": "pytorch", "dispositivo": "cuda",
                   "capas_recurrentes": 1, "perdida": "MAE", "optimizador": "Adam",
                   "escalado": "estandarizacion_por_variable"}
    if any(c[k] != v for k, v in compatibles.items()) or c["base"] not in BASES or c["entradas"] not in ESCALADOS_FINAL:
        raise ValueError("Configuración incompatible con el modelo o los datos preparados.")
    if c["ajuste_final"]["escalado"] != ESCALADOS_FINAL[c["entradas"]]:
        raise ValueError("El escalado final no corresponde al tipo de entradas.")
    return c


def main():
    c = leer_configuracion()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arquitectura", required=True, choices=REDES)
    parser.add_argument("--horizonte", required=True, type=int, choices=c["horizontes_fechas_brent"])
    parser.add_argument("--semilla", required=True, type=int, choices=c["semillas"])
    a = parser.parse_args()
    if not torch.cuda.is_available():
        parser.error("Se requiere CUDA disponible.")
    unidades = c["unidades"][a.arquitectura][str(a.horizonte)]
    tasa = tasa_del_horizonte(c["tasa_aprendizaje"], a.horizonte)
    existentes = list(CARPETA.glob(f"*_{a.arquitectura}_h{a.horizonte:03d}_u{unidades:03d}_semilla{a.semilla}"))
    if existentes:
        parser.error(f"Ese ajuste final ya existe: {existentes[0].name}")
    protocolo = (ROOT / c["protocolo"]).read_bytes()
    datos, fechas, test, escalador, bases = cargar_datos(CORTE, a.horizonte, c["objetivo"], c["entradas"], c["base"],
                                                         fase="final")
    bases_tramo = {k: torch.from_numpy(v).cuda() for k, v in bases.items()}
    instante = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    identificador = f"{instante}_{a.arquitectura}_h{a.horizonte:03d}_u{unidades:03d}_semilla{a.semilla}"
    torch.manual_seed(a.semilla)
    modelo = Regresor(a.arquitectura, len(escalador["orden_entradas"]), unidades).cuda()
    datos = {k: (x.cuda(), y.cuda()) for k, (x, y) in datos.items()}
    historial, mejor, segundos = ajustar(modelo, datos, dict(c, tasa_aprendizaje=tasa), c["objetivo"], bases_tramo)
    salida = predecir(modelo, datos["test"][0], c["tamano_lote"]).cpu().numpy()
    test["prediccion_red"] = a_precio(salida, bases["test"], c["objetivo"]) if c["objetivo"] == "porcentaje" \
        else salida + bases["test"]
    if not np.isfinite(test.prediccion_red).all():
        raise ValueError("Predicción de test no finita.")
    registro = dict(id=identificador, fase="final", snapshot=SNAPSHOT, objetivo=c["objetivo"], entradas=c["entradas"],
                    base=c["base"], tasa_aprendizaje=tasa, arquitectura=a.arquitectura, unidades=unidades,
                    horizonte=a.horizonte, corte=CORTE, semilla=a.semilla, configuracion="../config.json",
                    parametros=sum(p.numel() for p in modelo.parameters()), mejor_epoca=mejor,
                    epocas=int(len(historial)), mae_interno_minimo=float(historial.mae_interno.min()),
                    segundos_entrenamiento=segundos, origenes_test=int(len(test)),
                    python=platform.python_version(), torch=torch.__version__, cuda=torch.version.cuda,
                    cudnn=torch.backends.cudnn.version(), dispositivo=torch.cuda.get_device_name(),
                    script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    protocolo_sha256=hashlib.sha256(protocolo).hexdigest(),
                    commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                    tramos={k: dict(n=len(f), inicio=f.fecha_origen.min(), fin=f.fecha_origen.max())
                            for k, f in fechas.items()},
                    pesos="modelo.pt", escalador="escalador.json", predicciones="predicciones_test.csv")
    with tempfile.TemporaryDirectory(dir=CARPETA) as tmp:
        carpeta = Path(tmp) / identificador
        carpeta.mkdir()
        for nombre, contenido in [("registro", registro), ("escalador", escalador)]:
            (carpeta / f"{nombre}.json").write_text(json.dumps(contenido, indent=2, allow_nan=False), encoding="utf-8")
        torch.save(modelo.cpu().state_dict(), carpeta / "modelo.pt")
        historial.to_csv(carpeta / "epocas.csv", index=False)
        test.to_csv(carpeta / "predicciones_test.csv")
        ax = historial.plot(x="epoca", y=["mae_aprendizaje", "mae_interno"], xlabel="Época", ylabel="MAE (USD/barril)")
        ax.axvline(mejor, linestyle="--", color="gray", label="Mejor época")
        ax.legend()
        ax.figure.savefig(carpeta / "curvas.png", bbox_inches="tight")
        plt.close(ax.figure)
        carpeta.rename(CARPETA / identificador)
    # Solo información del entrenamiento: ninguna métrica de test.
    print(f"Mejor época {mejor} de {len(historial)}; MAE interno {historial.mae_interno.min():.4f}; {len(test)} predicciones de test")
    print(CARPETA / identificador)


if __name__ == "__main__":
    main()
