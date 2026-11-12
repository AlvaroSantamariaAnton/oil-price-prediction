"""Ajustar por corte y horizonte y transformar las filas usadas en validación.

Con `--entradas variaciones`, las variables de precio se sustituyen antes de escalar por su
variación logarítmica diaria × 100 entre el valor admisible de la fecha y el de la fecha anterior
del calendario. La variación falta si falta alguno de los dos valores o si alguno no es positivo
(WTI en abril de 2020). Se guarda en un ZIP aparte; sin la opción, la salida no cambia.

Con `--fase final`, usa particiones_final.csv (corte 2023: aprendizaje, interno y test) y escribe
escalado_final.zip o escalado_final_variaciones.zip con la misma regla de ajuste.
"""

import argparse
import json
import os
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import pandas as pd

from scripts.prepare_windows import HORIZONTES, ROOT, SNAPSHOT, VENTANA

VARIABLES_PRECIO = ["brent", "wti", "gas_natural", "usd_por_eur", "cny_por_usd",
                    *[f"{f}_fut_{c}" for f in ("brent", "wti") for c in ("Open", "High", "Low", "Close")],
                    "cobre", "oro", "indice_dolar", "cesta_opep"]
DESTINOS = {"niveles": "escalado_validacion.zip", "variaciones": "escalado_validacion_variaciones.zip"}
DESTINOS_FINAL = {"niveles": "escalado_final.zip", "variaciones": "escalado_final_variaciones.zip"}
FASES = {"validacion": ("particiones_validacion.csv", range(2018, 2022), "validacion"),
         "final": ("particiones_final.csv", (2023,), "test")}


def a_variaciones(valores):
    """Variación logarítmica diaria × 100 de las variables de precio; el resto no cambia."""
    resultado = valores.copy()
    for v in VARIABLES_PRECIO:
        actual, anterior = valores[v], valores[v].shift(1)
        validos = (actual > 0) & (anterior > 0)
        resultado[v] = (100 * np.log(actual.where(validos) / anterior.where(validos))).where(validos)
    return resultado


def filas_de_ventanas(calendario, origenes):
    posiciones = calendario.get_indexer(origenes)
    if not len(posiciones) or (posiciones < VENTANA - 1).any():
        raise ValueError("Tramo vacío u origen sin ventana completa.")
    mascara = np.zeros(len(calendario), dtype=bool)
    for fin in posiciones:
        mascara[fin - VENTANA + 1:fin + 1] = True
    return mascara


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entradas", choices=DESTINOS, default="niveles")
    parser.add_argument("--fase", choices=FASES, default="validacion")
    argumentos = parser.parse_args()
    entradas, fase = argumentos.entradas, argumentos.fase
    archivo_particiones, cortes, tramo_evaluado = FASES[fase]
    carpeta = ROOT / "data/processed" / SNAPSHOT
    diario = pd.read_csv(carpeta / "entradas_diarias.csv", index_col="fecha", parse_dates=["fecha"])
    particiones = pd.read_csv(carpeta / archivo_particiones, parse_dates=["fecha_origen"])
    destino = carpeta / (DESTINOS_FINAL if fase == "final" else DESTINOS)[entradas]
    escribir_escalado(diario, particiones, destino, entradas, fase, cortes, tramo_evaluado, SNAPSHOT)


def escribir_escalado(diario, particiones, destino, entradas, fase, cortes, tramo_evaluado, snapshot):
    """Ajusta el escalador de cada corte y horizonte con las fechas de las ventanas de aprendizaje.

    `tramo_evaluado` es "validacion", "test" o None (reentrenamiento: solo aprendizaje e interno).
    `fase` se anota en el escalador salvo en validación.
    """
    carpeta = destino.parent
    if not diario.index.is_unique or not diario.index.is_monotonic_increasing:
        raise ValueError("El calendario diario debe ser único y cronológico.")
    variables = [c.removesuffix("_disponible") for c in diario if c.endswith("_disponible")]
    valores = diario[variables]
    indicadores = diario[[f"{v}_disponible" for v in variables]]
    if not np.array_equal(indicadores.to_numpy(), valores.notna().to_numpy()):
        raise ValueError("Los indicadores de disponibilidad no coinciden con los valores.")
    if entradas == "variaciones":
        if not set(VARIABLES_PRECIO) <= set(variables):
            raise ValueError("Faltan variables de precio en la tabla diaria.")
        valores = a_variaciones(valores)
        indicadores = valores.notna().astype(indicadores.dtypes.iloc[0])
        indicadores.columns = [f"{v}_disponible" for v in variables]
    if particiones.duplicated(["corte", "horizonte", "fecha_origen"]).any():
        raise ValueError("Origen repetido dentro de una partición.")
    requeridos = {"aprendizaje", "interno"} | ({tramo_evaluado} if tramo_evaluado else set())

    with tempfile.NamedTemporaryFile(dir=carpeta, delete=False) as archivo:
        temporal = Path(archivo.name)
    try:
        with ZipFile(temporal, "w", compression=ZIP_DEFLATED) as salida:
            for corte in cortes:
                for horizonte in HORIZONTES:
                    grupo = particiones.loc[(particiones.corte == corte) & (particiones.horizonte == horizonte)]
                    if set(grupo.tramo) != requeridos:
                        raise ValueError(f"Tramos incompletos en {corte}, +{horizonte}")
                    aprendizaje = grupo.loc[grupo.tramo == "aprendizaje", "fecha_origen"]
                    ajuste = valores.loc[filas_de_ventanas(diario.index, aprendizaje)]
                    medias = ajuste.mean()
                    desviaciones = ajuste.std(ddof=0)
                    if not np.isfinite(medias).all() or not np.isfinite(desviaciones).all():
                        raise ValueError(f"Estadísticas indefinidas en {corte}, +{horizonte}")
                    divisores = desviaciones.replace(0, 1)
                    usadas = filas_de_ventanas(diario.index, grupo.fecha_origen)
                    escaladas = ((valores.loc[usadas] - medias) / divisores).fillna(0)
                    if not np.isfinite(escaladas.to_numpy()).all():
                        raise ValueError("Valor transformado no finito.")
                    tabla = escaladas.join(indicadores.loc[usadas])
                    tabla.insert(0, "fila_diaria", np.flatnonzero(usadas))
                    parametros = {
                        "snapshot": snapshot, "corte": corte, "horizonte": horizonte,
                        "fechas_aprendizaje": len(ajuste), "ddof": 0,
                        "orden_entradas": list(tabla.columns[1:]),
                        "media": medias.to_dict(), "desviacion": desviaciones.to_dict(),
                        "divisor": divisores.to_dict(), "n_disponibles": ajuste.count().to_dict(),
                    }
                    if entradas == "variaciones":
                        parametros["entradas"] = entradas
                        parametros["variables_en_variacion"] = VARIABLES_PRECIO
                    if fase != "validacion":
                        parametros["fase"] = fase
                    prefijo = f"{corte}/h{horizonte:03d}"
                    salida.writestr(f"{prefijo}/escalador.json", json.dumps(parametros, indent=2, allow_nan=False))
                    salida.writestr(f"{prefijo}/entradas.csv", tabla.to_csv(index_label="fecha"))
                    print(f"{corte} +{horizonte}: {len(ajuste)} fechas únicas de aprendizaje "
                          f"({ajuste.index.min():%Y-%m-%d} a {ajuste.index.max():%Y-%m-%d}); "
                          f"{len(tabla)} fechas transformadas.")
        os.replace(temporal, destino)
    finally:
        temporal.unlink(missing_ok=True)
    print(destino)


if __name__ == "__main__":
    main()
