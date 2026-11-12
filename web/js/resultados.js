// Página «Resultados del test».
const PREDICTORES = ["Ingenuo", "Ingenuo con futuros", "RNN", "LSTM", "GRU"];
const COLOR_PRED = { "Ingenuo": "ingenuo", "Ingenuo con futuros": "futuros", RNN: "RNN", LSTM: "LSTM", GRU: "GRU" };
const OPCIONES_H = [["5", "1 semana"], ["63", "3 meses"], ["252", "1 año"]];

document.addEventListener("DOMContentLoaded", async () => {
  const e = await cargarJSON(URL_ESTUDIO);
  const fila = (h, p) => e.test.tabla.find((f) => f.horizonte === Number(h) && f.predictor === p);
  pintarReferencias(document.getElementById("referencias"), {
    futuros: ` En el test, a una semana, mejora al ingenuo un ${fmt(fila(5, "Ingenuo con futuros").mejora_frente_ingenuo, 1)} % sin ninguna red.`,
  });
  pintarKpis(e, fila);
  pintarSerie(e);
  pintarAcumulado(e);
  pintarTabla(e, fila);
  pintarAnual(e, fila);
  pintarValTest(e, fila);
});

function pintarKpis(e, fila) {
  const sel = e.seleccionada;
  document.getElementById("kpis").innerHTML = e.horizontes.map((h) => {
    const red = fila(h, sel), fut = fila(h, "Ingenuo con futuros");
    return `<article class="tarjeta">
      <p class="etiqueta">${NOMBRES_HORIZONTE[h]} · ${red.n} previsiones</p>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div><div class="pequeno mutado">${sel} frente al ingenuo</div><div class="cifra-media num ${claseSigno(red.mejora_frente_ingenuo)}">${fmtPct(red.mejora_frente_ingenuo)}</div></div>
        <div><div class="pequeno mutado">${sel} frente al ingenuo con futuros</div><div class="cifra-media num ${claseSigno(red.mejora_frente_futuros)}">${fmtPct(red.mejora_frente_futuros)}</div></div>
      </div>
      <p class="pequeno mutado" style="margin:12px 0 0">Ingenuo con futuros frente al ingenuo: <b class="${claseSigno(fut.mejora_frente_ingenuo)}">${fmtPct(fut.mejora_frente_ingenuo)}</b>.
        Error medio de la red: ${fmtUSD(red.mae)}.</p>
    </article>`;
  }).join("");
  const r5 = fila(5, sel), f5 = fila(5, "Ingenuo con futuros");
  document.getElementById("veredicto").innerHTML = `<p><strong>Veredicto:</strong> a una semana, la ${sel} reduce el error del
    ingenuo un ${fmt(r5.mejora_frente_ingenuo, 1)} %, pero actualizar el último spot con los futuros lo reduce un
    ${fmt(f5.mejora_frente_ingenuo, 1)} % sin ninguna red; frente a esa regla, la red queda un ${fmt(-r5.mejora_frente_futuros, 1)} % por
    debajo (p = ${fmt(r5.p_dm_frente_futuros, 3)}). A tres meses y a un año no mejora de forma fiable a ninguna de las dos referencias.</p>`;
}

function serieDe(e, h) { return e.test.series[h]; }

