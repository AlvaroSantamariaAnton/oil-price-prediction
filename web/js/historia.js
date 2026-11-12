// Página «Histórico»: serie del Brent desde 2000 con acontecimientos y rango anual.
const EVENTOS = [
  {
    id: "2008", titulo: "Crisis financiera mundial", inicio: "2008-01-01", fin: "2009-06-30",
    texto: (e) => `El Brent alcanzó su máximo histórico en ${fmtFechaCorta(e.max.fecha)} (${fmtUSD(e.max.valor, 0)}) y, con la quiebra de
      Lehman Brothers y la recesión, se desplomó hasta ${fmtUSD(e.min.valor, 0)} en ${fmtFechaCorta(e.min.fecha)}: una caída del
      ${fmt(100 * (1 - e.min.valor / e.max.valor), 0)} % en pocos meses.`,
  },
  {
    id: "2014", titulo: "Exceso de oferta", inicio: "2014-06-01", fin: "2016-03-31",
    texto: (e) => `El auge del petróleo de esquisto en EE. UU. y la decisión de la OPEP, en noviembre de 2014, de no recortar su
      producción llenaron el mercado. De ${fmtUSD(e.max.valor, 0)} (${fmtFechaCorta(e.max.fecha)}) el precio bajó a
      ${fmtUSD(e.min.valor, 0)} (${fmtFechaCorta(e.min.fecha)}), en una caída lenta de año y medio.`,
  },
  {
    id: "2020", titulo: "Pandemia de COVID-19", inicio: "2020-01-01", fin: "2020-12-31",
    texto: (e) => `Los confinamientos hundieron la demanda y coincidieron con una guerra de precios entre Arabia Saudí y Rusia. El
      Brent spot tocó ${fmtUSD(e.min.valor, 2)} el ${fmtFecha(e.min.fecha)}, el mínimo de toda la serie, y el futuro del WTI llegó a
      cotizar en negativo: hubo que tratar ese caso aparte al calcular variaciones.`,
  },
  {
    id: "2022", titulo: "Invasión rusa de Ucrania", inicio: "2022-02-01", fin: "2022-12-31",
    texto: (e) => `Tras la invasión del 24 de febrero de 2022 y las sanciones a Rusia, el Brent superó los ${fmtUSD(e.max.valor, 0)}
      (${fmtFechaCorta(e.max.fecha)}). Para el estudio fue clave: las previsiones a un año hechas en 2021 apuntaban a
      precios estables o a la baja y fallaron por mucho.`,
  },
  {
    id: "2026", titulo: "Repunte reciente", inicio: "2026-01-01", fin: null,
    texto: (e) => `En 2026 el precio pasó de ${fmtUSD(e.min.valor, 0)} (${fmtFechaCorta(e.min.fecha)}) a ${fmtUSD(e.max.valor, 0)}
      (${fmtFechaCorta(e.max.fecha)}) con oscilaciones muy bruscas. Coincide con el final del periodo de test y explica la
      caída de la cobertura de los intervalos ese año. Este estudio no analiza sus causas.`,
  },
];

document.addEventListener("DOMContentLoaded", async () => {
  let prevision;
  try {
    prevision = await cargarJSON(URL_PREVISION);
  } catch (e) {
    document.getElementById("grafica-historia").innerHTML = `<p class="error cargando">No se ha podido cargar la serie: ${e.message}.</p>`;
    return;
  }
  const serie = prevision.historico.brent_spot;
  const eventos = EVENTOS.map((ev) => {
    const tramo = serie.filter(([d]) => d >= ev.inicio && (!ev.fin || d <= ev.fin));
    const max = tramo.reduce((a, b) => (b[1] > a[1] ? b : a));
    const min = tramo.reduce((a, b) => (b[1] < a[1] ? b : a));
    return { ...ev, fin: ev.fin || serie[serie.length - 1][0], max: { fecha: max[0], valor: max[1] }, min: { fecha: min[0], valor: min[1] } };
  });
  pintarHistoria(serie, eventos);
  pintarEventos(eventos);
  pintarAnual(serie);
  document.getElementById("nota-historia").textContent =
    `Fuente: EIA (serie DCOILBRENTEU de FRED). ${serie.length.toLocaleString("es-ES")} días con precio publicado, del ${fmtFecha(serie[0][0])} al ${fmtFecha(serie[serie.length - 1][0])}.`;
});

