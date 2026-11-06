"""Crea un paquete único de fuentes para la auditoría, sin borrar snapshots."""
import argparse
import hashlib
import json
import os
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path
from curl_cffi import requests

try:
    from . import download_raw_data as raw
    from . import download_alfred_data as alfred
except ImportError:
    import download_raw_data as raw
    import download_alfred_data as alfred

OPEC_URL = "https://www.opec.org/basket/basketDayArchives.xml"
ECB_URL = "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/key_ecb_interest_rates/html/index.en.html"
ROOT = Path(__file__).resolve().parent.parent


def obtener(url):
    """Cliente HTTPS ya instalado con yfinance; conserva validación TLS."""
    for intento in range(3):
        try:
            with requests.Session(impersonate='chrome', verify=True) as session:
                r = session.get(url, timeout=60)
                if r.status_code == 200:
                    return r.content
                if r.status_code not in (429, 500, 502, 503, 504):
                    raise alfred.DownloadError(f'HTTP {r.status_code}: el servidor rechazó la descarga')
                detalle = f'HTTP {r.status_code} tras tres intentos'
        except requests.exceptions.RequestException as exc:
            detalle = f'Fallo HTTPS ({type(exc).__name__}): {exc}'
        if intento == 2:
            raise alfred.DownloadError(detalle)
        time.sleep(2 ** (intento + 1))


def descargar_todo(inicio, fin, fin_observaciones, clave, destino=ROOT / 'data/raw'):
    if not date.fromisoformat(inicio) <= date.fromisoformat(fin_observaciones) <= date.fromisoformat(fin):
        raise ValueError('Se requiere start <= alfred-end <= end')
    if not clave:
        raise ValueError('Falta FRED_API_KEY')
    carpeta = Path(destino) / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ') + '_all')
    carpeta.mkdir(parents=True, exist_ok=False)
    m = dict(schema='oil-audit-bundle-v1', status='in_progress', start=inicio, end=fin,
             alfred_observation_end=fin_observaciones, components={},
             started_utc=datetime.now(timezone.utc).isoformat(),
             notes=['Raw Yahoo/FRED, OPEP y tabla BCE reflejan descarga actual; no son versiones históricas al corte.',
                    'El CSV inicial se copia solo como referencia histórica, no se regenera.',
                    'Los datos de OPEP/BCE pueden superar el corte: filtrar en preparación.',
                    'No se borran archivos anteriores ni se actualiza automáticamente el dataset de experimentos.'])

    def guardar():
        (carpeta / 'manifest.json').write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding='utf-8')

    def componente(nombre, accion):
        print(f'Fuente: {nombre}', flush=True)
        try:
            entrada = accion()
            m['components'][nombre] = entrada
        except Exception as exc:
            detalle = alfred.limpiar_error(str(exc), clave)
            m['components'][nombre] = dict(status='error', error_type=type(exc).__name__, error_detail=detalle)
            print(f'Fallo en {nombre}: {type(exc).__name__}: {detalle}. Se conserva el resto.', flush=True)
        guardar()

    def snapshot(funcion, *args):
        p, ok = funcion(*args, destino=carpeta)
        return dict(status='ok' if ok else 'error', path=p.relative_to(carpeta).as_posix())

    def archivo(nombre, contenido, url=None):
        if clave.encode() in contenido:
            raise ValueError('Contenido inesperado con credencial')
        (carpeta / nombre).write_bytes(contenido)
        return dict(status='ok', path=nombre, sha256=hashlib.sha256(contenido).hexdigest(), source=url)

    def opep():
        contenido = obtener(OPEC_URL)
        registros = list(ET.fromstring(contenido))
        if not registros:
            raise ValueError('OPEP vacío')
        for r in registros:
            date.fromisoformat(r.attrib['data'])
            float(r.attrib['val'])
        return archivo('basketDayArchives.xml', contenido, OPEC_URL)

    def bce():
        contenido = obtener(ECB_URL)
        from bs4 import BeautifulSoup
        tablas = BeautifulSoup(contenido, 'html.parser').find_all('table')
        if not any('Deposit facility' in t.get_text() and '1999' in t.get_text() for t in tablas):
            raise ValueError('No se encontró tabla histórica BCE')
        return archivo('ecb_key_interest_rates.html', contenido, ECB_URL)

    guardar()
    componente('raw', lambda: snapshot(raw.descargar_snapshot, inicio, fin))
    for serie in raw.SERIES_FRED:
        componente(serie, lambda s=serie: snapshot(alfred.descargar_snapshot, s, inicio, fin_observaciones, fin, clave))
    componente('opep', opep)
    componente('bce', bce)
    componente('initial_csv', lambda: archivo('petroleo_dataset_initial.csv', (ROOT / 'data/petroleo_dataset.csv').read_bytes(), 'data/petroleo_dataset.csv'))
    m['status'] = 'complete' if all(c['status'] == 'ok' for c in m['components'].values()) else 'incomplete'
    m['finished_utc'] = datetime.now(timezone.utc).isoformat()
    guardar()
    print(f"Paquete {m['status']}: {carpeta}")
    return carpeta, m['status'] == 'complete'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', default='2000-01-01')
    parser.add_argument('--end', default='2026-11-04')
    parser.add_argument('--alfred-end', default='2026-11-03')
    args = parser.parse_args()
    try:
        _, ok = descargar_todo(args.start, args.end, args.alfred_end, os.environ.get('FRED_API_KEY', '').strip())
    except ValueError as exc:
        parser.error(str(exc))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
