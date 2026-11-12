// Página «Datos y método»: hueco entre spot y futuro, y esquema de particiones.
document.addEventListener("DOMContentLoaded", async () => {
  document.getElementById("enlace-modelo").href = URL_MODELO;
  const [prevision, estudio] = await Promise.all([
    cargarJSON(URL_PREVISION).catch(() => null), cargarJSON(URL_ESTUDIO),
  ]);
  if (prevision) pintarHueco(prevision);
  else document.getElementById("grafica-hueco").innerHTML = `<p class="cargando error">No se ha podido cargar la serie reciente.</p>`;
  let horizonte = "5";
  segmentado(document.getElementById("selector-tramos"), [["5", "1 semana"], ["63", "3 meses"], ["252", "1 año"]], (v) => {
    horizonte = v; pintarEsquema(estudio.tramos[horizonte]);
  }, horizonte);
  pintarEsquema(estudio.tramos[horizonte]);
});

function pintarHueco(p) {
  const c0 = VAR;
  document.getElementById("leyenda-hueco").innerHTML = `
    <span><i style="background:${c0.real}"></i>Brent spot publicado</span>
    <span><i style="background:${c0.futuros};opacity:.6"></i>Futuro de Brent</span>
    <span><i class="banda" style="background:${c0.acento}"></i>Días sin spot admisible</span>`;
  const inicio = new Date(p.origen); inicio.setMonth(inicio.getMonth() - 3);
  const desde = inicio.toISOString().slice(0, 10);
  crearGrafica(document.getElementById("grafica-hueco"), () => {
    const c = colores();
    return {
      ...baseOpciones(),
      grid: { left: 44, right: 16, top: 24, bottom: 36 },
      tooltip: {
        ...baseOpciones().tooltip,
        formatter: (ps) => `<div style="color:${c.tinta3};margin-bottom:4px">${fmtFecha(String(ps[0].value[0]).slice(0, 10))}</div>` +
          ps.map((x) => lineaTooltip(x.color, x.seriesName, fmtUSD(x.value[1]))).join(""),
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
            symbol: "circle", symbolSize: 9, itemStyle: { color: c.acento, borderColor: c.superficie, borderWidth: 2 },
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
  const inicio = new Date("2000-01-01").getTime(), fin = new Date("2026-12-31").getTime();
  const pos = (d) => ((new Date(d).getTime() - inicio) / (fin - inicio)) * 100;
  const filas = Object.entries(tramos).map(([corte, t]) => {
    const evaluado = t.validacion || t.test;
    const segmento = (clase, a, b, texto) => `<span class="${clase}" style="left:${pos(a)}%;width:${Math.max(0.4, pos(b) - pos(a))}%" title="${texto}">${pos(b) - pos(a) > 9 ? texto : ""}</span>`;
    return `<div class="fila-esquema">
      <div class="num">${corte === "final" ? "<b>Test</b>" : `Corte ${corte}`}</div>
      <div class="pista">
        ${segmento("tramo-aprendizaje", t.aprendizaje.inicio, t.aprendizaje.fin, `Aprendizaje · ${t.aprendizaje.n.toLocaleString("es-ES")}`)}
        ${segmento("tramo-hueco", t.aprendizaje.fin, t.interno.inicio, "Purga")}
        ${segmento("tramo-interno", t.interno.inicio, t.interno.fin, `Parada · ${t.interno.n}`)}
        ${segmento("tramo-hueco", t.interno.fin, evaluado.inicio, "Purga")}
        ${segmento("tramo-evaluado", evaluado.inicio, evaluado.fin, `${corte === "final" ? "Test" : "Validación"} · ${evaluado.n}`)}
      </div></div>`;
  }).join("");
  document.getElementById("esquema").innerHTML = filas + `
    <div class="ejes-esquema"><div></div><div style="position:relative;height:18px">${[2000, 2005, 2010, 2015, 2020, 2025]
      .map((a) => `<span style="position:absolute;left:${pos(`${a}-01-01`)}%;transform:translateX(${a === 2000 ? 0 : -50}%)">${a}</span>`).join("")}</div></div>`;
}