function pintarSerie(e) {
  let h = "5";
  const activos = new Set(["real", e.seleccionada, "futuros"]);
  const opciones = [["real", "Brent real"], ["RNN", "RNN"], ["LSTM", "LSTM"], ["GRU", "GRU"], ["futuros", "Ingenuo con futuros"], ["ingenuo", "Ingenuo"], ["banda", `Intervalo 80 % (${e.seleccionada})`]];
  activos.add("banda");
  const casillas = document.getElementById("casillas-serie");
  const pintarCasillas = () => {
    const c = VAR;
    const color = { real: c.real, RNN: c.RNN, LSTM: c.LSTM, GRU: c.GRU, futuros: c.futuros, ingenuo: c.ingenuo, banda: c[e.seleccionada] };
    casillas.innerHTML = opciones.map(([k, t]) => `<label><input type="checkbox" value="${k}" ${activos.has(k) ? "checked" : ""}>
      <i style="width:10px;height:10px;border-radius:50%;display:inline-block;background:${color[k]}${k === "banda" ? ";opacity:.4" : ""}"></i>${t}</label>`).join("");
  };
  pintarCasillas();
  casillas.addEventListener("change", (ev) => {
    if (ev.target.checked) activos.add(ev.target.value); else activos.delete(ev.target.value);
    entrada.grafica.setOption(construir(), true);
  });
  segmentado(document.getElementById("selector-h-serie"), OPCIONES_H, (v) => { h = v; entrada.grafica.setOption(construir(), true); notas(); }, h);
  const notas = () => {
    document.getElementById("nota-serie").textContent = `Cada punto es la previsión hecha en un origen y se dibuja en su fecha objetivo (${DESCRIPCION_HORIZONTE[h]}). ` +
      `${serieDe(e, h).origen.length} orígenes entre el ${fmtFecha(serieDe(e, h).origen[0])} y el ${fmtFecha(serieDe(e, h).origen.at(-1))}. Desliza la barra inferior para acercarte.`;
  };
  notas();
  const construir = () => {
    const c = colores();
    const s = serieDe(e, h);
    const m = e.margenes[`${e.seleccionada}_${h}`].margen;
    const pares = (campo) => s.objetivo.map((d, i) => [d, s[campo][i]]);
    const series = [];
    if (activos.has("banda")) {
      series.push(
        { name: "base", type: "line", data: s.objetivo.map((d, i) => [d, s[e.seleccionada][i] - m]), showSymbol: false, lineStyle: { opacity: 0 }, stack: "banda", silent: true, tooltip: { show: false } },
        { name: "Intervalo", type: "line", data: s.objetivo.map((d) => [d, 2 * m]), showSymbol: false, lineStyle: { opacity: 0 }, stack: "banda", areaStyle: { color: c[e.seleccionada], opacity: .14 }, silent: true, tooltip: { show: false } },
      );
    }
    const definicion = [
      ["ingenuo", "Ingenuo", c.ingenuo, 1.2], ["futuros", "Ingenuo con futuros", c.futuros, 1.2],
      ["LSTM", "LSTM", c.LSTM, 1.3], ["GRU", "GRU", c.GRU, 1.3], ["RNN", "RNN", c.RNN, 1.6], ["real", "Brent real", c.real, 1.8],
    ];
    for (const [k, nombre, color, ancho] of definicion) {
      if (activos.has(k)) series.push({ name: nombre, type: "line", data: pares(k), showSymbol: false, sampling: "lttb", lineStyle: { width: ancho, color }, itemStyle: { color } });
    }
    return {
      ...baseOpciones(),
      grid: { left: 52, right: 20, top: 24, bottom: 84 },
      tooltip: {
        ...baseOpciones().tooltip,
        formatter: (ps) => {
          const i = ps[0].dataIndex;
          return `<div style="color:${c.tinta3};margin-bottom:4px">Objetivo ${fmtFecha(s.objetivo[i])} · hecha el ${fmtFecha(s.origen[i])}</div>` +
            ps.filter((x) => !["base", "Intervalo"].includes(x.seriesName)).map((x) => lineaTooltip(x.color, x.seriesName, fmtUSD(x.value[1]))).join("");
        },
      },
      xAxis: ejeTiempo(),
      yAxis: ejeValor({ name: "USD/barril" }),
      dataZoom: [
        { type: "inside", zoomOnMouseWheel: "ctrl", moveOnMouseWheel: false },
        { type: "slider", height: 26, bottom: 18, borderColor: c.rejilla, fillerColor: c.acentoSuave, handleStyle: { color: c.acento, borderColor: c.acento }, textStyle: { color: c.tinta3 }, dataBackground: { lineStyle: { color: c.tinta3 }, areaStyle: { color: c.rejilla } } },
      ],
      series,
    };
  };
  const entrada = crearGrafica(document.getElementById("grafica-serie"), construir);
}

