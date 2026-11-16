// Página «Hoy»: previsión vigente publicada en Hugging Face.
const NOMBRES_FUENTE = {
  brent: "Brent spot (EIA)", wti: "WTI spot (EIA)", gas_natural: "Gas natural Henry Hub", usd_por_eur: "Dólares por euro",
  cny_por_usd: "Yuanes por dólar", vix: "Volatilidad VIX", tipo_bce: "Tipo de depósito BCE", cesta_opep: "Cesta OPEP",
  brent_fut: "Futuro de Brent", wti_fut: "Futuro de WTI", cobre: "Cobre", oro: "Oro", indice_dolar: "Índice dólar",
};
// La sección que explica el precio de referencia no está aquí: empieza plegada y la abre el usuario.
const SECCIONES_PREVISION = ["previsiones-seccion", "grafica-seccion", "fuentes-seccion"];

document.addEventListener("DOMContentLoaded", async () => {
  const [resPrevision, resEstudio] = await Promise.allSettled([cargarJSON(URL_PREVISION), cargarJSON(URL_ESTUDIO)]);
  const estudio = resEstudio.status === "fulfilled" ? resEstudio.value : null;
  if (estudio) pintarFiabilidad(estudio, resPrevision.value?.modelo);
  else document.getElementById("tabla-fiabilidad").outerHTML = `<p class="nota">No se han podido cargar los resultados del estudio.</p>`;

  if (resPrevision.status !== "fulfilled") {
    mostrarError(document.getElementById("estado"), "No se ha podido cargar la previsión más reciente.");
    document.getElementById("estado-vivo").classList.add("fallo");
    document.getElementById("estado-texto").textContent = "Previsión no disponible";
    document.getElementById("base-valor").textContent = "—";
    return;
  }
  const prevision = resPrevision.value;
  document.getElementById("estado-seccion").hidden = !pintarAvisos(prevision);
  document.getElementById("estado").hidden = true;
  for (const id of SECCIONES_PREVISION) document.getElementById(id).hidden = false;

  pintarEstado(prevision);
  pintarReferencia(prevision);
  pintarFicha(prevision);
  montarDetalleReferencia();
  pintarPrevisiones(prevision);
  const grafica = pintarGrafica(prevision);
  montarSelectorHorizonte(prevision, estudio, grafica);
  pintarFuentes(prevision);
});

// ---------- Momento de la previsión ----------
function partesMadrid(fecha) {
  return Object.fromEntries(new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Madrid", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
    weekday: "short", hourCycle: "h23",
  }).formatToParts(fecha).map((x) => [x.type, x.value]));
}

// Fecha y hora de Madrid en que se calculó la previsión. Es «temprana» si se calculó antes de las 09:00 del día de
// origen (p. ej. una ejecución manual de madrugada) y «tarde» si fue a partir de las 10:00 o un día posterior (GitHub
// Actions retrasó la ejecución programada). En ambos casos los datos son los conocidos a esa hora, no a las 09:00.
function momentoCalculo(p) {
  const partes = partesMadrid(new Date(p.generado_utc));
  const fecha = `${partes.year}-${partes.month}-${partes.day}`;
  const temprano = fecha < p.origen || (fecha === p.origen && Number(partes.hour) < 9);
  const tarde = !temprano && (fecha > p.origen || Number(partes.hour) >= 10);
  const hora = `${partes.hour}:${partes.minute}`;
  const real = temprano || tarde;
  return { fecha, hora, temprano, tarde, horaDatos: real ? hora : "09:00", fechaDatos: real ? fecha : p.origen };
}

