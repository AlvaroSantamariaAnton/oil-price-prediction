"""Datos del estudio para la web (web/datos/estudio.json).

Reúne, a partir de los resultados ya guardados (validación de E1–E16, ajustes finales y evaluación del
test), todo lo que muestran las páginas del estudio: puntuaciones por familia y arquitectura frente a
las dos referencias, series de validación y de test por horizonte, márgenes e intervalos y la tabla
del test. No entrena ni recalcula el test: solo lee y resume. Necesita las carpetas locales de
validación de E1–E13 (ignoradas por Git); el JSON resultante sí se versiona con la web.
"""

import ast
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from scripts.evaluate_seed_ensemble import FAMILIAS, ingenuo_futuros
from scripts.evaluate_test import cargar_final, tabla_promediada
from scripts.evaluate_validation_uncertainty import ARQUITECTURAS, CORTES, mejora
from scripts.plot_validation import CARPETAS, promediadas
from scripts.prepare_windows import HORIZONTES, ROOT

DESTINO = ROOT / "web/datos/estudio.json"
ORDEN = ["precio", "cambio", "porcentaje", "cambio_tasa_menor", "variaciones", "futuros"]
R = lambda x, n=2: None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)


def serie(t, columnas):
    t = t.sort_values("fecha_origen")
    salida = {"origen": t.fecha_origen.dt.strftime("%Y-%m-%d").tolist(),
              "objetivo": t.fecha_objetivo.dt.strftime("%Y-%m-%d").tolist()}
    for nombre, col in columnas.items():
        salida[nombre] = [R(v) for v in t[col]]
    return salida


def main():
    futuros = ingenuo_futuros()
    familias, validacion = [], {}
    for familia in ORDEN:
        tablas, tamanos, puntuaciones, principal = promediadas(familia, futuros)
        filas = {}
        for a in ARQUITECTURAS:
            por_h = {}
            for h in HORIZONTES:
                t = tablas[a, h]
                anual_i = [mejora(g.error.to_numpy(), g.error_ingenuo.to_numpy()) for _, g in t.groupby("corte")]
                anual_f = [mejora(g.error.to_numpy(), g.error_futuros.to_numpy()) for _, g in t.groupby("corte")]
                por_h[str(h)] = dict(unidades=tamanos[a, h], frente_ingenuo=R(np.mean(anual_i)),
                                     frente_futuros=R(np.mean(anual_f)),
                                     anual_frente_ingenuo=[R(x) for x in anual_i])
            todos_i = sum((v["anual_frente_ingenuo"] for v in por_h.values()), [])
            filas[a] = dict(puntuacion=R(puntuaciones[a]), frente_futuros=R(np.mean([v["frente_futuros"] for v in por_h.values()])),
                            pares_positivos=int(sum(x > 0 for x in todos_i)), horizontes=por_h)
        familias.append(dict(id=familia, experimentos=CARPETAS[familia], principal=principal,
                             semillas=len(FAMILIAS[familia][HORIZONTES[0]]), arquitecturas=filas))
        if familia in ("precio", "futuros"):
            validacion[familia] = {str(h): serie(tablas[principal, h], {"real": "brent_objetivo", "ingenuo": "prediccion_ingenua",
                                                                        "futuros": "prediccion_ingenua_futuros", "red": "prediccion"})
                                   for h in HORIZONTES}
            validacion[familia]["principal"] = principal
    # Referencia con futuros en validación (puntuación del protocolo).
    tablas, _, _, principal = promediadas("futuros", futuros)
    ref_futuros = {}
    for h in HORIZONTES:
        t = tablas[principal, h]
        ref_futuros[str(h)] = R(np.mean([mejora(g.error_futuros.to_numpy(), g.error_ingenuo.to_numpy()) for _, g in t.groupby("corte")]))
    ref_futuros["global"] = R(np.mean([ref_futuros[str(h)] for h in HORIZONTES]))
    # Test.
    config, ajustes = cargar_final()
    test_tablas = {(a, h): tabla_promediada(config, ajustes, a, h) for a in ARQUITECTURAS for h in HORIZONTES}
    test_series = {}
    for h in HORIZONTES:
        base = test_tablas[config["seleccionada"], h].sort_values("fecha_origen")
        s = serie(base, {"real": "brent_objetivo", "ingenuo": "prediccion_ingenua", "futuros": "prediccion_ingenua_futuros"})
        for a in ARQUITECTURAS:
            s[a] = [R(v) for v in test_tablas[a, h].sort_values("fecha_origen").prediccion]
        test_series[str(h)] = s
    tabla = pd.read_csv(ROOT / "reports/evaluacion_test.csv")
    filas_test = []
    for _, f in tabla.iterrows():
        fila = {}
        for k, v in f.items():
            if isinstance(v, str) and v.startswith("["):
                v = [R(x, 3) for x in json.loads(v)]
            elif isinstance(v, str) and v.startswith("{"):
                v = {str(a): R(b, 4) for a, b in ast.literal_eval(v).items()}
            elif isinstance(v, (float, np.floating)):
                v = None if np.isnan(v) else R(v, 6)
            elif isinstance(v, (np.integer,)):
                v = int(v)
            elif isinstance(v, (np.bool_,)):
                v = bool(v)
            fila[k] = v
        filas_test.append(fila)
    margenes = json.loads((ROOT / "reports/margenes_validacion.json").read_text(encoding="utf-8"))
    # Tramos de cada corte (validación E14 y ajuste final) por horizonte, para el esquema de particiones.
    tramos = {}
    for h in HORIZONTES:
        u = config["unidades"][config["seleccionada"]][str(h)]
        filas_t = {}
        for corte in CORTES:
            registro = next((ROOT / "reports/experimentos/E14/validacion").glob(f"*_{config['seleccionada']}_h{h:03d}_u{u:03d}_corte{corte}"))
            filas_t[str(corte)] = json.loads((registro / "registro.json").read_text(encoding="utf-8"))["tramos"]
        registro = next((ROOT / "reports/experimentos/final").glob(f"*_{config['seleccionada']}_h{h:03d}_u{u:03d}_semilla{config['semillas'][0]}"))
        filas_t["final"] = json.loads((registro / "registro.json").read_text(encoding="utf-8"))["tramos"]
        tramos[str(h)] = filas_t
    salida = dict(
        generado_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        seleccionada=config["seleccionada"], unidades_final=config["unidades"], semillas=config["semillas"],
        tasa=config["tasa_aprendizaje"], cortes_validacion=list(CORTES), horizontes=list(HORIZONTES),
        familias=familias, referencia_futuros_validacion=ref_futuros, validacion=validacion,
        margenes={m["arquitectura"] + "_" + str(m["horizonte"]): dict(margen=R(m["margen"], 3), cobertura=m["cobertura_por_corte"])
                  for m in margenes["margenes"].values()},
        tramos=tramos, test=dict(tabla=filas_test, series=test_series))
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{DESTINO} ({DESTINO.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