function pintarHistoria(serie, eventos) {
  let escala = "lineal";
  segmentado(document.getElementById("selector-escala"), [["lineal", "Escala lineal"], ["log", "Logarítmica"]], (v) => {
    escala = v; entrada.grafica.setOption(construir(), true);
  }, escala);
  const c0 = VAR;
  document.getElementById("leyenda-historia").innerHTML = `
    <span><i style="background:${c0.real}"></i>Brent spot</span>
    <span><i class="banda" style="background:${c0.acento}"></i>Acontecimiento</span>
    <span><i class="banda" style="background:${c0.GRU}"></i>Validación del estudio (2018–2021)</span>
    <span><i class="banda" style="background:${c0.RNN}"></i>Test (2023 en adelante)</span>`;
  const construir = () => {
    const c = colores();
    const corto = { 2008: "2008", 2014: "2014–16", 2020: "2020", 2022: "2022", 2026: "2026" };
    const marcas = eventos.map((e) => [{ name: corto[e.id], xAxis: e.inicio }, { xAxis: e.fin }]);
    return {
      ...baseOpciones(),
      grid: { left: 52, right: 24, top: 36, bottom: 90 },
      tooltip: {
        ...baseOpciones().tooltip,
        formatter: (ps) => {
          const p = ps.find((x) => x.seriesName === "Brent spot");
          if (!p) return "";
          const evento = eventos.find((e) => p.value[0] >= e.inicio && p.value[0] <= e.fin);
          return `<div style="color:${c.tinta3};margin-bottom:4px">${fmtFecha(p.value[0])}</div>${lineaTooltip(c.real, "Brent spot", fmtUSD(p.value[1]))}` +
            (evento ? `<div style="margin-top:6px;color:${c.acento};font-weight:600">${evento.titulo}</div>` : "");
        },
      },
      xAxis: ejeTiempo(),
      yAxis: escala === "log" ? { ...ejeValor({ name: "USD/barril (log)" }), type: "log", logBase: 10, min: 5, max: 200 } : ejeValor({ name: "USD/barril", min: 0 }),
      dataZoom: [
        { type: "inside", start: 0, end: 100, zoomOnMouseWheel: "ctrl", moveOnMouseWheel: false, moveOnMouseMove: true },
        {
          type: "slider", start: 0, end: 100, height: 28, bottom: 18, borderColor: c.rejilla, fillerColor: c.acentoSuave,
          handleStyle: { color: c.acento, borderColor: c.acento }, textStyle: { color: c.tinta3 },
          dataBackground: { lineStyle: { color: c.tinta3 }, areaStyle: { color: c.rejilla } },
          selectedDataBackground: { lineStyle: { color: c.acento }, areaStyle: { color: c.acentoSuave } },
        },
      ],
      series: [
        {
          name: "Brent spot", type: "line", data: serie, showSymbol: false, sampling: "lttb",
          lineStyle: { width: 1.4, color: c.real }, itemStyle: { color: c.real },
          markArea: {
            silent: true, itemStyle: { color: c.acento, opacity: .13 },
            label: { color: c.tinta2, fontSize: 11, fontWeight: 600, position: "insideTop", distance: 6 },
            data: marcas,
          },
          markPoint: {
            symbol: "circle", symbolSize: 8, itemStyle: { color: c.acento, borderColor: c.superficie, borderWidth: 2 },
            label: { show: false },
            data: eventos.flatMap((e) => [{ coord: [e.max.fecha, e.max.valor] }, { coord: [e.min.fecha, e.min.valor] }]),
          },
        },
        {
          name: "Periodos", type: "line", data: [], markArea: {
            silent: true, label: { show: false },
            data: [
              [{ xAxis: "2018-01-01", itemStyle: { color: c.GRU, opacity: .07 } }, { xAxis: "2021-12-31" }],
              [{ xAxis: "2023-01-02", itemStyle: { color: c.RNN, opacity: .07 } }, { xAxis: serie[serie.length - 1][0] }],
            ],
          },
        },
      ],
    };
  };
  const entrada = crearGrafica(document.getElementById("grafica-historia"), construir);
}

