// Página «Hoy»: previsión vigente publicada en Hugging Face.
const NOMBRES_FUENTE = {
  brent: "Brent spot (EIA)", wti: "WTI spot (EIA)", gas_natural: "Gas natural Henry Hub", usd_por_eur: "Dólares por euro",
  cny_por_usd: "Yuanes por dólar", vix: "Volatilidad VIX", tipo_bce: "Tipo de depósito BCE", cesta_opep: "Cesta OPEP",
  brent_fut: "Futuro de Brent", wti_fut: "Futuro de WTI", cobre: "Cobre", oro: "Oro", indice_dolar: "Índice dólar",
};

document.addEventListener("DOMContentLoaded", async () => {
  const estado = document.getElementById("estado");
  let prevision, estudio;
  try {
    [prevision, estudio] = await Promise.all([cargarJSON(URL_PREVISION), cargarJSON(URL_ESTUDIO)]);
  } catch (e) {
    estado.innerHTML = `<p class="error">No se ha podido cargar la previsión: ${e.message}.</p>`;
    return;
  }
  estado.hidden = true;
  document.getElementById("contenido").hidden = false;
  const avisos = [];
  const calculo = momentoCalculo(prevision);
  if (calculo.temprano) {
    const cuando = calculo.fecha === prevision.origen ? `a las ${calculo.hora}`
      : `el ${fmtFecha(calculo.fecha)} a las ${calculo.hora}, para el ${fmtFecha(prevision.origen)}`;
    avisos.push(`<p><strong>Calculada antes de la hora habitual.</strong> Esta previsión se hizo ${cuando} (hora de Madrid),
      antes de las 09:00. Usa los datos conocidos a esa hora:
      puede faltar alguno que se publique antes de las 09:00, como un cierre de mercado o una cifra de FRED. La próxima
      ejecución automática la sustituirá.</p>`);
  }
  // La cesta OPEP falla siempre desde GitHub Actions: es una situación permanente y se explica en la sección de
  // fuentes. El recuadro amarillo queda para fallos inesperados (p. ej. el respaldo del BCE en FRED).
  const inesperados = (prevision.avisos || []).filter((a) => !esAvisoOpep(a));
  if (inesperados.length) {
    avisos.push(`<p><strong>Datos incompletos hoy.</strong> ${inesperados.join(" ")}</p>`);
  }
  if (avisos.length) {
    document.getElementById("avisos").innerHTML = `<div class="aviso" style="margin-bottom:20px">${avisos.join("")}</div>`;
  }
  pintarCabecera(prevision);
  pintarPrevisiones(prevision);
  const redibujarGrafica = pintarGrafica(prevision);
  montarSelectorHorizonte(prevision, estudio, redibujarGrafica);
  pintarFiabilidad(estudio, prevision);
  pintarFuentes(prevision);
});

// Horizonte elegido por el usuario: destaca su tarjeta y su previsión en la gráfica y explica su significado.
let horizonteActivo = 5;

function montarSelectorHorizonte(p, estudio, redibujarGrafica) {
  const selector = document.getElementById("selector-horizonte");
  const elegir = (h) => {
    horizonteActivo = h;
    selector.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(Number(b.dataset.valor) === h)));
    document.querySelectorAll("#previsiones .prevision").forEach((t) => {
      const activa = Number(t.dataset.horizonte) === h;
      t.classList.toggle("activa", activa);
      t.setAttribute("aria-pressed", String(activa));
    });
    document.getElementById("explicacion-horizonte").innerHTML = explicarHorizonte(p, estudio, h);
    redibujarGrafica();
  };
  segmentado(selector, p.previsiones.map((f) => [String(f.horizonte), NOMBRES_HORIZONTE[f.horizonte]]),
    (v) => elegir(Number(v)), String(horizonteActivo));
  document.querySelectorAll("#previsiones .prevision").forEach((t) => {
    t.addEventListener("click", () => elegir(Number(t.dataset.horizonte)));
    t.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); elegir(Number(t.dataset.horizonte)); }
    });
  });
  elegir(horizonteActivo);
}

