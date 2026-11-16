// Utilidades comunes: navegación, tema, datos, formato y gráficas.
const URL_PREVISION = "https://huggingface.co/datasets/AvaroSantamaria/brent-predicciones/resolve/main/prediccion.json";
const URL_ESTUDIO = "datos/estudio.json";
const URL_MODELO = "https://huggingface.co/AvaroSantamaria/brent-rnn";
const URL_DATOS_HF = "https://huggingface.co/datasets/AvaroSantamaria/brent-predicciones";
const URL_GITHUB = "https://github.com/AlvaroSantamariaAnton/oil-price-prediction";

const PAGINAS = [
  ["index.html", "Hoy"],
  ["historia.html", "Histórico"],
  ["datos.html", "Datos y método"],
  ["experimentos.html", "Experimentos"],
  ["resultados.html", "Resultados"],
];
const NOMBRES_HORIZONTE = { 5: "1 semana", 63: "3 meses", 252: "1 año" };
const DESCRIPCION_HORIZONTE = { 5: "+5 fechas", 63: "+63 fechas", 252: "+252 fechas" };

const ICONO = `<svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="9" fill="var(--tinta)"/>
<path d="M16 6c3.6 4.6 6.5 8.6 6.5 12.1A6.5 6.5 0 0 1 16 24.6a6.5 6.5 0 0 1-6.5-6.5C9.5 14.6 12.4 10.6 16 6z" fill="var(--acento)"/>
<path d="M12.6 19.4c.6 1.8 2 2.9 3.8 3" stroke="var(--fondo)" stroke-width="1.6" fill="none" stroke-linecap="round"/></svg>`;
const ICONOS = {
  flecha: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>`,
  significado: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16.5v.5"/></svg>`,
  fiabilidad: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l8 3v6c0 4.5-3.2 7.8-8 9-4.8-1.2-8-4.5-8-9V6l8-3z"/><path d="M9 12l2.2 2.2L15 10"/></svg>`,
  riesgo: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4l9 16H3L12 4z"/><path d="M12 10v4M12 17v.5"/></svg>`,
};

// Nombre de la página actual sin extensión (admite direcciones con y sin «.html»).
function paginaActual() {
  const ultimo = location.pathname.split("/").pop() || "index.html";
  return ultimo.replace(/\.html$/, "") || "index";
}

function temaDelSistema() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "oscuro" : "claro";
}
function temaGuardado() {
  try { return localStorage.getItem("tema"); } catch (e) { return null; }
}
// El tema se fija en <head> antes de pintar; aquí solo se garantiza que exista.
if (!document.documentElement.dataset.tema) document.documentElement.dataset.tema = temaGuardado() || temaDelSistema();

