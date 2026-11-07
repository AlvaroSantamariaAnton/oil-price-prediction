"""Ajustar por corte y horizonte y transformar las filas usadas en validación."""

import json
import os
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import pandas as pd

from scripts.prepare_windows import HORIZONTES, ROOT, SNAPSHOT, VENTANA


def filas_de_ventanas(calendario, origenes):
    posiciones = calendario.get_indexer(origenes)
    if not len(posiciones) or (posiciones < VENTANA - 1).any():
        raise ValueError("Tramo vacío u origen sin ventana completa.")
    mascara = np.zeros(len(calendario), dtype=bool)
    for fin in posiciones:
        mascara[fin - VENTANA + 1:fin + 1] = True
    return mascara


def main():
    carpeta = ROOT / "data/processed" / SNAPSHOT
    diario = pd.read_csv(carpeta / "entradas_diarias.csv", index_col="fecha", parse_dates=["fecha"])
    particiones = pd.read_csv(carpeta / "particiones_validacion.csv", parse_dates=["fecha_origen"])
    if not diario.index.is_unique or not diario.index.is_monotonic_increasing:
        raise ValueError("El calendario diario debe ser único y cronológico.")
    variables = [c.removesuffix("_disponible") for c in diario if c.endswith("_disponible")]
    valores = diario[variables]
    indicadores = diario[[f"{v}_disponible" for v in variables]]
    if not np.array_equal(indicadores.to_numpy(), valores.notna().to_numpy()):
        raise ValueError("Los indicadores de disponibilidad no coinciden con los valores.")
    if particiones.duplicated(["corte", "horizonte", "fecha_origen"]).any():
        raise ValueError("Origen repetido dentro de una partición.")

    destino = carpeta / "escalado_validacion.zip"
    with tempfile.NamedTemporaryFile(dir=carpeta, delete=False) as archivo:
        temporal = Path(archivo.name)
    try:
        with ZipFile(temporal, "w", compression=ZIP_DEFLATED) as salida:
            for corte in range(2018, 2022):
                for horizonte in HORIZONTES:
                    grupo = particiones.loc[(particiones.corte == corte) & (particiones.horizonte == horizonte)]
                    if set(grupo.tramo) != {"aprendizaje", "interno", "validacion"}:
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
                        "snapshot": SNAPSHOT, "corte": corte, "horizonte": horizonte,
                        "fechas_aprendizaje": len(ajuste), "ddof": 0,
                        "orden_entradas": list(tabla.columns[1:]),
                        "media": medias.to_dict(), "desviacion": desviaciones.to_dict(),
                        "divisor": divisores.to_dict(), "n_disponibles": ajuste.count().to_dict(),
                    }
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