const PLAZOS = {
  5: "dentro de una semana (5 días hábiles)",
  63: "dentro de unos tres meses (63 días hábiles)",
  252: "dentro de un año (252 días hábiles)",
};
const RIESGOS = {
  5: `Cualquier sorpresa de esta semana: una decisión de la OPEP+, una tensión geopolítica en una zona productora, un
    dato de inventarios o un movimiento brusco del dólar. El modelo solo ve datos pasados y no anticipa noticias.`,
  63: `En tres meses pueden cambiar la producción de la OPEP+, la demanda mundial (una desaceleración o una crisis) o los
    conflictos que afectan al suministro, como ocurrió en 2020 y en 2022.`,
  252: `A un año pesan factores que ningún dato de hoy recoge: recesiones o recuperaciones mundiales, guerras, cambios de
    estrategia de la OPEP+ o la transición energética. Movimientos como el desplome de 2020 o la subida de 2022 no se
    habrían podido prever con un año de antelación.`,
};

// Texto para un usuario no técnico: qué significa la previsión, qué fiabilidad tuvo ese horizonte en el test del
// estudio (según la comparativa) y qué puede invalidarla. Las cifras salen de la previsión y de estudio.json.
function explicarHorizonte(p, estudio, h) {
  const f = p.previsiones.find((x) => x.horizonte === h);
  const red = estudio.test.tabla.find((x) => x.horizonte === h && x.predictor === p.modelo.arquitectura);
  const [bajo, alto] = f.intervalo;
  const pct = f.variacion_pct_frente_base;
  const sentido = Math.abs(pct) < 0.05 ? "prácticamente igual al"
    : `un ${fmt(Math.abs(pct), 1)} % ${pct > 0 ? "por encima del" : "por debajo del"}`;
  const frente = (mejora, quien) => `un ${fmt(Math.abs(mejora), 1)} % ${mejora >= 0 ? "menos" : "más"} que ${quien}`;
  const [peorAnio, peorCobertura] = Object.entries(red.cobertura_por_anio).sort((a, b) => a[1] - b[1])[0];
  let veredicto;
  if (red.mejora_frente_ingenuo > 0 && red.mejora_frente_futuros >= 0) {
    veredicto = "A este plazo la red mejoró a las dos referencias.";
  } else if (red.mejora_frente_ingenuo > 0) {
    veredicto = `A este plazo aporta valor frente a repetir el último precio publicado, pero no frente a seguir el futuro de
      Brent: úsala como una referencia razonable de corto plazo, no como una ventaja sobre el mercado.`;
  } else {
    veredicto = `A este plazo la previsión no aportó valor fiable frente a las referencias: tómala como una orientación del
      rango posible, no como un objetivo.`;
  }
  return `
    <p class="etiqueta" style="margin:0">${NOMBRES_HORIZONTE[h]} · ${fmtFecha(f.fecha_objetivo)}</p>
    <p><span class="apartado">Qué significa.</span> El modelo estima que el ${fmtFecha(f.fecha_objetivo)}, ${PLAZOS[h]}, el
      Brent spot estará en torno a <strong>${fmtUSD(f.precio)}</strong> por barril, ${sentido} precio de referencia de hoy
      (${fmtUSD(p.base.valor)}). No es un precio exacto: con los errores observados en la validación, lo razonable es
      esperar un valor entre <strong>${fmt(bajo)} y ${fmt(alto)} USD</strong>; en 8 de cada 10 casos el precio real quedó a
      menos de ${fmtUSD(f.margen)} de lo previsto.</p>
    <p><span class="apartado">Cuánto fiarse.</span> En el test del estudio (${red.n} previsiones de 2023 a 2026), la red se equivocó
      ${frente(red.mejora_frente_ingenuo, "repetir el último precio spot conocido")} y
      ${frente(red.mejora_frente_futuros, "la regla simple de actualizarlo con el futuro de Brent")}. Acertó si el precio
      subía o bajaba el ${fmt(100 * red.acierto_direccional, 0)} % de las veces, y el precio real quedó dentro del intervalo
      el ${fmt(100 * red.cobertura_intervalo, 0)} % (lo previsto era el 80 %; en ${peorAnio}, solo el
      ${fmt(100 * peorCobertura, 0)} %). ${veredicto}</p>
    <p><span class="apartado">Qué puede invalidarla.</span> ${RIESGOS[h]} Además, el intervalo tiene una anchura fija y se
      queda corto cuando el mercado está muy agitado.</p>`;
}