function montarCabecera() {
  const actual = paginaActual();
  const indice = PAGINAS.findIndex(([href]) => href.replace(/\.html$/, "") === actual);
  const enlaces = PAGINAS.map(([href, texto], i) =>
    `<a href="${href}"${i === indice ? ' aria-current="page"' : ""}>${texto}</a>`).join("");
  document.body.insertAdjacentHTML("afterbegin", `
    <a class="oculto-visual" href="#contenido-principal">Saltar al contenido</a>
    <header class="cabecera"><div class="contenedor">
      <a class="marca" href="index.html" aria-label="Brentcast, inicio">${ICONO}
        <span class="marca-texto">Brentcast<small>Previsión del Brent con redes recurrentes</small></span></a>
      <nav class="nav" id="navegacion" aria-label="Secciones">${enlaces}</nav>
      <div class="acciones">
        <button class="boton-icono boton-tema" type="button" aria-label="Cambiar entre tema claro y oscuro" title="Cambiar tema">
          <svg class="luna" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>
          <svg class="sol" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
        </button>
        <button class="boton-icono boton-menu" type="button" aria-label="Abrir menú" aria-expanded="false" aria-controls="navegacion">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg>
        </button>
      </div>
    </div></header>`);
  const principal = document.querySelector("main");
  if (principal) principal.id = "contenido-principal";

  // Enlaces a la página anterior y a la siguiente, y pie.
  const anterior = indice > 0 ? PAGINAS[indice - 1] : null;
  const siguiente = indice >= 0 && indice < PAGINAS.length - 1 ? PAGINAS[indice + 1] : null;
  const paginacion = anterior || siguiente ? `<nav class="contenedor paginacion" aria-label="Seguir leyendo">
      ${anterior ? `<a class="anterior" href="${anterior[0]}"><small>← Anterior</small><span>${anterior[1]}</span></a>` : ""}
      ${siguiente ? `<a class="siguiente" href="${siguiente[0]}"><small>Siguiente →</small><span>${siguiente[1]}</span></a>` : ""}
    </nav>` : "";
  document.body.insertAdjacentHTML("beforeend", `${paginacion}
    <footer class="pie"><div class="contenedor">
      <div class="pie-rejilla">
        <div>
          <a class="marca" href="index.html">${ICONO}<span class="marca-texto">Brentcast</span></a>
          <p>Previsión diaria del precio del Brent con una red recurrente y el estudio que la respalda: una comparación
            de RNN, LSTM y GRU con datos tal como se conocían cada mañana.</p>
        </div>
        <div>
          <h4>Páginas</h4>
          <ul>${PAGINAS.map(([href, texto]) => `<li><a href="${href}">${texto}</a></li>`).join("")}</ul>
        </div>
        <div>
          <h4>Recursos</h4>
          <ul>
            <li><a href="${URL_GITHUB}">Código en GitHub</a></li>
            <li><a href="${URL_MODELO}">Modelo en Hugging Face</a></li>
            <li><a href="${URL_DATOS_HF}">Historial de previsiones</a></li>
          </ul>
        </div>
      </div>
      <div class="pie-legal">
        <span>Trabajo académico. No es una recomendación de inversión.</span>
        <span>Datos: EIA, Reserva Federal y Cboe (vía FRED), Yahoo Finance, OPEP y BCE.</span>
      </div>
    </div></footer>`);

  const cabecera = document.querySelector(".cabecera");
  const menu = document.querySelector(".boton-menu");
  const nav = document.querySelector(".nav");
  const cerrarMenu = () => {
    nav.classList.remove("abierto");
    menu.setAttribute("aria-expanded", "false");
    menu.setAttribute("aria-label", "Abrir menú");
  };
  menu.addEventListener("click", () => {
    const abierto = nav.classList.toggle("abierto");
    menu.setAttribute("aria-expanded", String(abierto));
    menu.setAttribute("aria-label", abierto ? "Cerrar menú" : "Abrir menú");
  });
  nav.addEventListener("click", (e) => { if (e.target.closest("a")) cerrarMenu(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") cerrarMenu(); });
  document.addEventListener("click", (e) => { if (!cabecera.contains(e.target)) cerrarMenu(); });
  window.matchMedia("(min-width: 901px)").addEventListener("change", cerrarMenu);

  document.querySelector(".boton-tema").addEventListener("click", () => {
    const nuevo = document.documentElement.dataset.tema === "oscuro" ? "claro" : "oscuro";
    document.documentElement.dataset.tema = nuevo;
    try { localStorage.setItem("tema", nuevo); } catch (e) { /* sin almacenamiento */ }
    redibujarTodo();
  });

  const alDesplazar = () => cabecera.classList.toggle("con-sombra", window.scrollY > 8);
  window.addEventListener("scroll", alDesplazar, { passive: true });
  alDesplazar();
  activarRevelado();
}

// Si el usuario no ha elegido tema, se sigue el del sistema cuando cambia.
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if (temaGuardado()) return;
  document.documentElement.dataset.tema = temaDelSistema();
  redibujarTodo();
});

// Aparición suave de los bloques principales al entrar en pantalla (sin efecto si el usuario pide menos movimiento).
function activarRevelado() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  let pendientes = [...document.querySelectorAll("main section > .contenedor > *")];
  pendientes.forEach((bloque) => bloque.classList.add("revelar"));
  // Se comprueba la posición directamente (sin depender de observadores, que se retrasan en pestañas en segundo plano).
  const comprobar = () => {
    const limite = window.innerHeight * 0.96;
    pendientes = pendientes.filter((bloque) => {
      const caja = bloque.getBoundingClientRect();
      const oculto = caja.width === 0 && caja.height === 0;  // dentro de una sección aún oculta
      if (oculto || caja.top > limite) return true;
      bloque.classList.add("visible");
      return false;
    });
    if (!pendientes.length) {
      window.removeEventListener("scroll", comprobar);
      window.removeEventListener("resize", comprobar);
      observadorCambios.disconnect();
    }
  };
  // Las secciones que se muestran al cargar los datos cambian la altura de la página: se vuelve a comprobar.
  const observadorCambios = new MutationObserver(comprobar);
  observadorCambios.observe(document.querySelector("main"), { attributes: true, attributeFilter: ["hidden"], subtree: true, childList: true });
  window.addEventListener("scroll", comprobar, { passive: true });
  window.addEventListener("resize", comprobar);
  comprobar();
}

// ---------- Datos ----------
async function cargarJSON(url) {
  const respuesta = await fetch(url, { cache: "no-cache" });
  if (!respuesta.ok) throw new Error(`No se pudo cargar ${url} (${respuesta.status})`);
  return respuesta.json();
}
// Mensaje de error con botón para reintentar, dentro de un contenedor.
function mostrarError(contenedor, mensaje) {
  contenedor.classList.remove("cargando");
  contenedor.innerHTML = `<div class="estado-error"><p class="error"><strong>${mensaje}</strong></p>
    <p class="mutado pequeno">Comprueba la conexión y vuelve a intentarlo.</p>
    <button class="boton secundario" type="button">Reintentar</button></div>`;
  contenedor.querySelector("button").addEventListener("click", () => location.reload());
}

