"""Decidir si una ejecución programada de la previsión diaria debe calcular la previsión.

GitHub retrasa o se salta a veces las tareas programadas, así que el flujo se programa varias veces al
día y cada ejecución decide aquí si hace falta trabajar:
- ejecución manual con «forzar»: siempre;
- fin de semana o antes de las 09:00 de Madrid: no;
- si la previsión publicada ya es de hoy y se calculó a partir de las 09:00 de Madrid: no;
- en otro caso (no hay previsión de hoy, solo hay una calculada antes de las 09:00 o no se puede leer la
  publicada): sí.
Solo usa la biblioteca estándar (se ejecuta antes de instalar dependencias). Escribe `seguir=true|false`
en GITHUB_OUTPUT si existe.
"""

import argparse
from datetime import datetime, time
import json
import os
import urllib.request
from zoneinfo import ZoneInfo

ZONA = ZoneInfo("Europe/Madrid")
HORA = time(9, 0)


def hace_falta(ahora, prevision):
    """`ahora` en hora de Madrid; `prevision` es el JSON publicado o None si no se pudo leer."""
    if ahora.weekday() >= 5:
        return False, "fin de semana"
    if ahora.time() < HORA:
        return False, "antes de las 09:00 de Madrid"
    if prevision is None:
        return True, "no se pudo leer la previsión publicada"
    hoy = ahora.date().isoformat()
    if prevision.get("origen") != hoy:
        return True, f"la previsión publicada es del {prevision.get('origen')}"
    generado = datetime.fromisoformat(prevision["generado_utc"]).astimezone(ZONA)
    if generado < datetime.combine(ahora.date(), HORA, ZONA):
        return True, f"la previsión de hoy se calculó a las {generado:%H:%M}, antes de las 09:00"
    return False, f"ya hay una previsión de hoy calculada a las {generado:%H:%M}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="URL de prediccion.json publicada")
    parser.add_argument("--forzar", default="false", help="true en una ejecución manual forzada")
    a = parser.parse_args()
    ahora = datetime.now(ZONA)
    if a.forzar == "true":
        seguir, motivo = True, "ejecución manual forzada"
    else:
        try:
            with urllib.request.urlopen(a.url, timeout=30) as respuesta:
                prevision = json.load(respuesta)
        except Exception as exc:  # Sin la previsión publicada, mejor calcular que quedarse sin previsión.
            print(f"No se pudo leer la previsión publicada: {type(exc).__name__}")
            prevision = None
        seguir, motivo = hace_falta(ahora, prevision)
    print(f"Hora en Madrid: {ahora:%Y-%m-%d %H:%M}. {'Se calcula' if seguir else 'No se calcula'}: {motivo}.")
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as salida:
            salida.write(f"seguir={'true' if seguir else 'false'}\n")


if __name__ == "__main__":
    main()
