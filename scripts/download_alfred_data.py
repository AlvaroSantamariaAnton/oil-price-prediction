"""Descarga intervalos históricos ALFRED sin transformar sus observaciones."""
import argparse
import hashlib
import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

ENDPOINT = "https://api.stlouisfed.org/fred/series/observations"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


class DownloadError(RuntimeError):
    """Diagnóstico con credenciales y URLs eliminadas."""


def limpiar_error(mensaje, clave):
    if not isinstance(mensaje, str):
        return "Respuesta de error sin descripción textual"
    mensaje = mensaje.replace(clave, "[CLAVE OCULTA]") if clave else mensaje
    mensaje = re.sub(r"https?://\S+", "[URL OCULTA]", mensaje)
    mensaje = re.sub(r"(?i)\b[a-z0-9]{32}\b", "[CLAVE OCULTA]", mensaje)
    return " ".join(mensaje.split())[:800]


def solicitar(params, clave):
    """No propagar errores HTTP con la URL que contiene la credencial."""
    url = ENDPOINT + "?" + urlencode({**params, "api_key": clave})
    for intento in range(4):
        try:
            with urlopen(url, timeout=60) as respuesta:
                return respuesta.read()
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or intento == 3:
                detalle = ""
                try:
                    mensaje = json.loads(exc.read()).get("error_message", "")
                    detalle = "; " + limpiar_error(mensaje, clave)
                except (ValueError, AttributeError, TypeError, OSError):
                    pass
                raise DownloadError(f"FRED respondió HTTP {exc.code}{detalle}") from None
        except (URLError, TimeoutError, OSError):
            if intento == 3:
                raise DownloadError("No se pudo completar la conexión con FRED tras cuatro intentos") from None
        time.sleep(2 ** (intento + 1))


