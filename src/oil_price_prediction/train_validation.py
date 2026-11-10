"""Entrenar un único ajuste de validación del experimento configurado."""

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tempfile
from time import perf_counter
from zipfile import ZipFile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from torch import nn

from scripts.prepare_windows import ROOT, SNAPSHOT, VENTANA


REDES = {"RNN": nn.RNN, "LSTM": nn.LSTM, "GRU": nn.GRU}
# precio: la red predice el Brent objetivo (E1; también si el campo falta).
# cambio: predice objetivo − último Brent admisible en el origen y se le suma ese Brent.
OBJETIVOS = ("precio", "cambio")


class Regresor(nn.Module):
    def __init__(self, arquitectura, entradas, unidades):
        super().__init__()
        self.recurrente = REDES[arquitectura](entradas, unidades, batch_first=True)
        self.salida = nn.Linear(unidades, 1)

    def forward(self, ventanas):
        secuencia, _ = self.recurrente(ventanas)
        return self.salida(secuencia[:, -1]).squeeze(-1)


def cargar_datos(corte, h, objetivo):
    carpeta = ROOT / "data/processed" / SNAPSHOT
    with ZipFile(carpeta / "escalado_validacion.zip") as z:
        base = f"{corte}/h{h:03d}/"
        escalador = json.loads(z.read(base + "escalador.json"))
        with z.open(base + "entradas.csv") as archivo:
            entradas = pd.read_csv(archivo, index_col="fila_diaria")
    if (escalador["snapshot"], escalador["corte"], escalador["horizonte"]) != (SNAPSHOT, corte, h):
        raise ValueError("El escalador pertenece a otro ajuste.")
    valores = entradas[escalador["orden_entradas"]].to_numpy(dtype="float32")
    particiones = pd.read_csv(carpeta / "particiones_validacion.csv")
    particiones = particiones.loc[(particiones.corte == corte) & (particiones.horizonte == h)]
    ventanas = pd.read_csv(carpeta / "ventanas_objetivos.csv")
    muestras = particiones.merge(ventanas.loc[ventanas.horizonte == h], on=["horizonte", "fecha_origen"],
                                 how="left", validate="one_to_one").sort_values("fecha_origen")
    if objetivo == "cambio":
        diario = pd.read_csv(carpeta / "entradas_diarias.csv", usecols=["fecha", "brent", "brent_disponible"])
        muestras = muestras.merge(diario.rename(columns={"fecha": "fecha_origen", "brent_disponible": "base_disponible"}),
                                  on="fecha_origen", how="left", validate="many_to_one")
        if not muestras.base_disponible.eq(muestras.brent_disponible).all():
            raise ValueError("La disponibilidad del Brent difiere entre particiones y entradas diarias.")
        # Sin Brent admisible en el origen no hay cambio definido: solo puede faltar en aprendizaje.
        sin_base = muestras.brent_disponible.ne(1)
        if (sin_base & muestras.tramo.ne("aprendizaje")).any():
            raise ValueError("Falta el Brent admisible en un origen interno o de validación.")
        muestras = muestras.loc[~sin_base]
        if not np.isfinite(muestras.brent).all():
            raise ValueError("Brent admisible no finito en el origen.")
    tensores, fechas, bases = {}, {}, {}
    for tramo in ("aprendizaje", "interno", "validacion"):
        filas = muestras.loc[muestras.tramo == tramo]
        if filas.empty or filas.fila_origen.isna().any():
            raise ValueError(f"Faltan ventanas en {tramo}.")
        base = (filas.brent if objetivo == "cambio" else pd.Series(0.0, index=filas.index)).to_numpy(dtype="float32")
        ids = filas.fila_inicio.to_numpy()[:, None] + np.arange(VENTANA)
        posiciones = entradas.index.get_indexer(ids.ravel()).reshape(ids.shape)
        if (posiciones < 0).any() or not np.array_equal(ids[:, -1], filas.fila_origen):
            raise ValueError(f"Ventana incompleta en {tramo}.")
        y = torch.tensor(filas.brent_objetivo.to_numpy(), dtype=torch.float32)
        if objetivo == "cambio":
            y = y - torch.from_numpy(base)
        tensores[tramo] = (torch.from_numpy(valores[posiciones]), y)
        fechas[tramo], bases[tramo] = filas, base
    with ZipFile(carpeta / "referencia_ingenua_validacion.zip") as z:
        with z.open("predicciones.csv") as archivo:
            referencia = pd.read_csv(archivo)
    anual = fechas["validacion"].set_index("fecha_origen")
    ref = referencia.loc[(referencia.corte == corte) & (referencia.horizonte == h)].set_index("fecha_origen").sort_index()
    if not anual.index.equals(ref.index) or not np.array_equal(anual.brent_objetivo, ref.brent_objetivo):
        raise ValueError("Las muestras de validación difieren de la referencia ingenua.")
    if objetivo == "cambio" and not np.array_equal(bases["validacion"], ref.prediccion_ingenua.to_numpy(dtype="float32")):
        raise ValueError("El Brent base difiere de la predicción ingenua.")
    return tensores, fechas, ref.copy(), escalador, bases["validacion"]