function pintarAvisos(p) {
  const avisos = [];
  const calculo = momentoCalculo(p);
  if (calculo.temprano) {
    const cuando = calculo.fecha === p.origen ? `a las ${calculo.hora}`
      : `el ${fmtFecha(calculo.fecha)} a las ${calculo.hora}, para el ${fmtFecha(p.origen)}`;
    avisos.push(`<p><strong>Calculada antes de la hora habitual.</strong> Esta previsión se hizo ${cuando} (hora de Madrid),
      antes de las 09:00. Usa los datos conocidos a esa hora: puede faltar alguno que se publique antes de las 09:00, como un
      cierre de mercado o una cifra de FRED. La próxima ejecución automática la sustituirá.</p>`);
  }
  // La cesta OPEP falla siempre desde GitHub Actions: es una situación permanente y se explica en la sección de
  // fuentes. El recuadro de aviso queda para fallos inesperados (p. ej. el respaldo del BCE en FRED).
  const inesperados = (p.avisos || []).filter((a) => !esAvisoOpep(a));
  if (inesperados.length) avisos.push(`<p><strong>Datos incompletos hoy.</strong> ${inesperados.join(" ")}</p>`);
  document.getElementById("avisos").innerHTML = avisos.length ? `<div class="aviso">${avisos.join("")}</div>` : "";
  return avisos.length > 0;
}

function pintarEstado(p) {
  const calculo = momentoCalculo(p);
  const ahora = partesMadrid(new Date());
  const hoy = `${ahora.year}-${ahora.month}-${ahora.day}`;
  const finDeSemana = ["Sat", "Sun"].includes(ahora.weekday);
  const dia = fmtFecha(p.origen, { weekday: "long", day: "numeric", month: "long" });
  const estado = document.getElementById("estado-vivo");
  let extra = "";
  if (p.origen === hoy) {
    estado.classList.add("al-dia");
    document.getElementById("estado-texto").textContent = `Previsión de hoy · ${dia}`;
  } else {
    estado.classList.add("anterior");
    document.getElementById("estado-texto").textContent = `Última previsión · ${dia}`;
    extra = finDeSemana ? " Los fines de semana no se calcula previsión, porque los mercados no cotizan."
      : " La de hoy aún no se ha publicado: se calcula cada mañana laborable a partir de las 09:15.";
  }
  document.getElementById("fecha-prevision").textContent =
    `Hecha con los datos disponibles a las ${calculo.horaDatos} del ${fmtFecha(calculo.fechaDatos)} (hora de Madrid).${extra}`;
}

