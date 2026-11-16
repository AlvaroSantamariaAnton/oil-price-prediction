// Página «Datos y método»: hueco entre spot y futuro, y esquema de particiones.
document.addEventListener("DOMContentLoaded", async () => {
  document.getElementById("enlace-modelo").href = URL_MODELO;
  const [resPrevision, resEstudio] = await Promise.allSettled([cargarJSON(URL_PREVISION), cargarJSON(URL_ESTUDIO)]);

  const hueco = document.getElementById("grafica-hueco");
  if (resPrevision.status === "fulfilled") pintarHueco(resPrevision.value);
  else { hueco.style.height = "auto"; mostrarError(hueco, "No se ha podido cargar la serie reciente."); }

  const esquema = document.getElementById("esquema");
  if (resEstudio.status !== "fulfilled") { mostrarError(esquema, "No se han podido cargar los datos del estudio."); return; }
  const estudio = resEstudio.value;
  let horizonte = "5";
  segmentado(document.getElementById("selector-tramos"), [["5", "1 semana"], ["63", "3 meses"], ["252", "1 año"]], (v) => {
    horizonte = v; pintarEsquema(estudio.tramos[horizonte]);
  }, horizonte);
  pintarEsquema(estudio.tramos[horizonte]);
});

function pintarHueco(p) {
  document.getElementById("leyenda-hueco").innerHTML = `
    <span><i style="background:${VAR.real}"></i>Brent spot publicado</span>
    <span><i style="background:${VAR.futuros};opacity:.6"></i>Futuro de Brent</span>
    <span><i class="banda" style="background:${VAR.acento}"></i>Días sin spot admisible</span>`;
  const desde = desplazarFecha(p.origen, { meses: -3 });
  crearGrafica(document.getElementById("grafica-hueco"), () => {
    const c = colores();
    return {
      ...baseOpciones(),
      grid: { left: 44, right: 16, top: 38, bottom: 36 },
      tooltip: {
        ...baseOpciones().tooltip,
        formatter: (ps) => ps.length ? cabeceraTooltip(fmtFecha(String(ps[0].value[0])), c.tinta3) +
          ps.map((x) => lineaTooltip(x.color, x.seriesName, fmtUSD(x.value[1]))).join("") : "",
      },
      xAxis: ejeTiempo({ max: p.origen }),
      yAxis: ejeValor({ name: "USD/barril" }),
      series: [
        {
          name: "Futuro de Brent", type: "line", data: p.historico.brent_futuro.filter(([d]) => d >= desde), showSymbol: false,
          lineStyle: { width: 1.6, color: c.futuros, opacity: .6 }, itemStyle: { color: c.futuros },
        },
        {
          name: "Brent spot", type: "line", data: p.historico.brent_spot.filter(([d]) => d >= desde), showSymbol: false,
          lineStyle: { width: 2, color: c.real }, itemStyle: { color: c.real },
          markArea: {
            silent: true, itemStyle: { color: c.acento, opacity: .14 },
            label: { show: true, position: "insideTop", color: c.tinta2, fontSize: 11, formatter: "aún sin spot\nadmisible" },
            data: [[{ xAxis: p.base.spot_fecha }, { xAxis: p.origen }]],
          },
          markPoint: {
            symbol: "circle", symbolSize: 9, silent: true, itemStyle: { color: c.acento, borderColor: c.superficie, borderWidth: 2 },
            data: [{ coord: [p.base.spot_fecha, p.base.spot], label: { show: false } }],
          },
        },
      ],
    };
  });
  document.getElementById("nota-hueco").textContent =
    `El ${fmtFecha(p.origen)}, el último spot admisible era el del ${fmtFecha(p.base.spot_fecha)} (${fmtUSD(p.base.spot)}); ` +
    `actualizado con el futuro, la referencia era ${fmtUSD(p.base.valor)}.`;
}

function pintarEsquema(tramos) {
  const inicio = Date.UTC(2000, 0, 1), fin = Date.UTC(2026, 11, 31);
  const pos = (d) => ((new Date(d).getTime() - inicio) / (fin - inicio)) * 100;
  const numero = (n) => n.toLocaleString("es-ES");
  // Las barras no llevan texto (en los tramos estrechos no cabría): las cifras van en una línea debajo de cada una.
  const segmento = (clase, a, b, texto) =>
    `<span class="${clase}" style="left:${pos(a)}%;width:${Math.max(0.4, pos(b) - pos(a))}%" title="${texto}"></span>`;
  const periodo = (t) => `${fmtFecha(t.inicio, { month: "short", year: "numeric" })} – ${fmtFecha(t.fin, { month: "short", year: "numeric" })}`;
  const filas = Object.entries(tramos).map(([corte, t]) => {
    const evaluado = t.validacion || t.test;
    const nombre = corte === "final" ? "Test" : "Validación";
    return `<div class="fila-esquema">
      <div class="num">${corte === "final" ? "<strong>Test</strong>" : `Corte ${corte}`}</div>
      <div>
        <div class="pista">
          ${segmento("tramo-aprendizaje", t.aprendizaje.inicio, t.aprendizaje.fin, `Aprendizaje: ${numero(t.aprendizaje.n)} muestras, ${periodo(t.aprendizaje)}`)}
          ${segmento("tramo-hueco", t.aprendizaje.fin, t.interno.inicio, "Purga por etiquetas no publicadas")}
          ${segmento("tramo-interno", t.interno.inicio, t.interno.fin, `Parada temprana: ${numero(t.interno.n)} muestras, ${periodo(t.interno)}`)}
          ${segmento("tramo-hueco", t.interno.fin, evaluado.inicio, "Purga por etiquetas no publicadas")}
          ${segmento("tramo-evaluado", evaluado.inicio, evaluado.fin, `${nombre}: ${numero(evaluado.n)} muestras, ${periodo(evaluado)}`)}
        </div>
        <div class="detalle-esquema num">
          <span><i class="tramo-aprendizaje"></i>Aprendizaje <strong>${numero(t.aprendizaje.n)}</strong></span>
          <span><i class="tramo-interno"></i>Parada temprana <strong>${numero(t.interno.n)}</strong></span>
          <span><i class="tramo-evaluado"></i>${nombre} <strong>${numero(evaluado.n)}</strong></span>
        </div>
      </div></div>`;
  }).join("");
  document.getElementById("esquema").innerHTML = filas + `
    <div class="ejes-esquema"><div></div><div style="position:relative;height:18px">${[2000, 2005, 2010, 2015, 2020, 2025]
      .map((a) => `<span style="position:absolute;left:${pos(`${a}-01-01`)}%;transform:translateX(${a === 2000 ? 0 : -50}%)">${a}</span>`).join("")}</div></div>
    <p class="nota">Número de muestras de cada tramo. Pasa el cursor por una barra para ver sus fechas.</p>`;
}