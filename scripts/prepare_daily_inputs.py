"""Reconstrucción diaria a las 09:00 de Madrid para el snapshot de comparación."""

import json
import os
import tempfile
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "data/raw/20261106T142300_705279Z_all"
MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()


def deposito_bce(path):
    soup = BeautifulSoup(path.read_bytes(), "html.parser")
    table = next(t for t in soup.select("table") if "Deposit facility" in t.get_text(" ", strip=True))
    years_rates = {}
    year = None
    for row in table.select("tbody tr"):
        for note in row.select("sup"):
            note.decompose()
        cells = [td.get_text(strip=True) for td in row.select("td")]
        if cells[0]:
            year = int(cells[0])
        day, month = cells[1].split()
        date = pd.Timestamp(year, MONTHS.index(month[:3].lower()) + 1, int(day))
        if date in years_rates:
            raise ValueError(f"Fecha BCE duplicada: {date}")
        years_rates[date] = float(cells[2].replace("−", "-"))
    return pd.Series(years_rates, name="tipo_bce").sort_index()


def alinear(serie, fechas, retraso, caducidad):
    if serie.index.has_duplicates or serie.index.hasnans:
        raise ValueError(f"Fechas inválidas en {serie.name}")
    datos = serie.dropna().sort_index().rename("valor").rename_axis("origen").reset_index()
    if caducidad is None:  # Vigencia BCE al cierre del día natural anterior.
        datos["disponible_desde"] = datos["origen"] + pd.Timedelta(days=1)
    else:
        datos["disponible_desde"] = datos["origen"] + pd.offsets.BDay(retraso)
    datos["disponible_desde"] = datos["disponible_desde"].astype("datetime64[ns]")
    fechas = fechas.as_unit("ns")
    filas = pd.merge_asof(fechas.to_frame(name="fecha", index=False), datos,
                          left_on="fecha", right_on="disponible_desde").set_index("fecha")
    conocido = filas["origen"].notna()
    edad = pd.Series(pd.NA, index=filas.index, dtype="Int64")
    edad.loc[conocido] = np.busday_count(
        filas.loc[conocido, "origen"].to_numpy(dtype="datetime64[D]"),
        filas.index[conocido].to_numpy(dtype="datetime64[D]"),
    )
    valido = conocido if caducidad is None else conocido & edad.le(caducidad).fillna(False)
    motivo = pd.Series("disponible", index=filas.index)
    motivo.loc[~conocido] = "sin_observacion_admisible_previa"
    motivo.loc[conocido & ~valido] = "caducado"
    if serie.name.endswith("_Volume"):
        motivo.loc[conocido & ~valido] = "sin_volumen_jornada_previa"
    return pd.DataFrame({
        serie.name: filas["valor"].where(valido),
        f"{serie.name}_disponible": valido.astype(int),
        f"{serie.name}_origen": filas["origen"],
        f"{serie.name}_edad": edad,
        f"{serie.name}_estado": motivo,
    })


FRED = ("wti", "gas_natural", "usd_por_eur", "cny_por_usd", "vix")
YAHOO = ("brent_fut", "wti_fut", "cobre", "oro", "indice_dolar")


def cesta_opep(path):
    xml = ElementTree.parse(path)
    cesta = pd.DataFrame([item.attrib for item in xml.getroot()])
    return pd.Series(pd.to_numeric(cesta["val"]).to_numpy(), index=pd.to_datetime(cesta["data"]), name="cesta_opep")


def construir_tabla(fuentes, fechas):
    """Tabla diaria a las 09:00 para un calendario dado, con las reglas de disponibilidad del protocolo.

    `fuentes` contiene `brent` y las series FRED (Series), `tipo_bce` (Series), `yahoo` (DataFrame por
    fuente, con columnas en el orden descargado) y `cesta_opep` (Series). El orden de columnas es fijo.
    """
    if fechas.empty or fechas.has_duplicates or not fechas.is_monotonic_increasing:
        raise ValueError("Calendario inválido")
    partes = [alinear(fuentes["brent"], fechas, 7, 10)]
    for nombre in FRED:
        limites = (2, 5) if nombre == "vix" else (7, 10)
        partes.append(alinear(fuentes[nombre], fechas, *limites))
    partes.append(alinear(fuentes["tipo_bce"], fechas, 1, None))
    for fuente in YAHOO:
        for nombre, serie in fuentes["yahoo"][fuente].items():
            partes.append(alinear(serie, fechas, 1, 1 if nombre.endswith("_Volume") else 5))
    partes.append(alinear(fuentes["cesta_opep"], fechas, 2, 5))
    return pd.concat(partes, axis=1)


def tabla_diaria():
    return construir_tabla(*fuentes_paquete())


def fuentes_paquete():
    """Series del paquete fijo del estudio y su calendario (índice Brent entre inicio y fin)."""
    manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
    if manifest["status"] != "complete":
        raise ValueError("Snapshot incompleto")
    paths = manifest["components"]
    raw = BUNDLE / paths["raw"]["path"]

    def csv(nombre):
        return pd.read_csv(raw / f"{nombre}.csv", parse_dates=["Date"], index_col="Date")

    brent = csv("fred_brent")["brent"]
    fechas = brent.loc[manifest["start"]:manifest["end"]].index
    fuentes = {"brent": brent, **{n: csv(f"fred_{n}")[n] for n in FRED},
               "tipo_bce": deposito_bce(BUNDLE / paths["bce"]["path"]),
               "yahoo": {f: csv(f"yahoo_{f}") for f in YAHOO},
               "cesta_opep": cesta_opep(BUNDLE / paths["opep"]["path"])}
    return fuentes, fechas


def main():
    tabla = tabla_diaria()
    destino = ROOT / "data/processed" / BUNDLE.name / "entradas_diarias.csv"
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destino.parent, delete=False) as archivo:
        temporal = Path(archivo.name)
    try:
        tabla.to_csv(temporal, index_label="fecha", date_format="%Y-%m-%d")
        os.replace(temporal, destino)
    finally:
        temporal.unlink(missing_ok=True)
    print(f"{len(tabla)} mañanas del {tabla.index.min():%Y-%m-%d} al {tabla.index.max():%Y-%m-%d}")
    print(tabla.filter(regex="_disponible$").sum().to_string())
    print(destino)


if __name__ == "__main__":
    main()