const esAvisoOpep = (aviso) => aviso.includes("cesta OPEP");

// Fecha y hora de Madrid en que se calculó la previsión. Es «temprana» si se calculó antes de las 09:00 del día de
// origen (p. ej. una ejecución manual de madrugada): entonces los datos son los conocidos a esa hora, no a las 09:00.
function momentoCalculo(p) {
  const partes = Object.fromEntries(new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Madrid", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(p.generado_utc)).map((x) => [x.type, x.value]));
  const fecha = `${partes.year}-${partes.month}-${partes.day}`;
  const temprano = fecha < p.origen || (fecha === p.origen && Number(partes.hour) < 9);
  // «Tarde»: a partir de las 10:00 del origen o un día posterior (GitHub Actions retrasó la ejecución programada).
  const tarde = !temprano && (fecha > p.origen || Number(partes.hour) >= 10);
  const hora = `${partes.hour}:${partes.minute}`;
  // Momento al que corresponden los datos: las 09:00 del origen si se calculó a la hora habitual (09:xx); si no, la
  // fecha y la hora reales del cálculo.
  const real = temprano || tarde;
  return { fecha, hora, temprano, tarde, horaDatos: real ? hora : "09:00", fechaDatos: real ? fecha : p.origen };
}

function pintarCabecera(p) {
  const { horaDatos, fechaDatos } = momentoCalculo(p);
  document.getElementById("fecha-prevision").textContent =
    `Previsión hecha con los datos disponibles a las ${horaDatos} del ${fmtFecha(fechaDatos)} (hora de Madrid)`;
  const b = p.base;
  document.getElementById("base-titulo").textContent = `Precio de referencia · ${fmtFecha(fechaDatos)}, ${horaDatos}`;
  document.getElementById("base-valor").innerHTML = `${fmt(b.valor)}<small>USD/barril</small>`;
  if (b.tipo !== "futuros") {
    document.getElementById("base-explicacion").innerHTML =
      `Ese día no había futuro de Brent disponible, así que la referencia es el último Brent spot publicado (${fmtFecha(b.spot_fecha)}).`;
    return pintarFicha(p);
  }
  // El futuro en la fecha del spot viene en el JSON; en previsiones antiguas se deduce de la propia fórmula.
  const futuroBase = b.futuro_base ?? (b.spot * b.futuro / b.valor);
  const fechaFuturoBase = b.futuro_base_fecha ?? b.spot_fecha;
  const variacion = 100 * (b.futuro / futuroBase - 1);
  document.getElementById("base-explicacion").innerHTML = `
    Es el <strong>precio del Brent puesto al día</strong>, no una previsión. El Brent spot oficial se publica con una semana
    de retraso, así que a las ${momentoCalculo(p).horaDatos} el último conocido era el del ${fmtFecha(b.spot_fecha)}. Para saber dónde está el
    precio hoy, se le aplica lo que ha variado desde entonces el <strong>futuro de Brent</strong>, que cotiza a diario y es
    el precio que sigue el mercado. Las tres previsiones de abajo parten de este valor.`;
  document.getElementById("base-calculo").innerHTML = `
    <span>Último Brent spot publicado (${fmtFechaCorta(b.spot_fecha)})</span><b>${fmtUSD(b.spot)}</b>
    <span>Futuro de Brent el ${fmtFechaCorta(fechaFuturoBase)}</span><b>${fmtUSD(futuroBase)}</b>
    <span>Futuro de Brent el ${fmtFechaCorta(b.futuro_fecha)} (último cierre conocido)</span><b>${fmtUSD(b.futuro)}</b>
    <span>Variación del futuro en ese tiempo</span><b class="${claseSigno(variacion)}">${fmtPct(variacion, 2)}</b>
    <span class="total">${fmt(b.spot)} × ${fmt(b.futuro)} / ${fmt(futuroBase)}</span><b class="total">${fmtUSD(b.valor)}</b>`;
  document.getElementById("base-ingenuo").innerHTML = `El ingenuo del enunciado, repetir el último spot publicado
    (${fmtUSD(b.spot)}), no se usa como referencia diaria: es un precio de hace una semana. Sí se usa en el
    <a href="resultados.html">estudio</a>, donde las redes se comparan con las dos referencias.`;
  pintarFicha(p);
}

function pintarFicha(p) {
  const calculo = momentoCalculo(p);
  document.getElementById("ficha").innerHTML = `
    <dt class="mutado">Datos usados</dt><dd style="margin:0">los conocidos a las ${calculo.horaDatos} del ${fmtFecha(calculo.fechaDatos)}</dd>
    <dt class="mutado">Modelo</dt><dd style="margin:0">${p.modelo.arquitectura} · media de ${p.modelo.semillas.length} semillas</dd>
    <dt class="mutado">Versión</dt><dd style="margin:0" class="num">${p.modelo.version}</dd>
    ${filasEntrenamiento(p.modelo)}
    <dt class="mutado">Calculada</dt><dd style="margin:0">${fmtFecha(calculo.fecha)} a las ${calculo.hora} (hora de Madrid)${calculo.tarde ? `
      <div class="mutado" style="margin-top:4px">La tarea diaria está programada a las 09:15 en GitHub Actions, que a veces
        retrasa las ejecuciones programadas; si no llega a su hora, se reintenta cada hora durante el día. Por eso esta
        previsión usa los datos conocidos a las ${calculo.hora}. Las reglas de publicación de cada dato no cambian, así que la
        diferencia con las 09:00 suele ser mínima.</div>` : ""}</dd>
    <dt class="mutado">Archivos</dt><dd style="margin:0"><a href="${URL_MODELO}">modelo</a> · <a href="${URL_DATOS_HF}">historial de previsiones</a></dd>`;
}

// Con la parada temprana y el retraso de las etiquetas, «datos hasta la fecha de corte» sería engañoso:
// se muestran, por horizonte, los orígenes de aprendizaje y los de parada temprana.
function filasEntrenamiento(m) {
  const tramos = m.tramos || {};
  const horizontes = Object.keys(tramos).map(Number).sort((a, b) => a - b);
  if (!horizontes.length) {
    return `<dt class="mutado">Fecha de corte</dt><dd style="margin:0">${fmtFecha(m.entrenamiento)}</dd>`;
  }
  const lineas = horizontes.map((h) => {
    const t = tramos[h];
    return `<div><b>${NOMBRES_HORIZONTE[h]}:</b> aprendizaje hasta ${fmtFechaCorta(t.aprendizaje.fin)} ·
      parada temprana hasta ${fmtFechaCorta(t.interno.fin)}</div>`;
  }).join("");
  return `<dt class="mutado">Fecha de corte</dt><dd style="margin:0">${fmtFecha(m.entrenamiento)}: solo precios ya publicados ese día</dd>
    <dt class="mutado">Entrenamiento</dt><dd style="margin:0">${lineas}
      <div class="mutado" style="margin-top:4px">Fechas de origen de las ventanas: cada una se compara con el precio 5, 63 o 252
        días hábiles después, publicado una semana más tarde. El último 15 % se reserva para decidir cuándo dejar de entrenar
        (parada temprana).</div></dd>`;
}

function pintarPrevisiones(p) {
  const contenedor = document.getElementById("previsiones");
  contenedor.innerHTML = p.previsiones.map((f) => {
    const [bajo, alto] = f.intervalo;
    const minimo = Math.min(bajo, p.base.valor), maximo = Math.max(alto, p.base.valor);
    const margen = (maximo - minimo) * 0.08;
    const pos = (v) => ((v - (minimo - margen)) / (maximo - minimo + 2 * margen)) * 100;
    const pct = f.variacion_pct_frente_base;
    return `<article class="tarjeta prevision" data-horizonte="${f.horizonte}" role="button" tabindex="0"
      aria-label="Ver la explicación de la previsión a ${NOMBRES_HORIZONTE[f.horizonte]}">
      <h3><span>${NOMBRES_HORIZONTE[f.horizonte]}</span><span class="chip">${fmtFechaCorta(f.fecha_objetivo)}</span></h3>
      <div class="cifra-media num">${fmt(f.precio)} <span class="pequeno mutado" style="font-family:var(--texto)">USD</span></div>
      <div class="variacion ${claseSigno(pct)}">${fmtPct(pct)} frente a la referencia</div>
      <div class="barra-intervalo" aria-hidden="true">
        <span style="left:${pos(bajo)}%;right:${100 - pos(alto)}%"></span>
        <em style="left:${pos(p.base.valor)}%"></em><b style="left:${pos(f.precio)}%"></b>
      </div>
      <div class="rango num">
        <div><span>Cambio previsto</span><span class="${claseSigno(f.variacion_frente_base)}">${fmtSigno(f.variacion_frente_base, 2)} USD</span></div>
        <div><span>Intervalo del 80 %</span><span>${fmt(bajo)} – ${fmt(alto)}</span></div>
        <div><span>Margen</span><span>± ${fmt(f.margen)} USD</span></div>
        <div><span>Días hábiles hasta el objetivo</span><span>${f.horizonte}</span></div>
      </div>
    </article>`;
  }).join("");
}

function pintarGrafica(p) {
  const meses = { "6": 6, "18": 18, "60": 60 };
  let rango = "18";
  const contenedorSelector = document.getElementById("selector-rango");
  segmentado(contenedorSelector, [["6", "6 meses"], ["18", "18 meses"], ["60", "5 años"]], (v) => {
    rango = v; entrada.grafica.setOption(construir(), true);
  }, rango);
  const c0 = VAR;
  document.getElementById("leyenda-hoy").innerHTML = `
    <span><i style="background:${c0.real}"></i>Brent spot publicado</span>
    <span><i style="background:${c0.futuros};opacity:.55"></i>Futuro de Brent</span>
    <span><i style="background:${c0.RNN}"></i>Previsión (RNN)</span>
    <span><i class="banda" style="background:${c0.RNN}"></i>Intervalo del 80 %</span>`;
  const origen = p.origen;
  const activa = (f) => f[4] === horizonteActivo;  // f = [fecha, precio, bajo, alto, horizonte]
  const desde = (m) => { const d = new Date(origen); d.setMonth(d.getMonth() - m); return d.toISOString().slice(0, 10); };
  const construir = () => {
    const c = colores();
    const inicio = desde(meses[rango]);
    const spot = p.historico.brent_spot.filter(([d]) => d >= inicio);
    const futuro = p.historico.brent_futuro.filter(([d]) => d >= inicio);
    const finales = p.previsiones.map((f) => [f.fecha_objetivo, f.precio, f.intervalo[0], f.intervalo[1], f.horizonte]);
    const ultimo = new Date(rango === "6" ? finales[1][0] : finales[2][0]);
    ultimo.setDate(ultimo.getDate() + (rango === "6" ? 20 : 45));
    const fin = ultimo.toISOString().slice(0, 10);
    return {
      ...baseOpciones(),
      grid: { left: 52, right: 28, top: 30, bottom: 40 },
      tooltip: {
        ...baseOpciones().tooltip,
        formatter: (ps) => {
          const fecha = ps[0].axisValueLabel || ps[0].value[0];
          return `<div style="margin-bottom:6px;color:${c.tinta3}">${fmtFecha(String(ps[0].value[0]).slice(0, 10))}</div>` +
            ps.filter((x) => x.seriesName !== "intervalo").map((x) => {
              if (x.seriesName === "Previsión") {
                const v = x.value;
                return lineaTooltip(c.RNN, `Previsión ${NOMBRES_HORIZONTE[v[4]]}`, `${fmt(v[1])} (${fmt(v[2])}–${fmt(v[3])})`);
              }
              return lineaTooltip(x.color, x.seriesName, fmt(x.value[1]));
            }).join("");
        },
      },
      xAxis: ejeTiempo({ min: inicio, max: fin }),
      yAxis: ejeValor({ name: "USD/barril" }),
      series: [
        { name: "Futuro de Brent", type: "line", data: futuro, showSymbol: false, lineStyle: { width: 1.5, color: c.futuros, opacity: .55 }, itemStyle: { color: c.futuros } },
        { name: "Brent spot", type: "line", data: spot, showSymbol: false, lineStyle: { width: 2, color: c.real }, itemStyle: { color: c.real } },
        {
          name: "Referencia", type: "scatter", data: [[origen, p.base.valor]], symbolSize: 10,
          itemStyle: { color: c.acento, borderColor: c.superficie, borderWidth: 2 }, z: 5,
          label: { show: true, formatter: "hoy", position: "left", color: c.tinta2, fontSize: 11 },
        },
        {
          name: "conexiones", type: "lines", coordinateSystem: "cartesian2d", silent: true, tooltip: { show: false },
          data: finales.map((f) => ({
            coords: [[origen, p.base.valor], [f[0], f[1]]],
            lineStyle: { opacity: activa(f) ? .75 : .2, width: activa(f) ? 2 : 1.5 },
          })),
          lineStyle: { color: c.RNN, width: 1.5, opacity: .5, type: "solid" },
        },
        {
          name: "intervalo", type: "custom", tooltip: { show: false }, silent: true, z: 2,
          renderItem: (params, api) => {
            const x = api.coord([api.value(0), api.value(1)]);
            const bajo = api.coord([api.value(0), api.value(2)]);
            const alto = api.coord([api.value(0), api.value(3)]);
            const ancho = 18;
            const tenue = api.value(4) !== horizonteActivo;
            return {
              type: "group", children: [
                { type: "rect", shape: { x: x[0] - ancho / 2, y: alto[1], width: ancho, height: bajo[1] - alto[1], r: 4 }, style: { fill: c.RNN, opacity: tenue ? .07 : .22 } },
                { type: "line", shape: { x1: x[0], y1: alto[1], x2: x[0], y2: bajo[1] }, style: { stroke: c.RNN, lineWidth: 1.5, opacity: tenue ? .25 : .8 } },
              ],
            };
          },
          data: finales, encode: { x: 0, y: [1, 2, 3] },
        },
        {
          name: "Previsión", type: "scatter", symbolSize: 12, z: 6,
          data: finales.map((f) => ({
            value: f, itemStyle: { opacity: activa(f) ? 1 : .35 }, symbolSize: activa(f) ? 14 : 10,
            label: { position: { 5: "bottom", 63: "top", 252: "top" }[f[4]], distance: 10, opacity: activa(f) ? 1 : .5 },
          })),
          itemStyle: { color: c.RNN, borderColor: c.superficie, borderWidth: 2 },
          label: { show: true, color: c.tinta, fontSize: 11, fontWeight: 600, formatter: (x) => `${NOMBRES_HORIZONTE[x.value[4]]}: ${fmt(x.value[1], 1)}` },
        },
      ],
    };
  };
  const entrada = crearGrafica(document.getElementById("grafica-hoy"), construir);
  return () => entrada.grafica.setOption(construir(), true);
}

function pintarFiabilidad(estudio, p) {
  const filas = estudio.test.tabla;
  const modelo = p.modelo.arquitectura;
  const contenido = estudio.horizontes.map((h) => {
    const red = filas.find((f) => f.horizonte === h && f.predictor === modelo);
    const fut = filas.find((f) => f.horizonte === h && f.predictor === "Ingenuo con futuros");
    return `<tr><td>${NOMBRES_HORIZONTE[h]}</td>
      <td class="num ${claseSigno(red.mejora_frente_ingenuo)}">${fmtPct(red.mejora_frente_ingenuo)}</td>
      <td class="num ${claseSigno(red.mejora_frente_futuros)}">${fmtPct(red.mejora_frente_futuros)}</td>
      <td class="num">${fmt(100 * red.cobertura_intervalo, 0)} %</td></tr>`;
  }).join("");
  document.getElementById("tabla-fiabilidad").outerHTML = `
    <div class="tabla-envoltura"><table>
      <thead><tr><th>Horizonte</th><th>Frente al último spot</th><th>Frente al spot con futuros</th><th>Cobertura 80 %</th></tr></thead>
      <tbody>${contenido}</tbody></table></div>
    <p class="nota">Mejora del error absoluto medio de la RNN seleccionada en ${filas.find((f) => f.horizonte === 5).n} orígenes a una semana,
      ${filas.find((f) => f.horizonte === 63).n} a tres meses y ${filas.find((f) => f.horizonte === 252).n} a un año. Negativo significa que la red
      se equivocó más que la referencia. La cobertura es el porcentaje de precios reales que cayeron dentro del intervalo.
      <a href="resultados.html">Ver todos los resultados</a>.</p>${notaReentreno(p.modelo)}`;
}

// Versión reentrenada: no tiene test propio; el tramo de parada temprana es solo una comprobación de cordura.
function notaReentreno(m) {
  if (!m.cordura) return "";
  const filas = Object.entries(m.cordura.interno).map(([h, t]) => `${NOMBRES_HORIZONTE[h]}: ${fmt(t.mae_red_media_semillas)}
    frente a ${fmt(t.mae_ingenuo_con_futuros)} USD`).join("; ");
  return `<p class="nota"><strong>Esta versión (${m.version}) se reentrenó con el mismo método y no tiene test propio:</strong>
    las cifras de la tabla son las del estudio y miden la fiabilidad del método, no de estos pesos. Su error medio en el tramo
    de parada temprana (${filas}, frente al ingenuo con futuros) es solo una comprobación de cordura, no una evaluación nueva:
    ese tramo sirvió para elegir cuándo dejar de entrenar y se solapa con el test del estudio.</p>`;
}

function pintarFuentes(p) {
  const grupos = {};
  for (const [clave, v] of Object.entries(p.fuentes)) {
    const raiz = clave.replace(/_(Open|High|Low|Close|Volume)$/, "");
    (grupos[raiz] ||= []).push(v);
  }
  const sinOpep = (p.avisos || []).some(esAvisoOpep);
  document.getElementById("fuentes").innerHTML = Object.entries(grupos).map(([raiz, valores]) => {
    const ok = valores.every((v) => v.disponible);
    const v = valores.find((x) => x.observacion) || valores[0];
    const detalle = raiz === "cesta_opep" && sinOpep ? "no se usa (ver nota)"
      : `${v.observacion ? fmtFechaCorta(v.observacion) : "sin dato"}${v.edad_dias_habiles != null ? ` · ${v.edad_dias_habiles} d` : ""}`;
    return `<div class="tarjeta" style="padding:14px 18px"><div class="fuente" style="border:0;padding:0">
      <span><span class="punto ${ok ? "" : "no"}"></span>${NOMBRES_FUENTE[raiz] || raiz}</span>
      <span class="num mutado">${detalle}</span>
    </div></div>`;
  }).join("");
  if (sinOpep) pintarNotaOpep(p);
}

// Situación permanente, no un fallo del día: la web de la OPEP rechaza las descargas desde la nube.
function pintarNotaOpep(p) {
  const nota = document.getElementById("nota-opep");
  if (!nota) return;  // HTML anterior en la caché del navegador
  const opep = p.modelo.cordura?.opep;
  const efecto = opep
    ? `Con este modelo, prescindir de la cesta cambió la previsión del ${fmtFecha(opep.origen)} en
      ${Object.entries(opep.diferencias).map(([h, d]) => `${fmtSigno(d, 2)} USD a ${NOMBRES_HORIZONTE[h]}`).join(", ")}`
    : "En el test del estudio, prescindir de la cesta cambió las previsiones de media entre 0,13 y 0,27 USD";
  nota.innerHTML = `<strong>La cesta OPEP no se usa en la previsión diaria.</strong> La previsión se calcula cada mañana
    en servidores de GitHub y la web de la OPEP rechaza las descargas que llegan desde la nube, así que la cesta se trata como
    dato ausente, igual que cuando un dato caduca. El modelo sí la usó al entrenar, por lo que la previsión puede diferir un
    poco de la que daría con ella. ${efecto}, muy por debajo del margen de error.`;
  nota.hidden = false;
}
