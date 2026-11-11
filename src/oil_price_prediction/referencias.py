"""Predictores de referencia compartidos por el estudio y la aplicación (sin PyTorch)."""

import numpy as np
import pandas as pd


def ingenuo_con_futuros_tabla(d):
    """Último spot admisible actualizado con el futuro de Brent, por fecha de origen.

    `d` es la tabla diaria con las columnas fecha, brent, brent_disponible, brent_origen,
    brent_fut_Close, brent_fut_Close_disponible y brent_fut_Close_origen (orígenes como fechas).
    Valor = spot admisible × cierre admisible del futuro en el origen / último cierre observado del
    futuro en o antes de la fecha de observación de ese spot. Falta (NaN) si no hay spot, futuro en el
    origen o futuro anterior al spot, o si algún precio no es positivo.
    """
    observados = (d.loc[d.brent_fut_Close_disponible == 1, ["brent_fut_Close_origen", "brent_fut_Close"]]
                  .drop_duplicates("brent_fut_Close_origen").set_index("brent_fut_Close_origen").brent_fut_Close.sort_index())
    if not observados.index.is_unique:
        raise ValueError("Cierre del futuro repetido con distinta fecha de observación.")
    futuro_base = pd.Series(observados.reindex(d.brent_origen, method="ffill").to_numpy(), index=d.index)
    futuro_base[d.brent_origen.isna()] = np.nan
    validos = ((d.brent_disponible == 1) & (d.brent_fut_Close_disponible == 1) & (d.brent > 0)
               & (d.brent_fut_Close > 0) & (futuro_base > 0))
    valor = (d.brent * d.brent_fut_Close / futuro_base).where(validos)
    return pd.Series(valor.to_numpy(), index=d.fecha, name="prediccion_ingenua_futuros")