// ---------- Formato ----------
const fmt = (v, d = 2) => v == null || Number.isNaN(v) ? "—" : v.toLocaleString("es-ES", { minimumFractionDigits: d, maximumFractionDigits: d });
const fmtSigno = (v, d = 1) => v == null ? "—" : (v > 0 ? "+" : v < 0 ? "−" : "") + fmt(Math.abs(v), d);
const fmtPct = (v, d = 1) => v == null ? "—" : `${fmtSigno(v, d)} %`;
const fmtUSD = (v, d = 2) => `${fmt(v, d)} USD`;
function fmtFecha(iso, opciones = { day: "numeric", month: "long", year: "numeric" }) {
  if (!iso) return "—";
  const [a, m, d] = String(iso).slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(a, m - 1, d)).toLocaleDateString("es-ES", { ...opciones, timeZone: "UTC" });
}
const fmtFechaCorta = (iso) => fmtFecha(iso, { day: "numeric", month: "short", year: "numeric" });
const claseSigno = (v) => v > 0 ? "sube" : v < 0 ? "baja" : "";
// Fecha ISO desplazada un número de meses o de días (en UTC, para no depender de la zona horaria del navegador).
function desplazarFecha(iso, { meses = 0, dias = 0 }) {
  const [a, m, d] = iso.slice(0, 10).split("-").map(Number);
  const fecha = new Date(Date.UTC(a, m - 1, d));
  fecha.setUTCMonth(fecha.getUTCMonth() + meses);
  fecha.setUTCDate(fecha.getUTCDate() + dias);
  return fecha.toISOString().slice(0, 10);
}

// ---------- Gráficas ----------
// Colores para leyendas HTML: variables CSS, que cambian solas con el tema (las gráficas usan colores()).
const VAR = {
  real: "var(--real)", futuros: "var(--futuros)", ingenuo: "var(--ingenuo)", acento: "var(--acento)", tinta3: "var(--tinta-3)",
  RNN: "var(--rnn)", LSTM: "var(--lstm)", GRU: "var(--gru)",
};
const graficas = [];
function css(nombre) { return getComputedStyle(document.documentElement).getPropertyValue(nombre).trim(); }
function colores() {
  return {
    tinta: css("--tinta"), tinta2: css("--tinta-2"), tinta3: css("--tinta-3"), rejilla: css("--rejilla"),
    superficie: css("--superficie"), acento: css("--acento"), acentoSuave: css("--acento-suave"),
    RNN: css("--rnn"), LSTM: css("--lstm"), GRU: css("--gru"), ingenuo: css("--ingenuo"), futuros: css("--futuros"),
    real: css("--real"), bien: css("--bien"), mal: css("--mal"),
  };
}
function baseOpciones() {
  const c = colores();
  return {
    backgroundColor: "transparent",
    textStyle: { fontFamily: "Inter, system-ui, sans-serif", color: c.tinta2 },
    animationDuration: 600, animationEasing: "cubicOut",
    grid: { left: 56, right: 24, top: 24, bottom: 48, containLabel: false },
    tooltip: {
      trigger: "axis", backgroundColor: c.superficie, borderColor: c.rejilla, borderWidth: 1, padding: [10, 14],
      textStyle: { color: c.tinta, fontSize: 12.5 }, extraCssText: "box-shadow:0 14px 34px -10px rgba(0,0,0,.28);border-radius:12px;",
      axisPointer: { type: "line", lineStyle: { color: c.tinta3, width: 1, type: [4, 4] } },
    },
  };
}
function ejeTiempo(extra = {}) {
  const c = colores();
  return {
    type: "time", axisLine: { lineStyle: { color: c.rejilla } }, axisTick: { show: false },
    axisLabel: { color: c.tinta3, hideOverlap: true, fontSize: 11.5 }, splitLine: { show: false }, ...extra,
  };
}
function ejeValor(extra = {}) {
  const c = colores();
  return {
    type: "value", scale: true, axisLine: { show: false }, axisTick: { show: false },
    axisLabel: { color: c.tinta3, fontSize: 11.5 }, splitLine: { lineStyle: { color: c.rejilla, width: 1, type: [3, 4] } },
    nameTextStyle: { color: c.tinta3, align: "left", fontSize: 11.5 }, ...extra,
  };
}
// Relleno degradado bajo una línea, del color dado a transparente.
function areaDegradada(color, opacidad = .16) {
  return {
    opacity: 1,
    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
      { offset: 0, color: echarts.color.modifyAlpha(color, opacidad) },
      { offset: 1, color: echarts.color.modifyAlpha(color, 0) },
    ]),
  };
}
// Barra de zoom inferior con el estilo de la web.
function barraZoom(c, zoom, extra = {}) {
  return [
    { type: "inside", start: zoom.start, end: zoom.end, zoomOnMouseWheel: "ctrl", moveOnMouseWheel: false, moveOnMouseMove: true },
    {
      type: "slider", start: zoom.start, end: zoom.end, height: 28, bottom: 16, borderColor: c.rejilla, fillerColor: echarts.color.modifyAlpha(c.acento, .16),
      backgroundColor: "transparent", handleStyle: { color: c.acento, borderColor: c.acento }, moveHandleStyle: { color: c.acento, opacity: .5 },
      textStyle: { color: c.tinta3, fontSize: 11 }, dataBackground: { lineStyle: { color: c.tinta3, opacity: .6 }, areaStyle: { color: c.rejilla } },
      selectedDataBackground: { lineStyle: { color: c.acento }, areaStyle: { color: echarts.color.modifyAlpha(c.acento, .25) } },
      brushSelect: false, ...extra,
    },
  ];
}
function crearGrafica(elemento, construir) {
  const grafica = echarts.init(elemento, null, { renderer: "canvas" });
  const entrada = { grafica, construir };
  graficas.push(entrada);
  grafica.setOption(construir(), true);
  new ResizeObserver(() => grafica.resize()).observe(elemento);
  return entrada;
}
// Mantiene el zoom de una gráfica cuando se vuelve a dibujar (cambio de tema o de opciones).
function recordarZoom(entrada, zoom) {
  entrada.grafica.on("datazoom", () => {
    const actual = entrada.grafica.getOption().dataZoom?.[0];
    if (actual) { zoom.start = actual.start; zoom.end = actual.end; }
  });
}
function redibujarTodo() {
  for (const { grafica, construir } of graficas) grafica.setOption(construir(), true);
}

