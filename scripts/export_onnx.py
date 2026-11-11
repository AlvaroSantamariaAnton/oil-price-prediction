"""Exportar los modelos de la arquitectura seleccionada a ONNX para la aplicación.

Lee los ajustes finales de reports/experimentos/final/ (arquitectura seleccionada, tres horizontes,
tres semillas) y escribe en dist/huggingface/modelo/ todo lo que la aplicación necesita para
predecir sin PyTorch:
- <arquitectura>_h<horizonte>_semilla<semilla>.onnx: entrada `ventanas` (lote, 60, n_entradas)
  escalada; salida `cambio` (lote,) en USD/barril respecto a la base;
- escalador_h<horizonte>.json: medias, divisores y orden de entradas del ajuste final;
- config.json: horizontes, ventana, transformación de entradas, base, semillas, márgenes del
  intervalo al 80 %, fechas de entrenamiento y procedencia (commit y registros).
La predicción de precio es base + media de las tres semillas. dist/ está ignorado por Git.
"""

import glob
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import torch

from scripts.prepare_scalers import VARIABLES_PRECIO
from scripts.prepare_windows import ROOT, SNAPSHOT, VENTANA
from src.oil_price_prediction.train_validation import Regresor

FINAL = ROOT / "reports/experimentos/final"
DESTINO = ROOT / "dist/huggingface/modelo"
VERSION = "estudio-2023-01-02"


def main():
    config = json.loads((FINAL / "config.json").read_text(encoding="utf-8"))
    arquitectura = config["seleccionada"]
    margenes = json.loads((ROOT / "reports/margenes_validacion.json").read_text(encoding="utf-8"))
    if margenes["familia"] != "futuros":
        raise ValueError("Los márgenes no corresponden a la familia seleccionada.")
    if DESTINO.exists():
        shutil.rmtree(DESTINO)
    DESTINO.mkdir(parents=True)
    modelos, escaladores = [], {}
    with ZipFile(ROOT / "data/processed" / SNAPSHOT / config["ajuste_final"]["escalado"]) as z:
        for h in config["horizontes_fechas_brent"]:
            escaladores[h] = json.loads(z.read(f"2023/h{h:03d}/escalador.json"))
    for h in config["horizontes_fechas_brent"]:
        e = escaladores[h]
        (DESTINO / f"escalador_h{h:03d}.json").write_text(json.dumps(
            {k: e[k] for k in ("orden_entradas", "media", "divisor", "entradas", "variables_en_variacion")}, indent=2),
            encoding="utf-8")
        unidades = config["unidades"][arquitectura][str(h)]
        for semilla in config["semillas"]:
            carpetas = glob.glob(str(FINAL / f"*_{arquitectura}_h{h:03d}_u{unidades:03d}_semilla{semilla}"))
            if len(carpetas) != 1:
                raise ValueError(f"Se esperaba un ajuste final para {arquitectura} +{h} semilla {semilla}.")
            carpeta = Path(carpetas[0])
            registro = json.loads((carpeta / "registro.json").read_text(encoding="utf-8"))
            if json.loads((carpeta / "escalador.json").read_text(encoding="utf-8")) != escaladores[h]:
                raise ValueError(f"El escalador de {carpeta.name} difiere del escalado final.")
            modelo = Regresor(arquitectura, len(escaladores[h]["orden_entradas"]), unidades)
            modelo.load_state_dict(torch.load(carpeta / "modelo.pt", map_location="cpu"))
            modelo.eval()
            nombre = f"{arquitectura}_h{h:03d}_semilla{semilla}.onnx"
            ejemplo = torch.zeros(2, VENTANA, len(escaladores[h]["orden_entradas"]))
            torch.onnx.export(modelo, (ejemplo,), DESTINO / nombre, input_names=["ventanas"], output_names=["cambio"],
                              dynamic_axes={"ventanas": {0: "lote"}, "cambio": {0: "lote"}}, opset_version=17,
                              dynamo=False)
            modelos.append(dict(archivo=nombre, horizonte=h, semilla=semilla, unidades=unidades,
                                parametros=registro["parametros"], registro=str(carpeta.relative_to(ROOT).as_posix()),
                                sha256=hashlib.sha256((DESTINO / nombre).read_bytes()).hexdigest()))
    final_registro = json.loads(Path(glob.glob(str(FINAL / "*" / "registro.json"))[0]).read_text(encoding="utf-8"))
    tramos = {}
    for m in modelos:
        r = json.loads((ROOT / m["registro"] / "registro.json").read_text(encoding="utf-8"))
        tramos.setdefault(str(m["horizonte"]), r["tramos"])
    salida = {
        "version": VERSION, "arquitectura": arquitectura, "horizontes": config["horizontes_fechas_brent"],
        "ventana": VENTANA, "objetivo": config["objetivo"], "base": config["base"], "entradas": config["entradas"],
        "variables_en_variacion": VARIABLES_PRECIO, "semillas": config["semillas"],
        "prediccion": "precio = base + media de las salidas de las tres semillas (USD/barril)",
        "base_descripcion": ("último Brent spot admisible × cierre admisible del futuro de Brent en el origen / "
                             "último cierre del futuro observado en o antes de la fecha de ese spot; si no hay futuro, el spot"),
        "intervalo": {"nivel": margenes["nivel"], "unidad": "USD/barril",
                      "margenes": {str(m["horizonte"]): m["margen"] for m in margenes["margenes"].values()
                                   if m["arquitectura"] == arquitectura},
                      "origen": "percentil 80 del error absoluto de la media de semillas en validación 2018–2021"},
        "entrenamiento": {"frontera": config["ajuste_final"]["frontera"], "snapshot": SNAPSHOT, "tramos": tramos,
                          "commit": final_registro["commit"]},
        "commit_exportacion": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "modelos": modelos,
    }
    (DESTINO / "config.json").write_text(json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{len(modelos)} modelos exportados en {DESTINO}")


if __name__ == "__main__":
    main()
