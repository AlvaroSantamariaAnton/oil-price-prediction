"""Figuras de la validación anual de una familia de réplicas promediadas.

Lee las predicciones guardadas de la familia (por defecto `variaciones`, E11–E13), promedia las
semillas con los tamaños elegidos por la regla del protocolo y guarda las figuras en
reports/figuras/<E primero-E último>/validacion/. Solo lee validación; no entrena ni consulta el test.
"""

import argparse
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scripts.evaluate_seed_ensemble import FAMILIAS, cargar
from scripts.evaluate_validation_uncertainty import ARQUITECTURAS, CORTES, mejora
from scripts.prepare_windows import HORIZONTES, ROOT

# Paleta categórica de referencia (orden fijo) y tintas neutras.
COLORES = {"GRU": "#2a78d6", "LSTM": "#eb6834", "RNN": "#1baf7a", "Ingenuo": "#898781"}
TINTA, TINTA_2, REJILLA, BASE = "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7"
FUERA = "#e34948"
PRINCIPAL = "GRU"

plt.rcParams.update({
    "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb", "axes.edgecolor": BASE,
    "axes.labelcolor": TINTA_2, "xtick.color": TINTA_2, "ytick.color": TINTA_2, "text.color": TINTA,
    "axes.grid": True, "grid.color": REJILLA, "grid.linewidth": 0.6, "axes.spines.top": False,
    "axes.spines.right": False, "font.size": 9, "axes.titlesize": 10, "legend.frameon": False,
    "lines.linewidth": 1.4,
})


def promediadas(familia):
    """Predicción promediada por fecha para cada arquitectura y horizonte con el tamaño elegido."""
    predicciones, _ = cargar(familia)
    tablas, tamanos = {}, {}
    for a in ARQUITECTURAS:
        for h in HORIZONTES:
            replicas = FAMILIAS[familia][h]
            por_tamano = {}
            for u in (32, 64):
                partes = []
                for c in CORTES:
                    bloque = [predicciones[e, a, h, u, c] for e in replicas]
                    base = bloque[0][["fecha_origen", "fecha_objetivo", "brent_objetivo", "prediccion_ingenua"]].copy()
                    for p in bloque[1:]:
                        if not p.fecha_origen.equals(base.fecha_origen):
                            raise ValueError("Las réplicas no comparten fechas.")
                    base["prediccion"] = np.mean([p.prediccion_red.to_numpy() for p in bloque], axis=0)
                    base["corte"] = c
                    partes.append(base)
                tabla = pd.concat(partes, ignore_index=True)
                for col in ("fecha_origen", "fecha_objetivo"):
                    tabla[col] = pd.to_datetime(tabla[col])
                tabla["error"] = (tabla.prediccion - tabla.brent_objetivo).abs()
                tabla["error_ingenuo"] = (tabla.prediccion_ingenua - tabla.brent_objetivo).abs()
                media = np.mean([mejora(g.error.to_numpy(), g.error_ingenuo.to_numpy()) for _, g in tabla.groupby("corte")])
                por_tamano[u] = (media, tabla)
            u = 32 if por_tamano[32][0] >= por_tamano[64][0] else 64
            tablas[a, h], tamanos[a, h] = por_tamano[u][1], u
    return tablas, tamanos