function lineaTooltip(color, nombre, valor) {
  return `<div style="display:flex;justify-content:space-between;gap:20px;align-items:center;line-height:1.7">
    <span><i style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};margin-right:7px"></i>${nombre}</span>
    <b style="font-variant-numeric:tabular-nums">${valor}</b></div>`;
}
function cabeceraTooltip(texto, color) {
  return `<div style="color:${color};margin-bottom:5px;font-size:11.5px">${texto}</div>`;
}

// Tarjetas que explican las dos referencias (usadas en Experimentos y Resultados).
function pintarReferencias(contenedor, extra = {}) {
  contenedor.innerHTML = `
    <article class="tarjeta linea" style="--color-linea:var(--ingenuo)">
      <p class="etiqueta">Referencia del enunciado</p>
      <h3>Ingenuo</h3>
      <p class="mutado pequeno">Predice que el precio futuro será igual al <strong>último Brent spot conocido</strong>. Es la
        «regla de no hacer nada»: si una red no la mejora, no aporta nada.</p>
      <p class="mutado pequeno">Matiz importante: a las 09:00 el último spot publicado suele ser de hace
        <strong>unos siete días hábiles</strong>, porque la EIA lo publica con retraso. Repetirlo es repetir un precio de hace una
        semana.${extra.ingenuo || ""}</p>
    </article>
    <article class="tarjeta linea" style="--color-linea:var(--futuros)">
      <p class="etiqueta">Referencia añadida en el estudio</p>
      <h3>Ingenuo con futuros</h3>
      <p class="mutado pequeno">Toma ese último spot conocido y le aplica <strong>lo que ha variado el futuro de Brent</strong>
        desde entonces, que sí se conoce del día anterior. Tampoco predice nada: solo «se pone al día» con el mercado.</p>
      <p class="mutado pequeno">La añadimos al descubrir que buena parte de la mejora de las redes venía de
        esa misma información. Mejorar a esta regla es la prueba de que una red sabe algo más que el mercado.${extra.futuros || ""}</p>
    </article>`;
}

function segmentado(contenedor, opciones, alCambiar, inicial) {
  contenedor.classList.add("segmentado");
  contenedor.setAttribute("role", "group");
  contenedor.innerHTML = opciones.map(([valor, texto]) =>
    `<button type="button" data-valor="${valor}" aria-pressed="${valor === inicial}">${texto}</button>`).join("");
  contenedor.addEventListener("click", (e) => {
    const boton = e.target.closest("button");
    if (!boton || boton.getAttribute("aria-pressed") === "true") return;
    marcarSegmentado(contenedor, boton.dataset.valor);
    alCambiar(boton.dataset.valor);
  });
}
// Marca una opción de un control segmentado sin lanzar su acción.
function marcarSegmentado(contenedor, valor) {
  contenedor.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.valor === String(valor))));
}

document.addEventListener("DOMContentLoaded", montarCabecera);