@torch.inference_mode()
def predecir(modelo, entradas, lote):
    modelo.eval()
    return torch.cat([modelo(x) for x in entradas.split(lote)])


def ajustar(modelo, datos, config):
    regla = config["parada_temprana"]
    lote = config["tamano_lote"]
    optimizador = torch.optim.Adam(modelo.parameters(), lr=config["tasa_aprendizaje"])
    x, y = datos["aprendizaje"]
    xi, yi = datos["interno"]
    historial = []
    minimo = float("inf")
    torch.cuda.synchronize()
    inicio = perf_counter()
    for epoca in range(1, regla["max_epocas"] + 1):
        modelo.train()
        for indices in torch.randperm(len(y), device=y.device).split(lote):
            optimizador.zero_grad(set_to_none=True)
            perdida = nn.functional.l1_loss(modelo(x[indices]), y[indices])
            perdida.backward()
            optimizador.step()
        mae = nn.functional.l1_loss(predecir(modelo, x, lote), y).item()
        interno = nn.functional.l1_loss(predecir(modelo, xi, lote), yi).item()
        if not np.isfinite([mae, interno]).all():
            raise ValueError("MAE no finito durante el entrenamiento.")
        historial.append((epoca, mae, interno))
        if interno < minimo:
            minimo, mejor = interno, epoca
            pesos = copy.deepcopy(modelo.state_dict())
        if epoca - mejor >= regla["paciencia_epocas"]:
            break
    torch.cuda.synchronize()
    segundos = perf_counter() - inicio
    modelo.load_state_dict(pesos)
    return pd.DataFrame(historial, columns=["epoca", "mae_aprendizaje", "mae_interno"]), mejor, segundos


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arquitectura", required=True, choices=REDES)
    parser.add_argument("--unidades", required=True, type=int)
    parser.add_argument("--horizonte", required=True, type=int)
    parser.add_argument("--corte", required=True, type=int)
    a = parser.parse_args()
    plantilla = (ROOT / "configs/config.json").read_bytes()
    c = json.loads(plantilla)
    for valor, opciones in [(a.arquitectura, c["arquitecturas"]), (a.unidades, c["unidades_recurrentes"]),
                            (a.horizonte, c["horizontes_fechas_brent"]), (a.corte, c["validacion"]["anios_de_prediccion"])]:
        if valor not in opciones:
            parser.error(f"{valor} no figura en la configuración.")
    compatibles = {"snapshot": SNAPSHOT, "ventana_fechas_brent": VENTANA, "biblioteca": "pytorch",
                   "dispositivo": "cuda", "capas_recurrentes": 1, "perdida": "MAE", "optimizador": "Adam",
                   "escalado": "estandarizacion_por_variable"}
    if any(c[k] != v for k, v in compatibles.items()):
        parser.error("Configuración incompatible con el modelo o los datos preparados.")
    regla = c["parada_temprana"]
    if (c["validacion"]["tipo"] != "entrenamiento_creciente" or c["validacion"]["primer_anio_entrenamiento"] != 2000
            or regla["fraccion_final_cronologica"] != 0.15 or regla["metrica"] != "mae_interno_usd_barril"
            or regla["recuperar_mejores_pesos"] is not True or regla["max_epocas"] < 1
            or regla["paciencia_epocas"] < 1 or c["tamano_lote"] < 1 or c["tasa_aprendizaje"] <= 0):
        parser.error("Revisar validación, parada temprana o parámetros de optimización.")
    if not re.fullmatch(r"E[0-9]+", c["experimento"] or "") or not torch.cuda.is_available():
        parser.error("Se requiere un nombre de experimento E<n> y CUDA disponible.")
    objetivo = c.get("objetivo", "precio")
    if objetivo not in OBJETIVOS:
        parser.error(f"objetivo debe ser uno de {OBJETIVOS}.")
    protocolo = (ROOT / c["protocolo"]).read_bytes()
    datos, fechas, ref, escalador, brent_base = cargar_datos(a.corte, a.horizonte, objetivo)
    experimento = ROOT / "reports/experimentos" / c["experimento"]
    base = experimento / "validacion"
    base.mkdir(parents=True, exist_ok=True)
    copia = experimento / "config.json"
    with tempfile.TemporaryDirectory(dir=experimento) as tmp:
        preparado = Path(tmp) / "config.json"
        preparado.write_bytes(plantilla)
        try:
            os.link(preparado, copia)
        except FileExistsError:
            if json.loads(copia.read_bytes()) != c:
                parser.error("El experimento ya contiene otra configuración. Elige otro nombre.")
    instante = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    identificador = f"{instante}_{a.arquitectura}_h{a.horizonte:03d}_u{a.unidades:03d}_corte{a.corte}"
    destino = base / identificador
    torch.manual_seed(c["semilla"])
    modelo = Regresor(a.arquitectura, len(escalador["orden_entradas"]), a.unidades).cuda()
    datos = {k: (x.cuda(), y.cuda()) for k, (x, y) in datos.items()}
    historial, mejor, segundos = ajustar(modelo, datos, c)
    ref["prediccion_red"] = predecir(modelo, datos["validacion"][0], c["tamano_lote"]).cpu().numpy() + brent_base
    error = ref.prediccion_red - ref.brent_objetivo
    mae, mse = float(error.abs().mean()), float((error ** 2).mean())
    ingenuo = float((ref.prediccion_ingenua - ref.brent_objetivo).abs().mean())
    registro = dict(id=identificador, snapshot=SNAPSHOT, objetivo=objetivo, arquitectura=a.arquitectura, unidades=a.unidades,
                    horizonte=a.horizonte, corte=a.corte, configuracion="../../config.json",
                    parametros=sum(p.numel() for p in modelo.parameters()), mejor_epoca=mejor,
                    segundos_entrenamiento=segundos, mae=mae, mse=mse, rmse=mse**0.5, mae_ingenuo=ingenuo,
                    mejora_porcentual=100*(1-mae/ingenuo), python=platform.python_version(),
                    torch=torch.__version__, cuda=torch.version.cuda, cudnn=torch.backends.cudnn.version(),
                    dispositivo=torch.cuda.get_device_name(), script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    protocolo_sha256=hashlib.sha256(protocolo).hexdigest(),
                    commit=subprocess.check_output(["git","rev-parse","HEAD"], cwd=ROOT, text=True).strip(),
                    tramos={k: dict(n=len(f), inicio=f.fecha_origen.min(), fin=f.fecha_origen.max()) for k,f in fechas.items()},
                    pesos="modelo.pt", escalador="escalador.json", predicciones="predicciones.csv")
    with tempfile.TemporaryDirectory(dir=base) as tmp:
        carpeta = Path(tmp) / identificador
        carpeta.mkdir()
        for nombre, contenido in [("registro", registro), ("escalador", escalador)]:
            (carpeta / f"{nombre}.json").write_text(json.dumps(contenido, indent=2, allow_nan=False), encoding="utf-8")
        torch.save(modelo.cpu().state_dict(), carpeta / "modelo.pt")
        historial.to_csv(carpeta / "epocas.csv", index=False)
        ref.rename(columns={"error_absoluto":"error_absoluto_ingenuo"}).assign(error_absoluto_red=error.abs()).to_csv(carpeta / "predicciones.csv")
        ax = historial.plot(x="epoca", y=["mae_aprendizaje","mae_interno"], xlabel="Época", ylabel="MAE (USD/barril)")
        ax.axvline(mejor, linestyle="--", color="gray", label="Mejor época")
        ax.legend()
        ax.figure.savefig(carpeta / "curvas.png", bbox_inches="tight")
        plt.close(ax.figure)
        carpeta.rename(destino)
    print(f"Mejor época {mejor}; MAE red {mae:.4f}; MAE ingenuo {ingenuo:.4f}; mejora {registro['mejora_porcentual']:.2f} %")
    print(destino)


if __name__ == "__main__":
    main()