function pintarEventos(eventos) {
  document.getElementById("eventos").innerHTML = eventos.map((e) => `
    <article class="tarjeta evento">
      <p class="fecha">${e.id === "2014" ? "2014–2016" : e.id === "2026" ? "2026" : e.id}</p>
      <h3>${e.titulo}</h3>
      <p class="mutado pequeno" style="margin:0">${e.texto(e)}</p>
    </article>`).join("") + `
    <article class="tarjeta">
      <p class="etiqueta">Lo que tienen en común</p>
      <h3>Ninguno estaba en los datos</h3>
      <p class="mutado pequeno" style="margin:0">Guerras, decisiones de la OPEP o una pandemia no se deducen de los precios de las
        semanas anteriores. Por eso el estudio mide a las redes contra referencias sencillas y explica abiertamente cuándo
        fallan, en lugar de prometer que anticipan estos giros.</p>
    </article>`;
}

function pintarAnual(serie) {
  const anios = {};
  for (const [d, v] of serie) (anios[d.slice(0, 4)] ||= []).push(v);
  const filas = Object.entries(anios).map(([a, vs]) => [a, Math.min(...vs), vs.reduce((x, y) => x + y, 0) / vs.length, Math.max(...vs)]);
  crearGrafica(document.getElementById("grafica-anual"), () => {
    const c = colores();
    return {
      ...baseOpciones(),
      grid: { left: 44, right: 16, top: 20, bottom: 36 },
      tooltip: {
        ...baseOpciones().tooltip, trigger: "item",
        formatter: (p) => `<b>${p.value[0]}</b>${lineaTooltip(c.acento, "Máximo", fmtUSD(p.value[3]))}${lineaTooltip(c.tinta2, "Media", fmtUSD(p.value[2]))}${lineaTooltip(c.acento, "Mínimo", fmtUSD(p.value[1]))}${lineaTooltip(c.tinta3, "Rango", fmtUSD(p.value[3] - p.value[1], 0))}`,
      },
      xAxis: { type: "category", data: filas.map((f) => f[0]), axisLabel: { color: c.tinta3, interval: 3 }, axisLine: { lineStyle: { color: c.rejilla } }, axisTick: { show: false } },
      yAxis: ejeValor({ min: 0, name: "USD" }),
      series: [{
        type: "custom", data: filas.map((f, i) => [f[0], f[1], f[2], f[3], i]),
        renderItem: (params, api) => {
          const x = api.coord([api.value(4), 0])[0];
          const bajo = api.coord([api.value(4), api.value(1)])[1];
          const alto = api.coord([api.value(4), api.value(3)])[1];
          const media = api.coord([api.value(4), api.value(2)])[1];
          const ancho = Math.max(4, api.size([1, 0])[0] * 0.45);
          const rango = api.value(3) - api.value(1);
          return {
            type: "group", children: [
              { type: "rect", shape: { x: x - ancho / 2, y: alto, width: ancho, height: bajo - alto, r: 3 }, style: { fill: rango > 50 ? c.acento : c.tinta3, opacity: rango > 50 ? .55 : .3 } },
              { type: "circle", shape: { cx: x, cy: media, r: 3 }, style: { fill: c.tinta } },
            ],
          };
        },
        encode: { x: 4, y: [1, 3] },
      }],
    };
  });
}