function pintarAcumulado(e) {
  let h = "5";
  segmentado(document.getElementById("selector-h-acumulado"), OPCIONES_H, (v) => { h = v; entrada.grafica.setOption(construir(), true); }, h);
  const c0 = VAR;
  document.getElementById("leyenda-acumulado").innerHTML = ["RNN", "LSTM", "GRU"].map((a) => `<span><i style="background:${c0[a]}"></i>${a}</span>`).join("") +
    `<span><i style="background:${c0.futuros}"></i>Ingenuo con futuros</span>`;
  const construir = () => {
    const c = colores();
    const s = serieDe(e, h);
    const acumulado = (campo) => {
      let suma = 0;
      return s.origen.map((d, i) => { suma += Math.abs(s[campo][i] - s.real[i]) - Math.abs(s.ingenuo[i] - s.real[i]); return [d, +suma.toFixed(2)]; });
    };
    return {
      ...baseOpciones(),
      grid: { left: 60, right: 20, top: 24, bottom: 40 },
      tooltip: {
        ...baseOpciones().tooltip,
        formatter: (ps) => `<div style="color:${c.tinta3};margin-bottom:4px">${fmtFecha(String(ps[0].value[0]).slice(0, 10))}</div>` +
          ps.map((x) => lineaTooltip(x.color, x.seriesName, `${fmtSigno(x.value[1], 0)} USD`)).join(""),
      },
      xAxis: ejeTiempo(),
      yAxis: ejeValor({ name: "USD acumulados", scale: false }),
      series: [
        ...["RNN", "LSTM", "GRU"].map((a) => ({ name: a, type: "line", data: acumulado(a), showSymbol: false, lineStyle: { width: 1.8, color: c[a] }, itemStyle: { color: c[a] } })),
        {
          name: "Ingenuo con futuros", type: "line", data: acumulado("futuros"), showSymbol: false, lineStyle: { width: 1.8, color: c.futuros, type: [6, 4] }, itemStyle: { color: c.futuros },
          markLine: { silent: true, symbol: "none", label: { show: false }, data: [{ yAxis: 0, lineStyle: { color: c.tinta3, width: 1, type: "solid" } }] },
        },
      ],
    };
  };
  const entrada = crearGrafica(document.getElementById("grafica-acumulado"), construir);
}

function pintarTabla(e, fila) {
  let h = "5";
  const ic = (v) => v ? `<span class="mutado">[${fmt(v[0], 1)}; ${fmt(v[1], 1)}]</span>` : "";
  const p = (v) => v == null ? "" : `<span class="mutado"> · p ${v < 0.001 ? "< 0,001" : fmt(v, 3)}</span>`;
  const pintar = () => {
    const filas = PREDICTORES.map((nombre) => {
      const f = fila(h, nombre);
      const clase = nombre === e.seleccionada ? "destacada" : "";
      return `<tr class="${clase}">
        <td><span class="marca-serie" style="background:var(--${COLOR_PRED[nombre].toLowerCase()})"></span>${nombre}${nombre === e.seleccionada ? " · seleccionada" : ""}</td>
        <td class="num">${fmt(f.mae)}</td><td class="num">${fmt(f.rmse)}</td>
        <td class="num"><span class="${claseSigno(f.mejora_frente_ingenuo)}">${nombre === "Ingenuo" ? "—" : fmtPct(f.mejora_frente_ingenuo)}</span> ${ic(f.ic95_frente_ingenuo)}${p(f.p_dm_frente_ingenuo)}</td>
        <td class="num"><span class="${claseSigno(f.mejora_frente_futuros)}">${nombre === "Ingenuo con futuros" ? "—" : fmtPct(f.mejora_frente_futuros)}</span> ${ic(f.ic95_frente_futuros)}${p(f.p_dm_frente_futuros)}</td>
        <td class="num">${f.acierto_direccional == null ? "—" : fmt(100 * f.acierto_direccional, 0) + " %"}</td>
        <td class="num">${f.cobertura_intervalo == null ? "—" : fmt(100 * f.cobertura_intervalo, 0) + " %"}</td>
        <td class="num">${f.parametros_por_modelo == null ? "—" : fmt(f.parametros_por_modelo, 0)}</td>
        <td class="num">${f.segundos_entrenamiento_3_semillas == null ? "—" : fmt(f.segundos_entrenamiento_3_semillas, 0) + " s"}</td>
      </tr>`;
    }).join("");
    document.getElementById("tabla-test").innerHTML = `<table>
      <thead><tr><th>Predictor</th><th>MAE (USD)</th><th>RMSE (USD)</th><th>Mejora frente al ingenuo</th><th>Mejora frente al ingenuo con futuros</th>
        <th>Dirección</th><th>Cobertura 80 %</th><th>Parámetros</th><th>Entrenamiento</th></tr></thead>
      <tbody>${filas}</tbody></table>`;
  };
  segmentado(document.getElementById("selector-h-tabla"), OPCIONES_H, (v) => { h = v; pintar(); }, h);
  pintar();
}

