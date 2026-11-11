"""Figuras de la validación anual de cada familia de réplicas promediadas.

Para cada familia de scripts/evaluate_seed_ensemble.py, promedia las semillas con los tamaños elegidos
por la regla del protocolo y guarda seis figuras en reports/figuras/<experimentos>/validacion/.
La arquitectura principal de cada familia es la que elige la regla dentro de ella (mejor puntuación;
a un punto o menos, la de menor tiempo). El margen del intervalo es el percentil 80 de los errores
absolutos de la predicción promediada. Se muestran las dos referencias: el ingenuo del protocolo y el
ingenuo con futuros. Solo lee validación; no entrena ni consulta el test.
"""

import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scripts.evaluate_seed_ensemble import FAMILIAS, cargar, ingenuo_futuros
from scripts.evaluate_validation_uncertainty import ARQUITECTURAS, CORTES, mejora
from scripts.prepare_windows import HORIZONTES, ROOT

CARPETAS = {"precio": "E1", "cambio": "E2-E4", "porcentaje": "E5-E7", "cambio_tasa_menor": "E2-E4_E8-E10",
            "variaciones": "E11-E13", "futuros": "E14-E16"}
# Paleta categórica de referencia (orden fijo) y tintas neutras para las dos referencias.
COLORES = {"GRU": "#2a78d6", "LSTM": "#eb6834", "RNN": "#1baf7a", "Ingenuo": "#898781", "Ingenuo con futuros": "#52514e"}
TINTA, TINTA_2, REJILLA, BASE = "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7"
FUERA = "#e34948"
NIVEL = 80

plt.rcParams.update({
    "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb", "axes.edgecolor": BASE,
    "axes.labelcolor": TINTA_2, "xtick.color": TINTA_2, "ytick.color": TINTA_2, "text.color": TINTA,
    "axes.grid": True, "grid.color": REJILLA, "grid.linewidth": 0.6, "axes.spines.top": False,
    "axes.spines.right": False, "font.size": 9, "axes.titlesize": 10, "legend.frameon": False,
    "lines.linewidth": 1.4,
})


def promediadas(familia, futuros):
    """Predicción promediada por fecha para cada arquitectura y horizonte con el tamaño elegido."""
    predicciones, tiempos = cargar(familia)
    tablas, tamanos, puntuaciones = {}, {}, {}
    for a in ARQUITECTURAS:
        anuales_sel = []
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
                    base["prediccion_ingenua_futuros"] = futuros.reindex(base.fecha_origen.astype(str)).to_numpy()
                    base["corte"] = c
                    partes.append(base)
                tabla = pd.concat(partes, ignore_index=True)
                if tabla.prediccion_ingenua_futuros.isna().any():
                    raise ValueError("Falta el ingenuo con futuros en un origen de validación.")
                for col in ("fecha_origen", "fecha_objetivo"):
                    tabla[col] = pd.to_datetime(tabla[col])
                tabla["error"] = (tabla.prediccion - tabla.brent_objetivo).abs()
                tabla["error_ingenuo"] = (tabla.prediccion_ingenua - tabla.brent_objetivo).abs()
                tabla["error_futuros"] = (tabla.prediccion_ingenua_futuros - tabla.brent_objetivo).abs()
                anuales = [mejora(g.error.to_numpy(), g.error_ingenuo.to_numpy()) for _, g in tabla.groupby("corte")]
                por_tamano[u] = (np.mean(anuales), anuales, tabla)
            u = 32 if por_tamano[32][0] >= por_tamano[64][0] else 64
            tablas[a, h], tamanos[a, h] = por_tamano[u][2], u
            anuales_sel += por_tamano[u][1]
        puntuaciones[a] = np.mean(anuales_sel)
    mejor = max(puntuaciones, key=puntuaciones.get)
    principal = min((a for a in ARQUITECTURAS if puntuaciones[mejor] - puntuaciones[a] <= 1), key=tiempos.get)
    return tablas, tamanos, puntuaciones, principal


def guardar(fig, carpeta, nombre):
    fig.savefig(carpeta / nombre, dpi=150, bbox_inches="tight")
    plt.close(fig)


def fechas_eje(ax):
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))


def figuras(familia, futuros):
    carpeta = ROOT / "reports/figuras" / CARPETAS[familia] / "validacion"
    carpeta.mkdir(parents=True, exist_ok=True)
    tablas, tamanos, puntuaciones, principal = promediadas(familia, futuros)
    margenes = {k: float(np.percentile(t.error, NIVEL)) for k, t in tablas.items()}
    semillas = len(FAMILIAS[familia][HORIZONTES[0]])
    media = "media de 3 semillas" if semillas > 1 else "una semilla"
    resumen = dibujar(tablas, tamanos, principal, margenes, carpeta, f"Validación {CARPETAS[familia]} ({familia})", media)
    print(f"{CARPETAS[familia]} ({familia}): principal {principal}; puntuación "
          + ", ".join(f"{a} {v:+.2f} %" for a, v in puntuaciones.items()))
    print("  márgenes P80 " + ", ".join(f"+{h} ±{margenes[principal, h]:.2f}" for h in HORIZONTES)
          + f"; dirección: {'; '.join(resumen)}")
    print(f"  {carpeta}")


