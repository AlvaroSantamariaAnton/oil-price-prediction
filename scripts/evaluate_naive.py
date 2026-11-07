"""MAE del último Brent admisible en los cuatro cortes de validación."""

import os
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import pandas as pd

from scripts.prepare_windows import HORIZONTES, ROOT, SNAPSHOT


def evaluar(anual, diario, objetivos):
    claves = ["fecha_origen", "horizonte"]
    predicciones = anual.merge(objetivos, on=claves, how="left", validate="one_to_one")
    predicciones = predicciones.merge(diario, left_on="fecha_origen", right_index=True,
                                     how="left", validate="many_to_one")
    if not predicciones["brent_disponible"].eq(1).all():
        raise ValueError("Hay orígenes de validación sin referencia admisible.")
    precios = predicciones[["brent", "brent_objetivo"]]
    if not np.isfinite(precios.to_numpy()).all():
        raise ValueError("Falta un precio de referencia u objetivo en la validación.")
    if not (predicciones["brent_origen"] < predicciones["fecha_origen"]).all():
        raise ValueError("La observación de referencia debe preceder a la predicción.")
    predicciones = predicciones.rename(columns={"brent": "prediccion_ingenua"})
    predicciones["error_absoluto"] = (
        predicciones["prediccion_ingenua"] - predicciones["brent_objetivo"]
    ).abs()
    resumen = predicciones.groupby(["corte", "horizonte"]).agg(
        origenes=("fecha_origen", "size"), mae_usd_barril=("error_absoluto", "mean")
    )
    esperados = {(anio, h) for anio in range(2018, 2022) for h in HORIZONTES}
    if set(resumen.index) != esperados or not predicciones.fecha_origen.dt.year.eq(predicciones.corte).all():
        raise ValueError("Los cortes u horizontes difieren del protocolo de validación.")
    return predicciones, resumen.reset_index()


def main():
    carpeta = ROOT / "data/processed" / SNAPSHOT
    particiones = pd.read_csv(carpeta / "particiones_validacion.csv",
                              usecols=["fecha_origen", "horizonte", "corte", "tramo"],
                              parse_dates=["fecha_origen"])
    anual = particiones.loc[particiones.tramo.eq("validacion")].drop(columns="tramo")
    diario = pd.read_csv(carpeta / "entradas_diarias.csv", index_col="fecha",
                         usecols=["fecha", "brent", "brent_disponible", "brent_origen"],
                         parse_dates=["fecha", "brent_origen"])
    objetivos = pd.read_csv(carpeta / "ventanas_objetivos.csv",
                            usecols=["fecha_origen", "horizonte", "fecha_objetivo", "brent_objetivo"],
                            parse_dates=["fecha_origen", "fecha_objetivo"])
    predicciones, resumen = evaluar(anual, diario, objetivos)
    destino = carpeta / "referencia_ingenua_validacion.zip"
    with tempfile.NamedTemporaryFile(dir=carpeta, delete=False) as archivo:
        temporal = Path(archivo.name)
    try:
        with ZipFile(temporal, "w", compression=ZIP_DEFLATED) as salida:
            salida.writestr("predicciones.csv", predicciones.to_csv(index=False))
            salida.writestr("resumen.csv", resumen.to_csv(index=False))
        os.replace(temporal, destino)
    finally:
        temporal.unlink(missing_ok=True)
    print(resumen.to_string(index=False))
    print(destino)


if __name__ == "__main__":
    main()
