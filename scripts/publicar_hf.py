"""Publicar en Hugging Face los modelos ONNX de la aplicación.

Escribe la ficha del modelo (README.md) en la carpeta exportada por scripts/export_onnx.py y la sube
completa al repositorio indicado, creándolo si no existe. Antes de subir, etiqueta la versión que haya
publicada (si aún no tiene etiqueta) y, después, la nueva: cada versión queda accesible por su nombre
(p. ej. `revision="estudio-2023-01-02"`). Para una carpeta de src/oil_price_prediction/reentrenar.py,
la ficha indica que la versión no tiene test propio y resume su comprobación de cordura. El token se toma de la sesión iniciada con
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
- **Entrenamiento:** fecha de corte {frontera} (solo precios ya publicados ese día). Orígenes de las ventanas:
{tramos}
{reentreno}
## Evaluación en test (02/01/2023 en adelante, modelos del estudio)

| Horizonte | Mejora frente al último precio conocido | Frente al último precio actualizado con futuros | Cobertura del intervalo |
|---|---|---|---|
{filas}

**Limitaciones.** Las redes no superan a la regla simple que actualiza el último spot con el futuro de Brent:
su mejora frente al último precio conocido procede sobre todo de esa actualización. A +63 y +252 no hay mejora
fiable. Los intervalos tienen anchura fija en USD y cubren menos de lo nominal en periodos muy volátiles.
No es una recomendación de inversión.
"""

REENTRENO = """
## Versión reentrenada

Pesos nuevos con el {metodo}. **No tiene test propio:** la tabla de abajo es la del test de la versión
{estudio} y mide la fiabilidad del método, no de estos pesos. Las versiones anteriores siguen disponibles
como etiquetas del repositorio.

Comprobación de cordura, **no evaluación**: error absoluto medio (USD/barril) en el tramo de parada temprana,
que sirvió para elegir la época y se solapa con el test del estudio.

| Horizonte | Orígenes | Red (media de semillas) | Ingenuo con futuros |
|---|---|---|---|
{filas}
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
    tramos = "\n".join(f"  - +{h}: aprendizaje hasta {t['aprendizaje']['fin']}; parada temprana (último 15 %) "
                       f"hasta {t['interno']['fin']}" for h, t in config["entrenamiento"]["tramos"].items())
    reentreno = ""
    cordura = config.get("comprobacion_cordura")
    if cordura:
        filas_cordura = "\n".join(
            f"| +{h} | {t['inicio']} a {t['fin']} | {t['mae_red_media_semillas']:.2f} | {t['mae_ingenuo_con_futuros']:.2f} |"
            for h, t in cordura["tramo_interno"].items())
        reentreno = REENTRENO.format(metodo=config["entrenamiento"]["metodo"], estudio=config["evaluacion_test"]["version_evaluada"],
                                     filas=filas_cordura)
    (carpeta / "README.md").write_text(FICHA.format(
        version=config["version"], repositorio=a.repositorio_github, arquitectura=config["arquitectura"],
        semillas=", ".join(map(str, config["semillas"])), base_descripcion=config["base_descripcion"],
        ventana=config["ventana"], nivel=config["intervalo"]["nivel"], margenes=margenes,
        frontera=config["entrenamiento"]["frontera"], tramos=tramos, reentreno=reentreno,
        filas="\n".join(filas)), encoding="utf-8")
    from huggingface_hub import HfApi, hf_hub_download
    api = HfApi()
    if api.repo_exists(a.repo, repo_type="model"):
        # Etiqueta la versión publicada ahora (si aún no lo está) antes de sustituirla.
        actual = json.loads(Path(hf_hub_download(a.repo, "config.json", repo_type="model")).read_text(encoding="utf-8"))
        etiquetar(api, a.repo, actual["version"], api.model_info(a.repo).sha)
    else:
        api.create_repo(a.repo, repo_type="model")
    info = api.upload_folder(repo_id=a.repo, repo_type="model", folder_path=str(carpeta),
                             commit_message=a.mensaje or f"Modelos {config['version']}")
    print(info)
    etiquetar(api, a.repo, config["version"], info.oid)


def etiquetar(api, repo, version, revision):
    etiquetas = {t.name for t in api.list_repo_refs(repo, repo_type="model").tags}
    if version in etiquetas:
        print(f"La etiqueta {version} ya existe; no se cambia.")
        return
    api.create_tag(repo, tag=version, revision=revision, repo_type="model", tag_message=f"Modelos {version}")
    print(f"Etiqueta {version} → {revision}")


if __name__ == "__main__":
    main()