function pintarAnual(e, fila) {
  let h = "5";
  segmentado(document.getElementById("selector-h-anual"), OPCIONES_H, (v) => { h = v; mae.grafica.setOption(construirMae(), true); cob.grafica.setOption(construirCobertura(), true); }, h);
  const anios = (s) => [...new Set(s.origen.map((d) => d.slice(0, 4)))];
  const construirMae = () => {
    const c = colores();
    const s = serieDe(e, h);
    const lista = anios(s);
    const media = (campo, anio) => {
      const idx = s.origen.map((d, i) => [d, i]).filter(([d]) => d.startsWith(anio)).map(([, i]) => i);
      return +(idx.reduce((a, i) => a + Math.abs(s[campo][i] - s.real[i]), 0) / idx.length).toFixed(2);
    };
    const campos = [["RNN", "RNN"], ["LSTM", "LSTM"], ["GRU", "GRU"], ["futuros", "Ingenuo con futuros"], ["ingenuo", "Ingenuo"]];
    return {
      ...baseOpciones(),
      grid: { left: 44, right: 12, top: 36, bottom: 32 },
      legend: { top: 0, left: 0, itemWidth: 10, itemHeight: 10, textStyle: { color: c.tinta2, fontSize: 11 } },
      tooltip: { ...baseOpciones().tooltip, axisPointer: { type: "shadow", shadowStyle: { color: c.rejilla, opacity: .35 } },
        formatter: (ps) => `<b>${ps[0].axisValue}</b>` + ps.map((x) => lineaTooltip(x.color, x.seriesName, fmtUSD(x.value))).join("") },
      xAxis: { type: "category", data: lista, axisTick: { show: false }, axisLine: { lineStyle: { color: c.rejilla } }, axisLabel: { color: c.tinta2 } },
      yAxis: ejeValor({ scale: false, name: "USD" }),
      series: campos.map(([k, nombre]) => ({ name: nombre, type: "bar", data: lista.map((a) => media(k, a)), barGap: "10%", itemStyle: { color: c[COLOR_PRED[nombre]], borderRadius: [3, 3, 0, 0] } })),
    };
  };
  const construirCobertura = () => {
    const c = colores();
    const f = fila(h, e.seleccionada);
    const lista = Object.keys(f.cobertura_por_anio);
    return {
      ...baseOpciones(),
      grid: { left: 44, right: 12, top: 24, bottom: 32 },
      tooltip: { ...baseOpciones().tooltip, axisPointer: { type: "shadow", shadowStyle: { color: c.rejilla, opacity: .35 } },
        formatter: (ps) => `<b>${ps[0].axisValue}</b>${lineaTooltip(c[e.seleccionada], "Dentro del intervalo", fmt(ps[0].value, 0) + " %")}` },
      xAxis: { type: "category", data: lista, axisTick: { show: false }, axisLine: { lineStyle: { color: c.rejilla } }, axisLabel: { color: c.tinta2 } },
      yAxis: ejeValor({ min: 0, max: 100, scale: false, axisLabel: { color: c.tinta3, formatter: "{value} %" } }),
      series: [{
        type: "bar", barWidth: "45%", data: lista.map((a) => +(100 * f.cobertura_por_anio[a]).toFixed(1)),
        itemStyle: { color: (p) => (p.value >= 70 ? c[e.seleccionada] : c.acento), borderRadius: [3, 3, 0, 0] },
        label: { show: true, position: "top", color: c.tinta2, fontSize: 11, formatter: (p) => `${fmt(p.value, 0)} %` },
        markLine: { silent: true, symbol: "none", data: [{ yAxis: 80, lineStyle: { color: c.tinta2, type: [6, 4] }, label: { formatter: "80 % nominal", color: c.tinta2, position: "insideEndTop" } }] },
      }],
    };
  };
  const mae = crearGrafica(document.getElementById("grafica-mae"), construirMae);
  const cob = crearGrafica(document.getElementById("grafica-cobertura"), construirCobertura);
}

function pintarValTest(e, fila) {
  const final = e.familias.find((f) => f.id === "futuros").arquitecturas[e.seleccionada];
  const filas = e.horizontes.map((h) => `<tr><td>${NOMBRES_HORIZONTE[h]}</td>
    <td class="num ${claseSigno(final.horizontes[h].frente_futuros)}">${fmtPct(final.horizontes[h].frente_futuros, 2)}</td>
    <td class="num ${claseSigno(fila(h, e.seleccionada).mejora_frente_futuros)}">${fmtPct(fila(h, e.seleccionada).mejora_frente_futuros, 2)}</td></tr>`).join("");
  document.getElementById("tabla-val-test").outerHTML = `<div class="tabla-envoltura"><table>
    <thead><tr><th>Horizonte</th><th>Validación 2018–2021</th><th>Test 2023–2026</th></tr></thead><tbody>${filas}</tbody></table></div>
    <p class="nota">En validación, media de las mejoras anuales; en test, con todos los orígenes juntos. Ambas, medias de tres semillas.</p>`;
}
