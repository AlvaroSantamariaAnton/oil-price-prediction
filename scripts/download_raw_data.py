"""Descarga snapshots por fuente, sin rellenar ni sobrescribir el CSV inicial."""
import argparse
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from importlib.metadata import version
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SERIES_FRED = {
    "DCOILBRENTEU": "brent", "DCOILWTICO": "wti", "DHHNGSP": "gas_natural",
    "ECBDFR": "tipo_bce", "DEXUSEU": "usd_por_eur", "DEXCHUS": "cny_por_usd",
    "VIXCLS": "vix",
}
SERIES_YAHOO = {
    "BZ=F": "brent_fut", "CL=F": "wti_fut", "HG=F": "cobre",
    "GC=F": "oro", "DX-Y.NYB": "indice_dolar",
}


def descargar_fuente(proveedor, serie, nombre, inicio, fin):
    if proveedor == "fred":
        url = ("https://fred.stlouisfed.org/graph/fredgraph.csv"
               f"?id={serie}&cosd={inicio}&coed={fin}")
        df = pd.read_csv(url, index_col=0, parse_dates=True, na_values=".")
        if len(df.columns) != 1:
            raise ValueError("Respuesta FRED inesperada")
        return df.rename(columns={df.columns[0]: nombre})
    import yfinance as yf
    # Yahoo usa fin exclusivo; nuestra opción --end es inclusiva.
    fin_exclusivo = (date.fromisoformat(fin) + timedelta(days=1)).isoformat()
    df = yf.download(serie, start=inicio, end=fin_exclusivo,
                     auto_adjust=False, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    campos = ["Open", "High", "Low", "Close", "Volume"] if serie in {"BZ=F", "CL=F"} else ["Close"]
    df = df[campos]
    return df.add_prefix(f"{nombre}_") if len(campos) > 1 else df.rename(columns={"Close": nombre})


def validar_fuente(df, inicio, fin):
    """Comprueba estructura; no elimina ni rellena observaciones."""
    if df.empty or not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("Respuesta vacía o índice sin fechas")
    if df.index.hasnans or df.index.has_duplicates or df.columns.has_duplicates:
        raise ValueError("Fechas ausentes o fechas/columnas duplicadas")
    if not all(pd.api.types.is_numeric_dtype(t) for t in df.dtypes):
        raise ValueError("Columnas no numéricas")
    if df.isna().all().any():
        raise ValueError("Alguna columna carece de observaciones")
    if min(df.index.date) < date.fromisoformat(inicio) or max(df.index.date) > date.fromisoformat(fin):
        raise ValueError("Fechas fuera del intervalo solicitado")


def descargar_snapshot(inicio, fin, destino=DATA_DIR / "raw"):
    if date.fromisoformat(inicio) > date.fromisoformat(fin):
        raise ValueError("El inicio debe ser anterior o igual al fin")
    instante = datetime.now(timezone.utc)
    carpeta = Path(destino) / instante.strftime("%Y%m%dT%H%M%S_%fZ")
    carpeta.mkdir(parents=True, exist_ok=False)
    manifest = {
        "status": "in_progress", "download_started_utc": instante.isoformat(),
        "requested_start_inclusive": inicio, "requested_end_inclusive": fin,
        "versions": {p: version(p) for p in ("pandas", "yfinance")},
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "notes": [
            "Valores extraídos por pandas/yfinance; no respuestas HTTP originales.",
            "Sin unión de calendarios, relleno, escalado o eliminación de filas.",
            "La fecha de observación no es la fecha de publicación; puede haber revisiones.",
            "No incluye OPEP. complete indica éxito de las 12 fuentes configuradas, no calidad económica.",
        ], "sources": [],
    }

    def guardar_manifest():
        (carpeta / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    guardar_manifest()
    fuentes = [("fred", s, n) for s, n in SERIES_FRED.items()]
    fuentes += [("yahoo", s, n) for s, n in SERIES_YAHOO.items()]
    for proveedor, serie, nombre in fuentes:
        entrada = {"provider": proveedor, "series": serie, "name": nombre}
        print(f"Descargando {proveedor}: {serie}...", flush=True)
        try:
            df = descargar_fuente(proveedor, serie, nombre, inicio, fin)
            validar_fuente(df, inicio, fin)
            archivo = carpeta / f"{proveedor}_{nombre}.csv"
            df.to_csv(archivo, index_label="Date")
            entrada.update({
                "status": "ok", "file": archivo.name, "rows": len(df),
                "first_date": df.index.min().isoformat(), "last_date": df.index.max().isoformat(),
                "missing_by_column": {c: int(v) for c, v in df.isna().sum().items()},
                "sha256": hashlib.sha256(archivo.read_bytes()).hexdigest(),
            })
        except Exception as exc:
            entrada.update({"status": "error", "error": str(exc)})
            print(f"ERROR en {serie}: {exc}", flush=True)
        manifest["sources"].append(entrada)
        guardar_manifest()
    correcto = all(s["status"] == "ok" for s in manifest["sources"])
    manifest["status"] = "complete" if correcto else "incomplete"
    manifest["download_finished_utc"] = datetime.now(timezone.utc).isoformat()
    guardar_manifest()
    print(f"Snapshot {manifest['status']}: {carpeta}")
    return carpeta, correcto


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2000-01-01", help="Fecha inicial inclusiva YYYY-MM-DD")
    parser.add_argument("--end", default=date.today().isoformat(), help="Fecha final inclusiva YYYY-MM-DD")
    args = parser.parse_args()
    _, correcto = descargar_snapshot(args.start, args.end)
    return 0 if correcto else 1


if __name__ == "__main__":
    raise SystemExit(main())