def guardar(fig, carpeta, nombre):
    fig.savefig(carpeta / nombre, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(carpeta / nombre)


def fechas_eje(ax):
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--familia", choices=FAMILIAS, default="variaciones")
    familia = parser.parse_args().familia
    replicas = sorted({e for r in FAMILIAS[familia].values() for e in r}, key=lambda e: int(e[1:]))
    carpeta = ROOT / "reports/figuras" / f"{replicas[0]}-{replicas[-1]}" / "validacion"
    carpeta.mkdir(parents=True, exist_ok=True)
    tablas, tamanos = promediadas(familia)
    margenes = None
    ruta_margenes = ROOT / "reports/margenes_validacion.json"
    if ruta_margenes.exists():
        datos = json.loads(ruta_margenes.read_text(encoding="utf-8"))
        if datos["familia"] == familia:
            margenes = {(m["arquitectura"], m["horizonte"]): m["margen"] for m in datos["margenes"].values()}
    etiqueta = lambda a, h: f"{a} ({tamanos[a, h]} u)"

    # 1. Precio real frente a previsto con la banda del intervalo (arquitectura principal).
    fig, ejes = plt.subplots(len(HORIZONTES), 1, figsize=(10, 9), sharex=True)
    for ax, h in zip(ejes, HORIZONTES):
        t = tablas[PRINCIPAL, h].sort_values("fecha_objetivo")
        for _, g in t.groupby("corte"):
            if margenes:
                m = margenes[PRINCIPAL, h]
                ax.fill_between(g.fecha_objetivo, g.prediccion - m, g.prediccion + m, color=COLORES[PRINCIPAL],
                                alpha=0.15, linewidth=0)
            ax.plot(g.fecha_objetivo, g.brent_objetivo, color=TINTA, linewidth=1.2)
            ax.plot(g.fecha_objetivo, g.prediccion, color=COLORES[PRINCIPAL], linewidth=1.2)
        ax.set_title(f"+{h} fechas · {etiqueta(PRINCIPAL, h)}" + (f" · banda ±{margenes[PRINCIPAL, h]:.1f} USD" if margenes else ""),
                     loc="left")
        ax.set_ylabel("USD/barril")
        fechas_eje(ax)
    ejes[0].legend(handles=[plt.Line2D([], [], color=TINTA, label="Brent real"),
                            plt.Line2D([], [], color=COLORES[PRINCIPAL], label="Previsión (media de 3 semillas)")]
                   + ([plt.Rectangle((0, 0), 1, 1, color=COLORES[PRINCIPAL], alpha=0.15, label="Intervalo 80 %")] if margenes else []),
                   loc="upper left", ncol=3)
    ejes[-1].set_xlabel("Fecha objetivo")
    fig.suptitle("Validación: precio real frente a previsto", x=0.01, ha="left", fontsize=12)
    guardar(fig, carpeta, "01_real_vs_previsto.png")

    # 2. Error acumulado de cada red menos el del ingenuo.
    fig, ejes = plt.subplots(len(HORIZONTES), 1, figsize=(10, 9), sharex=True)
    for ax, h in zip(ejes, HORIZONTES):
        for a in ARQUITECTURAS:
            t = tablas[a, h].sort_values("fecha_origen")
            ax.plot(t.fecha_origen, (t.error - t.error_ingenuo).cumsum(), color=COLORES[a], label=etiqueta(a, h))
        ax.axhline(0, color=BASE, linewidth=1)
        ax.set_title(f"+{h} fechas · por debajo de 0, la red acumula menos error que el ingenuo", loc="left")
        ax.set_ylabel("USD acumulados")
        ax.legend(loc="best", ncol=3)
        fechas_eje(ax)
    ejes[-1].set_xlabel("Fecha de origen")
    fig.suptitle("Validación: error absoluto acumulado de la red menos el del ingenuo", x=0.01, ha="left", fontsize=12)
    guardar(fig, carpeta, "02_error_acumulado.png")

    # 3. MAE por año y horizonte.
    fig, ejes = plt.subplots(1, len(HORIZONTES), figsize=(12, 4))
    series = [*ARQUITECTURAS[::-1], "Ingenuo"]
    ancho = 0.8 / len(series)
    for ax, h in zip(ejes, HORIZONTES):
        for i, s in enumerate(series):
            t = tablas[PRINCIPAL if s == "Ingenuo" else s, h]
            valores = t.groupby("corte")["error_ingenuo" if s == "Ingenuo" else "error"].mean()
            ax.bar(np.arange(len(CORTES)) + (i - (len(series) - 1) / 2) * ancho, valores.to_numpy(), ancho * 0.9,
                   color=COLORES[s], label=s if s == "Ingenuo" else etiqueta(s, h))
        ax.set_xticks(np.arange(len(CORTES)), [str(c) for c in CORTES])
        ax.set_title(f"+{h} fechas", loc="left")
        ax.grid(axis="x", visible=False)
    ejes[0].set_ylabel("MAE (USD/barril)")
    ejes[0].legend(loc="upper left", fontsize=8)
    fig.suptitle("Validación: MAE por año", x=0.01, ha="left", fontsize=12)
    guardar(fig, carpeta, "03_mae_por_anio.png")

    # 4. Cambio previsto frente a cambio real.
    fig, ejes = plt.subplots(1, len(HORIZONTES), figsize=(12, 4.2))
    for ax, h in zip(ejes, HORIZONTES):
        t = tablas[PRINCIPAL, h]
        real, previsto = t.brent_objetivo - t.prediccion_ingenua, t.prediccion - t.prediccion_ingenua
        limite = float(np.nanmax(np.abs(real))) * 1.05
        ax.scatter(real, previsto, s=8, color=COLORES[PRINCIPAL], alpha=0.35, linewidths=0)
        ax.plot([-limite, limite], [-limite, limite], color=BASE, linewidth=1)
        ax.axhline(0, color=BASE, linewidth=0.8)
        ax.axvline(0, color=BASE, linewidth=0.8)
        ax.set_xlim(-limite, limite)
        ax.set_ylim(-limite, limite)
        ax.set_aspect("equal")
        correlacion = np.corrcoef(real, previsto)[0, 1]
        ax.set_title(f"+{h} · {etiqueta(PRINCIPAL, h)} · r = {correlacion:.2f}", loc="left")
        ax.set_xlabel("Cambio real (USD)")
    ejes[0].set_ylabel("Cambio previsto (USD)")
    fig.suptitle("Validación: cambio previsto frente a cambio real (diagonal = acierto perfecto)", x=0.01, ha="left", fontsize=12)
    guardar(fig, carpeta, "04_cambio_previsto_vs_real.png")

    # 5. Cobertura del intervalo a lo largo del tiempo.
    if margenes:
        fig, ejes = plt.subplots(len(HORIZONTES), 1, figsize=(10, 7), sharex=True)
        for ax, h in zip(ejes, HORIZONTES):
            t = tablas[PRINCIPAL, h].sort_values("fecha_origen")
            dentro = t.error <= margenes[PRINCIPAL, h]
            for _, g in t.assign(dentro=dentro).groupby("corte"):
                movil = g.dentro.rolling(63, min_periods=20).mean() * 100
                ax.plot(g.fecha_origen, movil, color=COLORES[PRINCIPAL])
                fuera = g.loc[~g.dentro]
                ax.scatter(fuera.fecha_origen, np.full(len(fuera), 2), s=6, color=FUERA, linewidths=0)
            ax.axhline(80, color=TINTA_2, linewidth=1, linestyle="--")
            ax.set_ylim(0, 105)
            ax.set_title(f"+{h} · cobertura total {100 * dentro.mean():.0f} % · puntos: precio fuera del intervalo", loc="left")
            ax.set_ylabel("% en 63 orígenes")
            fechas_eje(ax)
        ejes[-1].set_xlabel("Fecha de origen")
        fig.suptitle(f"Validación: cobertura móvil del intervalo 80 % ({PRINCIPAL})", x=0.01, ha="left", fontsize=12)
        guardar(fig, carpeta, "05_cobertura_intervalo.png")

    # 6. Dirección: matriz de confusión sube/baja.
    fig, ejes = plt.subplots(1, len(HORIZONTES), figsize=(12, 3.8))
    for ax, h in zip(ejes, HORIZONTES):
        t = tablas[PRINCIPAL, h]
        real = np.sign(t.brent_objetivo - t.prediccion_ingenua)
        previsto = np.sign(t.prediccion - t.prediccion_ingenua)
        validos = (real != 0) & (previsto != 0)
        matriz = np.array([[np.sum(validos & (previsto == p) & (real == r)) for r in (1, -1)] for p in (1, -1)])
        ax.imshow(matriz, cmap="Blues", vmin=0)
        for i in range(2):
            for j in range(2):
                ax.text(j, i, matriz[i, j], ha="center", va="center",
                        color="#ffffff" if matriz[i, j] > matriz.max() / 2 else TINTA)
        ax.set_xticks([0, 1], ["Sube", "Baja"])
        ax.set_yticks([0, 1], ["Sube", "Baja"])
        ax.set_xlabel("Real")
        ax.grid(False)
        acierto = np.trace(matriz) / matriz.sum()
        sube = (real[validos] > 0).mean()
        ax.set_title(f"+{h} · acierto {100 * acierto:.0f} % · real sube {100 * sube:.0f} %", loc="left")
        otros = ", ".join(f"{a} {100 * np.mean(np.sign(tablas[a, h].prediccion - tablas[a, h].prediccion_ingenua)[validos] == real[validos]):.0f} %"
                          for a in ARQUITECTURAS if a != PRINCIPAL)
        print(f"+{h}: acierto direccional {PRINCIPAL} {100 * acierto:.1f} % ({otros}); proporción real al alza {100 * sube:.1f} %")
    ejes[0].set_ylabel("Previsto")
    fig.suptitle(f"Validación: dirección prevista frente a real ({PRINCIPAL})", x=0.01, ha="left", fontsize=12)
    guardar(fig, carpeta, "06_direccion.png")


if __name__ == "__main__":
    main()