def descargar_snapshot(serie, inicio, fin, corte, clave, destino=RAW_DIR,
                       solicitar_pagina=solicitar):
    if not re.fullmatch(r"[A-Za-z0-9_]+", serie):
        raise ValueError("Identificador de serie inválido")
    if not date.fromisoformat(inicio) <= date.fromisoformat(fin) <= date.fromisoformat(corte):
        raise ValueError("Se requiere start <= end <= vintage-end")
    if not clave:
        raise ValueError("Falta FRED_API_KEY en esta terminal")
    instante = datetime.now(timezone.utc)
    carpeta = Path(destino) / (instante.strftime("%Y%m%dT%H%M%S_%fZ") + "_alfred_" + serie)
    carpeta.mkdir(parents=True, exist_ok=False)
    params = dict(series_id=serie, file_type="json", units="lin", output_type=1,
                  observation_start=inicio, observation_end=fin,
                  realtime_start="1776-07-04", realtime_end=corte,
                  sort_order="asc", limit=100000, offset=0)
    manifest = {
        "status": "in_progress", "download_started_utc": instante.isoformat(),
        "endpoint": ENDPOINT, "parameters": params.copy(), "pages": [], "periods": [],
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "notes": ["Cuerpos JSON originales, sin relleno ni transformación.",
                  "Los intervalos de vigencia no aportan horas de publicación.",
                  "complete indica paginación completa, no cobertura histórica completa.",
                  "realtime_end limita las versiones al corte solicitado."],
    }

    def guardar():
        (carpeta / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    guardar()
    total = None
    vistos = set()
    pendientes = []
    acumulado = 0
    try:
        while True:
            print(f"Descargando {serie}, versiones {params['realtime_start']} a "
                  f"{params['realtime_end']}, offset {params['offset']}...", flush=True)
            try:
                contenido = solicitar_pagina(params.copy(), clave)
            except DownloadError as exc:
                if ("exceeds the maximum number of vintage dates" not in str(exc).lower()
                        or params["offset"] != 0):
                    raise
                primero = date.fromisoformat(params["realtime_start"])
                ultimo = date.fromisoformat(params["realtime_end"])
                if primero >= ultimo:
                    raise
                # Retirar un bloque de cinco años del extremo reciente; repetir
                # si el proveedor también considera demasiado grande el resto.
                mitad = max(primero, ultimo - timedelta(days=5 * 365))
                pendientes.append(((mitad + timedelta(days=1)).isoformat(), ultimo.isoformat()))
                params["realtime_end"] = mitad.isoformat()
                print("Límite de versiones: dividiendo el periodo automáticamente.", flush=True)
                time.sleep(0.6)
                continue
            # Una respuesta inesperada nunca debe persistir la credencial.
            if clave.encode() in contenido:
                raise ValueError("Respuesta que contiene la credencial")
            pagina = json.loads(contenido)
            filas = pagina["observations"]
            count = pagina["count"]
            if type(count) is not int or count < 0 or not isinstance(filas, list):
                raise ValueError("Respuesta vacía o estructura inválida")
            if pagina["offset"] != params["offset"] or (total is not None and count != total):
                raise ValueError("Paginación inconsistente")
            total = count
            if (not filas and total != 0) or params["offset"] + len(filas) > total:
                raise ValueError("Página incompleta o recuento inconsistente")
            for fila in filas:
                obs = date.fromisoformat(fila["date"])
                desde = date.fromisoformat(fila["realtime_start"])
                hasta = date.fromisoformat(fila["realtime_end"])
                if not date.fromisoformat(inicio) <= obs <= date.fromisoformat(fin):
                    raise ValueError("Observación fuera de rango")
                if not date.fromisoformat(params["realtime_start"]) <= desde <= hasta <= date.fromisoformat(params["realtime_end"]):
                    raise ValueError("Intervalo de vigencia fuera de rango")
                identidad = (fila["date"], fila["realtime_start"], fila["realtime_end"])
                if identidad in vistos:
                    raise ValueError("Intervalo duplicado entre páginas")
                vistos.add(identidad)
                if fila["value"] != ".":
                    float(fila["value"])
            nombre = f"page_{len(manifest['pages']) + 1:04d}.json"
            (carpeta / nombre).write_bytes(contenido)
            manifest["pages"].append({"file": nombre, "offset": params["offset"],
                                      "realtime_start": params["realtime_start"],
                                      "realtime_end": params["realtime_end"],
                                      "rows": len(filas),
                                      "sha256": hashlib.sha256(contenido).hexdigest()})
            params["offset"] += len(filas)
            manifest["downloaded_rows"] = acumulado + params["offset"]
            guardar()
            if params["offset"] == total:
                manifest["periods"].append({"realtime_start": params["realtime_start"],
                                            "realtime_end": params["realtime_end"],
                                            "expected_rows": total, "downloaded_rows": total})
                acumulado += total
                if not pendientes:
                    break
                params["realtime_start"], params["realtime_end"] = pendientes.pop()
                params["offset"] = 0
                total = None
                vistos.clear()
            time.sleep(0.6)
        if acumulado == 0:
            raise ValueError("No se obtuvieron observaciones en ningún periodo")
        manifest["expected_rows"] = acumulado
        manifest["status"] = "complete"
    except Exception as exc:
        manifest["status"] = "incomplete"
        # No registrar mensajes de excepción ni cuerpos de error del proveedor.
        manifest["error_type"] = type(exc).__name__
        if isinstance(exc, DownloadError):
            manifest["error_detail"] = str(exc)
        else:
            manifest["error_detail"] = "Respuesta no válida o fallo local; revisar validación y escritura."
        print(f"Descarga incompleta: {manifest['error_detail']}. Se conservan las páginas válidas.")
    finally:
        manifest["download_finished_utc"] = datetime.now(timezone.utc).isoformat()
        guardar()
    print(f"Snapshot {manifest['status']}: {carpeta}")
    return carpeta, manifest["status"] == "complete"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--series", default="VIXCLS")
    parser.add_argument("--start", default="2000-01-01")
    parser.add_argument("--end", default="2026-11-03")
    parser.add_argument("--vintage-end", default="2026-11-04")
    args = parser.parse_args()
    clave = os.environ.get("FRED_API_KEY", "").strip()
    if not clave:
        parser.error("Configura FRED_API_KEY en esta terminal antes de ejecutar")
    try:
        _, correcto = descargar_snapshot(args.series, args.start, args.end, args.vintage_end, clave)
    except ValueError as exc:
        parser.error(str(exc))
    return 0 if correcto else 1


if __name__ == "__main__":
    raise SystemExit(main())
