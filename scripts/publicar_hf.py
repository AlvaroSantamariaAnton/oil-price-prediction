"""Publicar en Hugging Face los modelos ONNX de la aplicación.

Escribe la ficha del modelo (README.md) en la carpeta exportada por scripts/export_onnx.py y la sube
completa al repositorio indicado, creándolo si no existe. El token se toma de la sesión iniciada con
`hf auth login` o de la variable de entorno HF_TOKEN; nunca se guarda en el proyecto.
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from scripts.prepare_windows import ROOT

FICHA = """---
library_name: onnx
tags:
- time-series
- forecasting
- brent
- rnn
---

# Previsión del Brent con RNN ({version})

Modelos de la aplicación del proyecto [oil-price-prediction]({repositorio}): una **{arquitectura}** de una capa
por horizonte (+5, +63 y +252 fechas del calendario del Brent), cada una con tres semillas ({semillas}).
La previsión es **base + media del cambio previsto por las tres semillas**, en USD/barril.

- **Base:** {base_descripcion}.
- **Entradas:** ventana de {ventana} fechas con 21 variables disponibles a las 09:00 de Madrid; los precios en
  variación logarítmica diaria; cada variable con valor escalado e indicador de disponibilidad.
- **Archivos:** `{arquitectura}_h<horizonte>_semilla<semilla>.onnx` (entrada `ventanas` de forma
  (lote, {ventana}, n), salida `cambio`), `escalador_h<horizonte>.json` y `config.json`.
- **Intervalo al {nivel} %:** previsión ± {margenes} USD (+5 / +63 / +252), calibrado en validación 2018–2021.
- **Entrenamiento:** datos disponibles hasta {frontera}.

## Evaluación en test (02/01/2023 en adelante, modelos del estudio)

| Horizonte | Mejora frente al último precio conocido | Frente al último precio actualizado con futuros | Cobertura del intervalo |
|---|---|---|---|
{filas}

**Limitaciones.** Las redes no superan a la regla simple que actualiza el último spot con el futuro de Brent:
su mejora frente al último precio conocido procede sobre todo de esa actualización. A +63 y +252 no hay mejora
fiable. Los intervalos tienen anchura fija en USD y cubren menos de lo nominal en periodos muy volátiles.
No es una recomendación de inversión.
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="Repositorio del modelo, p. ej. usuario/brent-rnn")
    parser.add_argument("--carpeta", default=str(ROOT / "dist/huggingface/modelo"))
    parser.add_argument("--repositorio-github", default="https://github.com/AlvaroSantamariaAnton/oil-price-prediction")
    parser.add_argument("--mensaje", help="Mensaje del commit en Hugging Face")
    a = parser.parse_args()
    carpeta = Path(a.carpeta)
    config = json.loads((carpeta / "config.json").read_text(encoding="utf-8"))
    test = pd.read_csv(ROOT / "reports/evaluacion_test.csv")
    filas = []
    for h in config["horizontes"]:
        f = test[(test.horizonte == h) & (test.predictor == config["arquitectura"])].iloc[0]
        filas.append(f"| +{h} | {f.mejora_frente_ingenuo:+.1f} % | {f.mejora_frente_futuros:+.1f} % | "
                     f"{100 * f.cobertura_intervalo:.0f} % |")
    margenes = " / ".join(f"{config['intervalo']['margenes'][str(h)]:.2f}" for h in config["horizontes"])
    (carpeta / "README.md").write_text(FICHA.format(
        version=config["version"], repositorio=a.repositorio_github, arquitectura=config["arquitectura"],
        semillas=", ".join(map(str, config["semillas"])), base_descripcion=config["base_descripcion"],
        ventana=config["ventana"], nivel=config["intervalo"]["nivel"], margenes=margenes,
        frontera=config["entrenamiento"]["frontera"], filas="\n".join(filas)), encoding="utf-8")
    from huggingface_hub import HfApi
    api = HfApi()
    api.create_repo(a.repo, repo_type="model", exist_ok=True)
    info = api.upload_folder(repo_id=a.repo, repo_type="model", folder_path=str(carpeta),
                             commit_message=a.mensaje or f"Modelos {config['version']}")
    print(info)


if __name__ == "__main__":
    main()
