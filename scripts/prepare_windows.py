"""Indexar ventanas de entradas y etiquetas spot del protocolo de comparación."""

import json
import os
import tempfile
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = "20261106T142300_705279Z_all"
VENTANA = 60
HORIZONTES = (5, 63, 252)


def preparar_indice(brent, fechas):
    if not fechas.equals(brent.index) or fechas.has_duplicates or fechas.hasnans:
        raise ValueError("El calendario diario debe coincidir exactamente con el índice Brent.")
    if not fechas.is_monotonic_increasing or len(fechas) < VENTANA + max(HORIZONTES):
        raise ValueError("El calendario debe estar ordenado y cubrir los tres horizontes.")

    grupos = []
    for horizonte in HORIZONTES:
        # Posiciones base cero: la ventana incluye la fila del origen.
        origen = pd.RangeIndex(VENTANA - 1, len(fechas) - horizonte)
        inicio = origen - (VENTANA - 1)
        objetivo = origen + horizonte
        fechas_objetivo = fechas.take(objetivo)
        grupo = pd.DataFrame({
            "fila_inicio": inicio,
            "fila_origen": origen,
            "fecha_inicio": fechas.take(inicio),
            "fecha_origen": fechas.take(origen),
            "horizonte": horizonte,
            "fecha_objetivo": fechas_objetivo,
            "brent_objetivo": brent.iloc[objetivo].to_numpy(),
            "etiqueta_disponible_desde": fechas_objetivo + pd.offsets.BDay(7),
        })
        validas = grupo.dropna(subset=["brent_objetivo"])
        grupos.append(validas)
        print(f"Horizonte {horizonte}: {len(validas)} muestras; "
              f"{len(grupo) - len(validas)} sin precio en la fecha exacta; "
              f"{horizonte} orígenes finales fuera de alcance.")
        print(validas.head(1).to_string(index=False))
    return pd.concat(grupos, ignore_index=True)


def main():
    paquete = ROOT / "data/raw" / SNAPSHOT
    carpeta = ROOT / "data/processed" / SNAPSHOT
    manifest = json.loads((paquete / "manifest.json").read_text(encoding="utf-8"))
    if manifest["status"] != "complete":
        raise ValueError("El snapshot fijo está incompleto.")
    fuente = paquete / manifest["components"]["raw"]["path"] / "fred_brent.csv"
    brent = pd.read_csv(fuente, index_col="Date", parse_dates=["Date"])["brent"]
    diario = pd.read_csv(carpeta / "entradas_diarias.csv", usecols=["fecha"], parse_dates=["fecha"])
    indice = preparar_indice(brent.loc[manifest["start"]:manifest["end"]], pd.DatetimeIndex(diario["fecha"]))
    destino = carpeta / "ventanas_objetivos.csv"
    with tempfile.NamedTemporaryFile(dir=carpeta, delete=False) as archivo:
        temporal = Path(archivo.name)
    try:
        indice.to_csv(temporal, index=False, date_format="%Y-%m-%d")
        os.replace(temporal, destino)
    finally:
        temporal.unlink(missing_ok=True)
    print(destino)


if __name__ == "__main__":
    main()
