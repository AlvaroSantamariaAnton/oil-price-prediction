"""Asignar orígenes a aprendizaje, parada temprana y validación anual.

Con `--fase final`, la frontera es la primera mañana del calendario Brent de 2023 y se escribe
particiones_final.csv: aprendizaje e interno con las mismas reglas que en validación, y test con todos
los orígenes desde la frontera con spot admisible (las ventanas ya exigen objetivo en el paquete).
Sin la opción, la salida de validación no cambia.
"""

import argparse
import os
import tempfile
from pathlib import Path

import pandas as pd

from scripts.prepare_windows import HORIZONTES, ROOT, SNAPSHOT


def particionar(ventanas, diario):
    grupos = []
    resumen = []
    if not diario.index.is_unique or not diario.index.is_monotonic_increasing:
        raise ValueError("El calendario diario debe ser único y cronológico.")
    if ventanas.duplicated(["horizonte", "fecha_origen"]).any():
        raise ValueError("Hay orígenes repetidos dentro de un horizonte.")
    datos = ventanas.join(diario, on="fecha_origen", validate="many_to_one")
    if not datos["brent_disponible"].isin([0, 1]).all():
        raise ValueError("Falta la disponibilidad del Brent en algún origen.")
    for anio in range(2018, 2022):
        frontera = diario.loc[str(anio)].index.min()
        for horizonte in HORIZONTES:
            serie = datos.loc[datos["horizonte"].eq(horizonte)].sort_values("fecha_origen")
            anteriores = serie.loc[serie["fecha_origen"] < frontera]
            conocidos = anteriores.loc[anteriores["etiqueta_disponible_desde"] <= frontera]
            n_interno = (15 * len(conocidos) + 99) // 100
            if n_interno == 0:
                raise ValueError(f"Histórico vacío para {anio}, horizonte {horizonte}.")
            interno = conocidos.tail(n_interno)
            inicio_interno = interno["fecha_origen"].iloc[0]
            candidatos = conocidos.iloc[:-n_interno]
            aprendizaje = candidatos.loc[candidatos["etiqueta_disponible_desde"] <= inicio_interno]
            anual = serie.loc[serie["fecha_origen"].dt.year.eq(anio)
                              & serie["brent_disponible"].eq(1)
                              & (serie["etiqueta_disponible_desde"] <= pd.Timestamp("2023-01-02"))]
            if aprendizaje.empty or anual.empty:
                raise ValueError(f"Tramo vacío para {anio}, horizonte {horizonte}.")
            for tramo, filas in (("aprendizaje", aprendizaje), ("interno", interno), ("validacion", anual)):
                grupos.append(filas.assign(corte=anio, tramo=tramo))
            resumen.append({
                "corte": anio, "h": horizonte, "inicio_interno": inicio_interno.date(),
                "inicio_anual": frontera.date(), "aprendizaje": len(aprendizaje),
                "interno": len(interno), "validacion": len(anual),
                "purga_interna": len(candidatos) - len(aprendizaje),
                "purga_anual": len(anteriores) - len(conocidos),
            })
    return pd.concat(grupos, ignore_index=True), pd.DataFrame(resumen)


ANIO_TEST = 2023


def particionar_final(ventanas, diario, frontera=None, exigir_test=True):
    """Aprendizaje, interno y test para los ajustes finales, con la misma regla de fronteras.

    Sin `frontera`, es la primera mañana del calendario de 2023 (ajustes finales del estudio). El
    reentrenamiento de la aplicación pasa la fecha de corte (hoy) y `exigir_test=False`: entonces no
    hay orígenes de test y solo se devuelven aprendizaje e interno. La columna `corte` es el año de
    la frontera.
    """
    grupos, resumen = [], []
    if not diario.index.is_unique or not diario.index.is_monotonic_increasing:
        raise ValueError("El calendario diario debe ser único y cronológico.")
    if ventanas.duplicated(["horizonte", "fecha_origen"]).any():
        raise ValueError("Hay orígenes repetidos dentro de un horizonte.")
    datos = ventanas.join(diario, on="fecha_origen", validate="many_to_one")
    if not datos["brent_disponible"].isin([0, 1]).all():
        raise ValueError("Falta la disponibilidad del Brent en algún origen.")
    frontera = diario.loc[str(ANIO_TEST)].index.min() if frontera is None else pd.Timestamp(frontera)
    corte = frontera.year
    for horizonte in HORIZONTES:
        serie = datos.loc[datos["horizonte"].eq(horizonte)].sort_values("fecha_origen")
        anteriores = serie.loc[serie["fecha_origen"] < frontera]
        conocidos = anteriores.loc[anteriores["etiqueta_disponible_desde"] <= frontera]
        n_interno = (15 * len(conocidos) + 99) // 100
        interno = conocidos.tail(n_interno)
        inicio_interno = interno["fecha_origen"].iloc[0]
        candidatos = conocidos.iloc[:-n_interno]
        aprendizaje = candidatos.loc[candidatos["etiqueta_disponible_desde"] <= inicio_interno]
        test = serie.loc[(serie["fecha_origen"] >= frontera) & serie["brent_disponible"].eq(1)]
        if aprendizaje.empty or interno.empty or (exigir_test and test.empty):
            raise ValueError(f"Tramo vacío en el ajuste final, horizonte {horizonte}.")
        tramos = (("aprendizaje", aprendizaje), ("interno", interno)) + ((("test", test),) if len(test) else ())
        for tramo, filas in tramos:
            grupos.append(filas.assign(corte=corte, tramo=tramo))
        resumen.append({
            "corte": corte, "h": horizonte, "inicio_interno": inicio_interno.date(),
            "inicio_test": frontera.date(), "aprendizaje": len(aprendizaje), "interno": len(interno),
            "test": len(test), "ultimo_origen_test": test["fecha_origen"].max().date() if len(test) else None,
            "purga_interna": len(candidatos) - len(aprendizaje),
            "purga_frontera": len(anteriores) - len(conocidos),
            "test_sin_spot": int((serie["fecha_origen"] >= frontera).sum() - len(test)),
        })
    return pd.concat(grupos, ignore_index=True), pd.DataFrame(resumen)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fase", choices=("validacion", "final"), default="validacion")
    fase = parser.parse_args().fase
    carpeta = ROOT / "data/processed" / SNAPSHOT
    diario = pd.read_csv(carpeta / "entradas_diarias.csv", usecols=["fecha", "brent_disponible"],
                         index_col="fecha", parse_dates=["fecha"])
    ventanas = pd.read_csv(carpeta / "ventanas_objetivos.csv",
                           usecols=["horizonte", "fecha_origen", "etiqueta_disponible_desde"],
                           parse_dates=["fecha_origen", "etiqueta_disponible_desde"])
    if fase == "final":
        indice, resumen = particionar_final(ventanas, diario)
        destino = carpeta / "particiones_final.csv"
    else:
        indice, resumen = particionar(ventanas, diario)
        destino = carpeta / "particiones_validacion.csv"
    with tempfile.NamedTemporaryFile(dir=carpeta, delete=False) as archivo:
        temporal = Path(archivo.name)
    try:
        indice.to_csv(temporal, index=False, date_format="%Y-%m-%d")
        os.replace(temporal, destino)
    finally:
        temporal.unlink(missing_ok=True)
    print(resumen.to_string(index=False))
    print(destino)


if __name__ == "__main__":
    main()