// ---------- Precio de referencia ----------
function chispa(valores) {
  if (valores.length < 2) return "";
  const minimo = Math.min(...valores), maximo = Math.max(...valores), rango = maximo - minimo || 1;
  const ANCHO = 300, ALTO = 68, MARGEN = 5;
  const linea = valores.map((v, i) => {
    const x = (i / (valores.length - 1)) * ANCHO, y = MARGEN + (1 - (v - minimo) / rango) * (ALTO - 2 * MARGEN);
    return `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(" ");
  return `<svg viewBox="0 0 ${ANCHO} ${ALTO}" preserveAspectRatio="none">
    <defs><linearGradient id="chispa-relleno" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="currentColor" stop-opacity=".3"/><stop offset="1" stop-color="currentColor" stop-opacity="0"/>
    </linearGradient></defs>
    <path d="${linea} L${ANCHO} ${ALTO} L0 ${ALTO} Z" fill="url(#chispa-relleno)"/>
    <path d="${linea}" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>
  </svg>`;
}

function pintarReferencia(p) {
  const { horaDatos, fechaDatos } = momentoCalculo(p);
  const b = p.base;
  const conFuturos = b.tipo === "futuros";
  document.getElementById("base-titulo").textContent = `Precio de referencia · ${fmtFechaCorta(fechaDatos)}, ${horaDatos}`;
  document.getElementById("base-valor").innerHTML = `${fmt(b.valor)}<small>USD/barril</small>`;
  document.getElementById("base-chip").textContent = conFuturos ? "Último precio puesto al día con futuros" : "Último Brent spot publicado";
  if (conFuturos) {
    const spot = document.getElementById("base-spot");
    spot.textContent = `Spot oficial: ${fmt(b.spot)} USD · ${fmtFechaCorta(b.spot_fecha)}`;
    spot.hidden = false;
  }
  const desde = desplazarFecha(p.origen, { meses: -3 });
  const futuro = p.historico.brent_futuro.filter(([d]) => d >= desde).map(([, v]) => v);
  if (futuro.length > 1) {
    document.getElementById("base-chispa").innerHTML = chispa(futuro);
    const cambio = 100 * (futuro.at(-1) / futuro[0] - 1);
    document.getElementById("base-chispa-pie").innerHTML =
      `<span>Futuro de Brent, últimos 3 meses</span><span class="num ${claseSigno(cambio)}">${fmtPct(cambio)}</span>`;
  }

  if (!conFuturos) {
    document.getElementById("base-resumen").textContent =
      "Hoy no hay futuro de Brent disponible, así que la referencia es el último Brent spot publicado. Es el punto del que parten las tres previsiones.";
    document.getElementById("base-explicacion").innerHTML = `Ese día no había futuro de Brent disponible, así que la referencia
      es el último Brent spot publicado, el del ${fmtFecha(b.spot_fecha)} (${fmtUSD(b.spot)}). Las tres previsiones parten de este valor.`;
    document.getElementById("base-calculo").innerHTML = "";
    document.getElementById("base-ingenuo").hidden = true;
    return;
  }
  // El futuro en la fecha del spot viene en el JSON; en previsiones antiguas se deduce de la propia fórmula.
  const futuroBase = b.futuro_base ?? (b.spot * b.futuro / b.valor);
  const fechaFuturoBase = b.futuro_base_fecha ?? b.spot_fecha;
  const variacion = 100 * (b.futuro / futuroBase - 1);
  document.getElementById("base-explicacion").innerHTML = `
    Es el <strong>precio del Brent puesto al día</strong>, no una previsión. El Brent spot oficial se publica con una semana
    de retraso, así que a las ${horaDatos} el último conocido era el del ${fmtFecha(b.spot_fecha)}. Para saber dónde está el
    precio hoy, se le aplica lo que ha variado desde entonces el <strong>futuro de Brent</strong>, que cotiza a diario y es
    el precio que sigue el mercado. Las tres previsiones parten de este valor.`;
  document.getElementById("base-calculo").innerHTML = `
    <span>Último Brent spot publicado (${fmtFechaCorta(b.spot_fecha)})</span><b>${fmtUSD(b.spot)}</b>
    <span>Futuro de Brent el ${fmtFechaCorta(fechaFuturoBase)}</span><b>${fmtUSD(futuroBase)}</b>
    <span>Futuro de Brent el ${fmtFechaCorta(b.futuro_fecha)} (último cierre conocido)</span><b>${fmtUSD(b.futuro)}</b>
    <span>Variación del futuro en ese tiempo</span><b class="${claseSigno(variacion)}">${fmtPct(variacion, 2)}</b>
    <span class="total">${fmt(b.spot)} × ${fmt(b.futuro)} / ${fmt(futuroBase)}</span><b class="total">${fmtUSD(b.valor)}</b>`;
  document.getElementById("base-ingenuo").innerHTML = `El ingenuo del enunciado, repetir el último spot publicado
    (${fmtUSD(b.spot)}), no se usa como referencia diaria: es un precio de hace una semana. Sí se usa en el
    <a href="resultados.html">estudio</a>, donde las redes se comparan con las dos referencias.`;
}

// El detalle del precio de referencia (cálculo y ficha) empieza plegado para que el precio y las previsiones se vean
// juntos; se abre y se cierra desde la tarjeta del precio.
function montarDetalleReferencia() {
  const boton = document.getElementById("alternar-referencia");
  const seccion = document.getElementById("referencia-seccion");
  const fijar = (abierto) => {
    seccion.hidden = !abierto;
    boton.setAttribute("aria-expanded", String(abierto));
    boton.querySelector("span").textContent = abierto ? "Ocultar el detalle" : "Cómo se calcula y con qué datos";
  };
  boton.hidden = false;
  boton.addEventListener("click", () => {
    const abrir = seccion.hidden;
    fijar(abrir);
    if (abrir) seccion.scrollIntoView({ block: "start" });
  });
  document.getElementById("cerrar-referencia").addEventListener("click", () => {
    fijar(false);
    boton.focus({ preventScroll: true });
    boton.closest(".tarjeta").scrollIntoView({ block: "center" });
  });
}

function pintarFicha(p) {
  const calculo = momentoCalculo(p);
  document.getElementById("ficha").innerHTML = `
    <dt>Datos usados</dt><dd>Los conocidos a las ${calculo.horaDatos} del ${fmtFecha(calculo.fechaDatos)}</dd>
    <dt>Modelo</dt><dd>${p.modelo.arquitectura} · media de ${p.modelo.semillas.length} semillas</dd>
    <dt>Versión</dt><dd class="num">${p.modelo.version}</dd>
    ${filasEntrenamiento(p.modelo)}
    <dt>Calculada</dt><dd>${fmtFecha(calculo.fecha)} a las ${calculo.hora} (hora de Madrid)${calculo.tarde ? `
      <div class="aclaracion">La tarea diaria está programada a las 09:15 en GitHub Actions, que a veces retrasa las
        ejecuciones programadas; si no llega a su hora, se reintenta cada hora durante el día. Por eso esta previsión usa los
        datos conocidos a las ${calculo.hora}. Las reglas de publicación de cada dato no cambian, así que la diferencia con las
        09:00 suele ser mínima.</div>` : ""}</dd>
    <dt>Archivos</dt><dd><a href="${URL_MODELO}">Modelo</a> · <a href="${URL_DATOS_HF}">historial de previsiones</a></dd>`;
}

// Con la parada temprana y el retraso de las etiquetas, «datos hasta la fecha de corte» sería engañoso:
// se muestran, por horizonte, los orígenes de aprendizaje y los de parada temprana.
function filasEntrenamiento(m) {
  const tramos = m.tramos || {};
  const horizontes = Object.keys(tramos).map(Number).sort((a, b) => a - b);
  if (!horizontes.length) return `<dt>Fecha de corte</dt><dd>${fmtFecha(m.entrenamiento)}</dd>`;
  const lineas = horizontes.map((h) => {
    const t = tramos[h];
    return `<div><strong>${NOMBRES_HORIZONTE[h] || `+${h}`}:</strong> aprendizaje hasta ${fmtFechaCorta(t.aprendizaje.fin)} ·
      parada temprana hasta ${fmtFechaCorta(t.interno.fin)}</div>`;
  }).join("");
  return `<dt>Fecha de corte</dt><dd>${fmtFecha(m.entrenamiento)}: solo precios ya publicados ese día</dd>
    <dt>Entrenamiento</dt><dd>${lineas}
      <div class="aclaracion">Fechas de origen de las ventanas: cada una se compara con el precio 5, 63 o 252 días hábiles
        después, publicado una semana más tarde. El último 15 % se reserva para decidir cuándo dejar de entrenar (parada
        temprana).</div></dd>`;
}

// ---------- Las tres previsiones ----------
function pintarPrevisiones(p) {
  document.getElementById("previsiones").innerHTML = p.previsiones.map((f) => {
    const [bajo, alto] = f.intervalo;
    const minimo = Math.min(bajo, p.base.valor), maximo = Math.max(alto, p.base.valor);
    const margen = (maximo - minimo) * 0.08;
    const pos = (v) => ((v - (minimo - margen)) / (maximo - minimo + 2 * margen)) * 100;
    const pct = f.variacion_pct_frente_base;
    const plano = Math.abs(pct) < 0.05;
    const nombre = NOMBRES_HORIZONTE[f.horizonte] || `+${f.horizonte}`;
    return `<article class="tarjeta prevision" data-horizonte="${f.horizonte}" role="button" tabindex="0" aria-pressed="false"
      aria-label="Previsión a ${nombre}: ${fmt(f.precio)} dólares. Ver su explicación">
      <div class="prevision-cabecera">
        <h3>${nombre}<span class="fecha-objetivo">${fmtFecha(f.fecha_objetivo)}</span></h3>
        <span class="delta num ${plano ? "" : claseSigno(pct)}" title="Variación frente al precio de referencia">${plano ? "=" : pct > 0 ? "▲" : "▼"} ${fmtPct(pct)}</span>
      </div>
      <div class="precio num">${fmt(f.precio)}<small>USD</small></div>
      <div>
        <div class="barra-intervalo" aria-hidden="true">
          <span style="left:${pos(bajo)}%;right:${100 - pos(alto)}%"></span>
          <em style="left:${pos(p.base.valor)}%" title="Precio de referencia"></em><b style="left:${pos(f.precio)}%"></b>
        </div>
        <div class="extremos num" style="margin-top:10px"><span>${fmt(bajo)}</span><span>intervalo del 80 %</span><span>${fmt(alto)}</span></div>
      </div>
      <div class="rango num">
        <div><span>Cambio previsto</span><span class="${claseSigno(f.variacion_frente_base)}">${fmtSigno(f.variacion_frente_base, 2)} USD</span></div>
        <div><span>Margen de error</span><span>± ${fmt(f.margen)} USD</span></div>
        <div><span>Días hábiles hasta el objetivo</span><span>${f.horizonte}</span></div>
      </div>
      <div class="prevision-pie">Ver qué significa ${ICONOS.flecha}</div>
    </article>`;
  }).join("");
}

// Horizonte elegido por el usuario: destaca su tarjeta y su previsión en la gráfica y explica su significado.
let horizonteActivo = 5;

function montarSelectorHorizonte(p, estudio, grafica) {
  const selector = document.getElementById("selector-horizonte");
  if (!p.previsiones.some((f) => f.horizonte === horizonteActivo)) horizonteActivo = p.previsiones[0].horizonte;
  const elegir = (h) => {
    horizonteActivo = h;
    marcarSegmentado(selector, h);
    document.querySelectorAll("#previsiones .prevision").forEach((t) => {
      const activa = Number(t.dataset.horizonte) === h;
      t.classList.toggle("activa", activa);
      t.setAttribute("aria-pressed", String(activa));
    });
    document.getElementById("explicacion-horizonte").innerHTML = explicarHorizonte(p, estudio, h);
    grafica.mostrarHorizonte(h);
  };
  segmentado(selector, p.previsiones.map((f) => [String(f.horizonte), NOMBRES_HORIZONTE[f.horizonte] || `+${f.horizonte}`]),
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
  const red = estudio?.test.tabla.find((x) => x.horizonte === h && x.predictor === p.modelo.arquitectura);
  const [bajo, alto] = f.intervalo;
  const pct = f.variacion_pct_frente_base;
  const sentido = Math.abs(pct) < 0.05 ? "prácticamente igual al"
    : `un ${fmt(Math.abs(pct), 1)} % ${pct > 0 ? "por encima del" : "por debajo del"}`;
  const nombre = NOMBRES_HORIZONTE[h] || `+${h}`;
  let fiabilidad = "No se han podido cargar los resultados del estudio para este horizonte.";
  if (red) {
    const frente = (mejora, quien) => `un ${fmt(Math.abs(mejora), 1)} % ${mejora >= 0 ? "menos" : "más"} que ${quien}`;
    const [peorAnio, peorCobertura] = Object.entries(red.cobertura_por_anio).sort((a, b) => a[1] - b[1])[0];
    let veredicto;
    if (red.mejora_frente_ingenuo > 0 && red.mejora_frente_futuros >= 0) {
      veredicto = "A este plazo la red mejoró a las dos referencias.";
    } else if (red.mejora_frente_ingenuo > 0) {
      veredicto = `<strong>A este plazo aporta valor frente a repetir el último precio publicado, pero no frente a seguir el
        futuro de Brent:</strong> úsala como una referencia razonable de corto plazo, no como una ventaja sobre el mercado.`;
    } else {
      veredicto = `<strong>A este plazo la previsión no aportó valor fiable frente a las referencias:</strong> tómala como una
        orientación del rango posible, no como un objetivo.`;
    }
    fiabilidad = `En el test del estudio (${red.n} previsiones de 2023 a 2026), la red se equivocó
      ${frente(red.mejora_frente_ingenuo, "repetir el último precio spot conocido")} y
      ${frente(red.mejora_frente_futuros, "la regla simple de actualizarlo con el futuro de Brent")}. Acertó si el precio
      subía o bajaba el ${fmt(100 * red.acierto_direccional, 0)} % de las veces, y el precio real quedó dentro del intervalo
      el ${fmt(100 * red.cobertura_intervalo, 0)} % (lo previsto era el 80 %; en ${peorAnio}, solo el
      ${fmt(100 * peorCobertura, 0)} %). ${veredicto}`;
  }
  return `
    <div class="explicacion-cabecera">
      <h3>La previsión a ${nombre}, explicada</h3>
      <span class="chip">Objetivo: ${fmtFecha(f.fecha_objetivo)}</span>
    </div>
    <div class="explicacion-rejilla">
      <div><h4><span class="icono-redondo">${ICONOS.significado}</span>Qué significa</h4>
        <p>El modelo estima que el ${fmtFecha(f.fecha_objetivo)}, ${PLAZOS[h] || `dentro de ${h} días hábiles`}, el Brent spot
          estará en torno a <strong>${fmtUSD(f.precio)}</strong> por barril, ${sentido} precio de referencia
          (${fmtUSD(p.base.valor)}). No es un precio exacto: lo razonable es esperar un valor entre
          <strong>${fmt(bajo)} y ${fmt(alto)} USD</strong>; en la validación, en 8 de cada 10 casos el precio real quedó a
          menos de ${fmtUSD(f.margen)} de lo previsto.</p></div>
      <div><h4><span class="icono-redondo">${ICONOS.fiabilidad}</span>Cuánto fiarse</h4><p>${fiabilidad}</p></div>
      <div><h4><span class="icono-redondo">${ICONOS.riesgo}</span>Qué puede invalidarla</h4>
        <p>${RIESGOS[h] || "Cualquier acontecimiento que no esté en los datos pasados."} Además, el intervalo tiene una anchura
          fija y se queda corto cuando el mercado está muy agitado.</p></div>
    </div>`;
}

const esAvisoOpep = (aviso) => aviso.includes("cesta OPEP");

// ---------- Gráfica ----------
function pintarGrafica(p) {
  const meses = { "6": 6, "18": 18, "60": 60 };
  let rango = "18";
  const selector = document.getElementById("selector-rango");
  segmentado(selector, [["6", "6 meses"], ["18", "18 meses"], ["60", "5 años"]], (v) => { rango = v; redibujar(); }, rango);
  document.getElementById("leyenda-hoy").innerHTML = `
    <span><i style="background:${VAR.real}"></i>Brent spot publicado</span>
    <span><i style="background:${VAR.futuros};opacity:.6"></i>Futuro de Brent</span>
    <span><i class="punto" style="background:${VAR.acento};border-radius:2px;transform:rotate(45deg) scale(.85)"></i>Precio de referencia</span>
    <span><i class="punto" style="background:${VAR.RNN}"></i>Previsión (${p.modelo.arquitectura})</span>
    <span><i class="banda" style="background:${VAR.RNN}"></i>Intervalo del 80 %</span>`;
  const origen = p.origen;
  const finales = p.previsiones.map((f) => [f.fecha_objetivo, f.precio, f.intervalo[0], f.intervalo[1], f.horizonte]);
  const activa = (f) => f[4] === horizonteActivo;  // f = [fecha, precio, bajo, alto, horizonte]
  const construir = () => {
    const c = colores();
    const inicio = desplazarFecha(origen, { meses: -meses[rango] });
    const spot = p.historico.brent_spot.filter(([d]) => d >= inicio);
    const futuro = p.historico.brent_futuro.filter(([d]) => d >= inicio);
    // En la vista de 6 meses solo caben los dos primeros horizontes; en las demás, los tres.
    const ultimoVisible = rango === "6" && finales.length > 2 ? finales[finales.length - 2] : finales[finales.length - 1];
    const fin = desplazarFecha(ultimoVisible[0], { dias: rango === "6" ? 20 : 45 });
    const posicion = (h) => (h === finales[0][4] ? "bottom" : "top");
    return {
      ...baseOpciones(),
      grid: { left: 52, right: 28, top: 38, bottom: 40 },
      tooltip: {
        ...baseOpciones().tooltip,
        formatter: (ps) => {
          if (!ps.length) return "";
          return cabeceraTooltip(fmtFecha(String(ps[0].value[0])), c.tinta3) +
            ps.map((x) => {
              if (x.seriesName === "Previsión") {
                const v = x.value;
                return lineaTooltip(c.RNN, `Previsión a ${NOMBRES_HORIZONTE[v[4]] || `+${v[4]}`}`, `${fmt(v[1])} (${fmt(v[2])}–${fmt(v[3])})`);
              }
              return lineaTooltip(x.color, x.seriesName, fmt(x.value[1]));
            }).join("");
        },
      },
      xAxis: ejeTiempo({ min: inicio, max: fin }),
      yAxis: ejeValor({ name: "USD/barril" }),
      series: [
        { name: "Futuro de Brent", type: "line", data: futuro, showSymbol: false, lineStyle: { width: 1.5, color: c.futuros, opacity: .6 }, itemStyle: { color: c.futuros } },
        {
          name: "Brent spot", type: "line", data: spot, showSymbol: false, lineStyle: { width: 2, color: c.real }, itemStyle: { color: c.real },
          areaStyle: areaDegradada(c.real, .1),
        },
        {
          // Rombo por encima de las previsiones: a una semana vista, los dos puntos casi coinciden.
          name: "Precio de referencia", type: "scatter", data: [[origen, p.base.valor]], symbol: "diamond", symbolSize: 13,
          itemStyle: { color: c.acento, borderColor: c.superficie, borderWidth: 2 }, z: 7,
        },
        {
          name: "conexiones", type: "lines", coordinateSystem: "cartesian2d", silent: true, tooltip: { show: false },
          data: finales.map((f) => ({
            coords: [[origen, p.base.valor], [f[0], f[1]]],
            lineStyle: { opacity: activa(f) ? .8 : .2, width: activa(f) ? 2 : 1.5, type: activa(f) ? "solid" : [4, 4] },
          })),
          lineStyle: { color: c.RNN, width: 1.5, opacity: .5 },
        },
        {
          name: "intervalo", type: "custom", tooltip: { show: false }, silent: true, z: 2,
          renderItem: (params, api) => {
            const x = api.coord([api.value(0), api.value(1)]);
            const bajo = api.coord([api.value(0), api.value(2)]);
            const alto = api.coord([api.value(0), api.value(3)]);
            const ancho = 20;
            const tenue = api.value(4) !== horizonteActivo;
            return {
              type: "group", children: [
                { type: "rect", shape: { x: x[0] - ancho / 2, y: alto[1], width: ancho, height: bajo[1] - alto[1], r: 6 }, style: { fill: c.RNN, opacity: tenue ? .07 : .22 } },
                { type: "line", shape: { x1: x[0], y1: alto[1], x2: x[0], y2: bajo[1] }, style: { stroke: c.RNN, lineWidth: 1.5, opacity: tenue ? .25 : .8 } },
              ],
            };
          },
          data: finales, encode: { x: 0, y: [1, 2, 3] },
        },
        {
          name: "Previsión", type: "scatter", symbolSize: 12, z: 6,
          data: finales.map((f) => ({
            value: f, itemStyle: { opacity: activa(f) ? 1 : .4 }, symbolSize: activa(f) ? 15 : 10,
            label: { position: posicion(f[4]), distance: 10, opacity: activa(f) ? 1 : .55 },
          })),
          itemStyle: { color: c.RNN, borderColor: c.superficie, borderWidth: 2 },
          label: { show: true, color: c.tinta, fontSize: 11.5, fontWeight: 600, formatter: (x) => `${NOMBRES_HORIZONTE[x.value[4]] || `+${x.value[4]}`}: ${fmt(x.value[1], 1)}` },
        },
      ],
    };
  };
  const entrada = crearGrafica(document.getElementById("grafica-hoy"), construir);
  const redibujar = () => entrada.grafica.setOption(construir(), true);
  return {
    // Destaca el horizonte elegido; si no cabe en la vista de 6 meses, pasa a la de 18.
    mostrarHorizonte(h) {
      const fueraDeVista = rango === "6" && finales.length > 2 && h === finales[finales.length - 1][4];
      if (fueraDeVista) { rango = "18"; marcarSegmentado(selector, rango); }
      redibujar();
    },
  };
}

// ---------- Fiabilidad ----------
function pintarFiabilidad(estudio, modelo) {
  const filas = estudio.test.tabla;
  const arquitectura = modelo?.arquitectura || estudio.seleccionada;
  const de = (h, predictor) => filas.find((f) => f.horizonte === h && f.predictor === predictor);
  const contenido = estudio.horizontes.map((h) => {
    const red = de(h, arquitectura);
    if (!red) return "";
    return `<tr><td>${NOMBRES_HORIZONTE[h]}</td>
      <td class="num ${claseSigno(red.mejora_frente_ingenuo)}">${fmtPct(red.mejora_frente_ingenuo)}</td>
      <td class="num ${claseSigno(red.mejora_frente_futuros)}">${fmtPct(red.mejora_frente_futuros)}</td>
      <td class="num">${fmt(100 * red.cobertura_intervalo, 0)} %</td></tr>`;
  }).join("");
  const origenes = estudio.horizontes.map((h) => de(h, arquitectura)?.n).filter(Boolean);
  document.getElementById("tabla-fiabilidad").outerHTML = `
    <div class="tabla-envoltura"><table>
      <thead><tr><th>Horizonte</th><th>Frente al último spot</th><th>Frente al spot con futuros</th><th>Cobertura 80 %</th></tr></thead>
      <tbody>${contenido}</tbody></table></div>
    <p class="nota">Mejora del error absoluto medio de la ${arquitectura} seleccionada${origenes.length === 3
      ? ` en ${origenes[0]} orígenes a una semana, ${origenes[1]} a tres meses y ${origenes[2]} a un año` : ""}. Negativo
      significa que la red se equivocó más que la referencia. La cobertura es el porcentaje de precios reales que cayeron
      dentro del intervalo. <a href="resultados.html">Ver todos los resultados</a>.</p>${notaReentreno(modelo)}`;
}

// Versión reentrenada: no tiene test propio; el tramo de parada temprana es solo una comprobación de cordura.
function notaReentreno(m) {
  if (!m?.cordura) return "";
  const filas = Object.entries(m.cordura.interno).map(([h, t]) => `${NOMBRES_HORIZONTE[h] || `+${h}`}: ${fmt(t.mae_red_media_semillas)}
    frente a ${fmt(t.mae_ingenuo_con_futuros)} USD`).join("; ");
  return `<p class="nota"><strong>Esta versión (${m.version}) se reentrenó con el mismo método y no tiene test propio:</strong>
    las cifras de la tabla son las del estudio y miden la fiabilidad del método, no de estos pesos. Su error medio en el tramo
    de parada temprana (${filas}, frente al ingenuo con futuros) es solo una comprobación de cordura, no una evaluación nueva:
    ese tramo sirvió para elegir cuándo dejar de entrenar y se solapa con el test del estudio.</p>`;
}

// ---------- Fuentes ----------
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
    const edad = v.edad_dias_habiles;
    const detalle = raiz === "cesta_opep" && sinOpep ? "no se usa (ver nota)"
      : `${v.observacion ? fmtFechaCorta(v.observacion) : "sin dato"}${edad != null ? ` · ${edad} ${edad === 1 ? "día" : "días"}` : ""}`;
    return `<div class="fuente">
      <span><span class="punto ${ok ? "" : "no"}" title="${ok ? "Disponible" : "No disponible"}"></span>${NOMBRES_FUENTE[raiz] || raiz}</span>
      <span class="num">${detalle}</span>
    </div>`;
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
      ${Object.entries(opep.diferencias).map(([h, d]) => `${fmtSigno(d, 2)} USD a ${NOMBRES_HORIZONTE[h] || `+${h}`}`).join(", ")}`
    : "En el test del estudio, prescindir de la cesta cambió las previsiones de media entre 0,13 y 0,27 USD";
  nota.innerHTML = `<strong>La cesta OPEP no se usa en la previsión diaria.</strong> La previsión se calcula cada mañana
    en servidores de GitHub y la web de la OPEP rechaza las descargas que llegan desde la nube, así que la cesta se trata como
    dato ausente, igual que cuando un dato caduca. El modelo sí la usó al entrenar, por lo que la previsión puede diferir un
    poco de la que daría con ella. ${efecto}, muy por debajo del margen de error.`;
  nota.hidden = false;
}