def dibujar(tablas, tamanos, principal, margenes, carpeta, titulo, media):
    """Seis figuras a partir de tablas por (arquitectura, horizonte) con la columna `corte` como periodo.

    Las tablas llevan fecha_origen, fecha_objetivo, brent_objetivo, prediccion_ingenua,
    prediccion_ingenua_futuros, prediccion y los errores absolutos error, error_ingenuo y error_futuros.
    `margenes` da el margen del intervalo por (arquitectura, horizonte). Devuelve el resumen de dirección.
    """
    carpeta.mkdir(parents=True, exist_ok=True)

    etiqueta = lambda a, h: f"{a} ({tamanos[a, h]} u)"

    # 1. Precio real frente a previsto con la banda del intervalo (arquitectura principal).
    fig, ejes = plt.subplots(len(HORIZONTES), 1, figsize=(10, 9), sharex=True)
    for ax, h in zip(ejes, HORIZONTES):
        t, m = tablas[principal, h].sort_values("fecha_objetivo"), margenes[principal, h]
        for _, g in t.groupby("corte"):
            ax.fill_between(g.fecha_objetivo, g.prediccion - m, g.prediccion + m, color=COLORES[principal],
                            alpha=0.15, linewidth=0)
            ax.plot(g.fecha_objetivo, g.brent_objetivo, color=TINTA, linewidth=1.2)
            ax.plot(g.fecha_objetivo, g.prediccion, color=COLORES[principal], linewidth=1.2)
        ax.set_title(f"+{h} fechas · {etiqueta(principal, h)} · banda ±{m:.1f} USD", loc="left")
        ax.set_ylabel("USD/barril")
        fechas_eje(ax)
    ejes[0].legend(handles=[plt.Line2D([], [], color=TINTA, label="Brent real"),
                            plt.Line2D([], [], color=COLORES[principal], label=f"Previsión ({media})"),
                            plt.Rectangle((0, 0), 1, 1, color=COLORES[principal], alpha=0.15, label="Intervalo 80 %")],
                   loc="upper left", ncol=3)
    ejes[-1].set_xlabel("Fecha objetivo")
    fig.suptitle(f"{titulo}: precio real frente a previsto", x=0.01, ha="left", fontsize=12)
    guardar(fig, carpeta, "01_real_vs_previsto.png")

    # 2. Error acumulado de cada red y del ingenuo con futuros menos el del ingenuo.
    fig, ejes = plt.subplots(len(HORIZONTES), 1, figsize=(10, 9), sharex=True)
    for ax, h in zip(ejes, HORIZONTES):
        for a in ARQUITECTURAS:
            t = tablas[a, h].sort_values("fecha_origen")
            ax.plot(t.fecha_origen, (t.error - t.error_ingenuo).cumsum(), color=COLORES[a], label=etiqueta(a, h))
        t = tablas[principal, h].sort_values("fecha_origen")
        ax.plot(t.fecha_origen, (t.error_futuros - t.error_ingenuo).cumsum(), color=COLORES["Ingenuo con futuros"],
                linestyle="--", label="Ingenuo con futuros")
        ax.axhline(0, color=BASE, linewidth=1)
        ax.set_title(f"+{h} fechas · por debajo de 0, menos error acumulado que el ingenuo", loc="left")
        ax.set_ylabel("USD acumulados")
        ax.legend(loc="best", ncol=4)
        fechas_eje(ax)
    ejes[-1].set_xlabel("Fecha de origen")
    fig.suptitle(f"{titulo}: error absoluto acumulado menos el del ingenuo", x=0.01, ha="left", fontsize=12)
    guardar(fig, carpeta, "02_error_acumulado.png")

    # 3. MAE por año y horizonte.
    fig, ejes = plt.subplots(1, len(HORIZONTES), figsize=(13, 4))
    series = [*ARQUITECTURAS[::-1], "Ingenuo con futuros", "Ingenuo"]
    columna = {"Ingenuo": "error_ingenuo", "Ingenuo con futuros": "error_futuros"}
    ancho = 0.8 / len(series)
    for ax, h in zip(ejes, HORIZONTES):
        # Cada horizonte tiene sus propios periodos (en test, +252 termina antes que +5).
        periodos = sorted(tablas[principal, h].corte.unique())
        for i, s in enumerate(series):
            t = tablas[s, h] if s in ARQUITECTURAS else tablas[principal, h]
            valores = t.groupby("corte")[columna.get(s, "error")].mean().reindex(periodos)
            ax.bar(np.arange(len(periodos)) + (i - (len(series) - 1) / 2) * ancho, valores.to_numpy(), ancho * 0.9,
                   color=COLORES[s], label=etiqueta(s, h) if s in ARQUITECTURAS else s)
        ax.set_xticks(np.arange(len(periodos)), [str(c) for c in periodos])
        ax.set_title(f"+{h} fechas", loc="left")
        ax.grid(axis="x", visible=False)
    ejes[0].set_ylabel("MAE (USD/barril)")
    ejes[0].legend(loc="upper left", fontsize=7)
    fig.suptitle(f"{titulo}: MAE por año", x=0.01, ha="left", fontsize=12)
    guardar(fig, carpeta, "03_mae_por_anio.png")

    # 4. Cambio previsto frente a cambio real (respecto al último spot admisible).
    fig, ejes = plt.subplots(1, len(HORIZONTES), figsize=(12, 4.2))
    for ax, h in zip(ejes, HORIZONTES):
        t = tablas[principal, h]
        real, previsto = t.brent_objetivo - t.prediccion_ingenua, t.prediccion - t.prediccion_ingenua
        limite = float(np.nanmax(np.abs(real))) * 1.05
        ax.scatter(real, previsto, s=8, color=COLORES[principal], alpha=0.35, linewidths=0)
        ax.plot([-limite, limite], [-limite, limite], color=BASE, linewidth=1)
        ax.axhline(0, color=BASE, linewidth=0.8)
        ax.axvline(0, color=BASE, linewidth=0.8)
        ax.set_xlim(-limite, limite)
        ax.set_ylim(-limite, limite)
        ax.set_aspect("equal")
        correlacion = np.corrcoef(real, previsto)[0, 1] if previsto.std() > 0 else float("nan")
        ax.set_title(f"+{h} · {etiqueta(principal, h)} · r = {correlacion:.2f}", loc="left")
        ax.set_xlabel("Cambio real (USD)")
    ejes[0].set_ylabel("Cambio previsto (USD)")
    fig.suptitle(f"{titulo}: cambio previsto frente a real (diagonal = acierto perfecto)",
                 x=0.01, ha="left", fontsize=12)
    guardar(fig, carpeta, "04_cambio_previsto_vs_real.png")

    # 5. Cobertura del intervalo a lo largo del tiempo.
    fig, ejes = plt.subplots(len(HORIZONTES), 1, figsize=(10, 7), sharex=True)
    for ax, h in zip(ejes, HORIZONTES):
        t = tablas[principal, h].sort_values("fecha_origen")
        dentro = t.error <= margenes[principal, h]
        for _, g in t.assign(dentro=dentro).groupby("corte"):
            ax.plot(g.fecha_origen, g.dentro.rolling(63, min_periods=20).mean() * 100, color=COLORES[principal])
            fuera = g.loc[~g.dentro]
            ax.scatter(fuera.fecha_origen, np.full(len(fuera), 2), s=6, color=FUERA, linewidths=0)
        ax.axhline(NIVEL, color=TINTA_2, linewidth=1, linestyle="--")
        ax.set_ylim(0, 105)
        ax.set_title(f"+{h} · cobertura total {100 * dentro.mean():.0f} % · puntos: precio fuera del intervalo", loc="left")
        ax.set_ylabel("% en 63 orígenes")
        fechas_eje(ax)
    ejes[-1].set_xlabel("Fecha de origen")
    fig.suptitle(f"{titulo}: cobertura móvil del intervalo 80 % ({principal})", x=0.01, ha="left", fontsize=12)
    guardar(fig, carpeta, "05_cobertura_intervalo.png")

    # 6. Dirección: matriz de confusión sube/baja respecto al último spot admisible.
    fig, ejes = plt.subplots(1, len(HORIZONTES), figsize=(12, 3.8))
    resumen = []
    for ax, h in zip(ejes, HORIZONTES):
        t = tablas[principal, h]
        real = np.sign(t.brent_objetivo - t.prediccion_ingenua)
        validos = real != 0
        aciertos = {}
        for nombre, columna_pred in [(a, None) for a in ARQUITECTURAS] + [("Ingenuo con futuros", "prediccion_ingenua_futuros")]:
            tt = tablas[nombre, h] if columna_pred is None else t
            previsto = np.sign(tt[columna_pred or "prediccion"] - tt.prediccion_ingenua)
            aciertos[nombre] = 100 * np.mean(previsto[validos] == real[validos])
        previsto = np.sign(t.prediccion - t.prediccion_ingenua)
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
        ax.set_title(f"+{h} · acierto {aciertos[principal]:.0f} % · con futuros {aciertos['Ingenuo con futuros']:.0f} %",
                     loc="left")
        resumen.append(f"+{h} " + ", ".join(f"{k} {v:.0f} %" for k, v in aciertos.items()))
    ejes[0].set_ylabel("Previsto")
    fig.suptitle(f"{titulo}: dirección prevista frente a real ({principal})", x=0.01, ha="left", fontsize=12)
    guardar(fig, carpeta, "06_direccion.png")
    return resumen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--familia", choices=[*FAMILIAS, "todas"], default="todas")
    familia = parser.parse_args().familia
    futuros = ingenuo_futuros()
    for f in (FAMILIAS if familia == "todas" else [familia]):
        figuras(f, futuros)


if __name__ == "__main__":
    main()
