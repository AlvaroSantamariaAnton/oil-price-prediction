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

function montarCabecera() {
  const actual = location.pathname.split("/").pop() || "index.html";
  const enlaces = PAGINAS.map(([href, texto]) =>
    `<a href="${href}"${actual === href || (actual === "" && href === "index.html") ? ' aria-current="page"' : ""}>${texto}</a>`).join("");
  document.body.insertAdjacentHTML("afterbegin", `
    <header class="cabecera"><div class="contenedor">
      <a class="marca" href="index.html">${ICONO}<span>Brent a la vista<small>Previsión y estudio con redes recurrentes</small></span></a>
      <button class="boton-menu" aria-label="Abrir menú" aria-expanded="false">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 7h16M4 12h16M4 17h16"/></svg></button>
      <nav class="nav" aria-label="Secciones">${enlaces}
        <button class="boton-tema" aria-label="Cambiar entre tema claro y oscuro" title="Cambiar tema">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg></button>
      </nav>
    </div></header>`);
  document.body.insertAdjacentHTML("beforeend", `
    <footer class="pie"><div class="contenedor">
      <div>Proyecto de predicción del precio del Brent con RNN, LSTM y GRU. Código en
        <a href="${URL_GITHUB}">GitHub</a> · modelo en <a href="${URL_MODELO}">Hugging Face</a>.</div>
      <div>Herramienta educativa. No es una recomendación de inversión.</div>
    </div></footer>`);
  const menu = document.querySelector(".boton-menu");
  const nav = document.querySelector(".nav");
  menu.addEventListener("click", () => {
    const abierto = nav.classList.toggle("abierto");
    menu.setAttribute("aria-expanded", String(abierto));
  });
  document.querySelector(".boton-tema").addEventListener("click", () => {
    const oscuro = getComputedStyle(document.documentElement).colorScheme === "dark";
    const nuevo = oscuro ? "claro" : "oscuro";
    document.documentElement.dataset.tema = nuevo;
    try { localStorage.setItem("tema", nuevo); } catch (e) { /* sin almacenamiento */ }
    redibujarTodo();
  });
}

(function aplicarTemaGuardado() {
  try {
    const tema = localStorage.getItem("tema");
    if (tema) document.documentElement.dataset.tema = tema;
  } catch (e) { /* sin almacenamiento */ }
})();

// ---------- Datos ----------
async function cargarJSON(url) {
  const respuesta = await fetch(url, { cache: "no-cache" });
  if (!respuesta.ok) throw new Error(`No se pudo cargar ${url} (${respuesta.status})`);
  return respuesta.json();
}

// ---------- Formato ----------
const fmt = (v, d = 2) => v == null || Number.isNaN(v) ? "—" : v.toLocaleString("es-ES", { minimumFractionDigits: d, maximumFractionDigits: d });
const fmtSigno = (v, d = 1) => v == null ? "—" : (v > 0 ? "+" : v < 0 ? "−" : "") + fmt(Math.abs(v), d);
const fmtPct = (v, d = 1) => v == null ? "—" : `${fmtSigno(v, d)} %`;
const fmtUSD = (v, d = 2) => `${fmt(v, d)} USD`;
function fmtFecha(iso, opciones = { day: "numeric", month: "long", year: "numeric" }) {
  if (!iso) return "—";
  const [a, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(a, m - 1, d)).toLocaleDateString("es-ES", { ...opciones, timeZone: "UTC" });
}
const fmtFechaCorta = (iso) => fmtFecha(iso, { day: "numeric", month: "short", year: "numeric" });
const claseSigno = (v) => v > 0 ? "sube" : v < 0 ? "baja" : "";

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
    animationDuration: 500,
    grid: { left: 56, right: 24, top: 24, bottom: 48, containLabel: false },
    tooltip: {
      trigger: "axis", backgroundColor: c.superficie, borderColor: c.rejilla, borderWidth: 1,
      textStyle: { color: c.tinta, fontSize: 12 }, extraCssText: "box-shadow:0 8px 24px rgba(0,0,0,.12);border-radius:10px;",
      axisPointer: { type: "line", lineStyle: { color: c.tinta3, width: 1 } },
    },
  };
}
function ejeTiempo(extra = {}) {
  const c = colores();
  return {
    type: "time", axisLine: { lineStyle: { color: c.rejilla } }, axisTick: { show: false },
    axisLabel: { color: c.tinta3, hideOverlap: true }, splitLine: { show: false }, ...extra,
  };
}
function ejeValor(extra = {}) {
  const c = colores();
  return {
    type: "value", scale: true, axisLine: { show: false }, axisTick: { show: false },
    axisLabel: { color: c.tinta3 }, splitLine: { lineStyle: { color: c.rejilla, width: 1 } },
    nameTextStyle: { color: c.tinta3, align: "left" }, ...extra,
  };
}
function crearGrafica(elemento, construir) {
  const grafica = echarts.init(elemento, null, { renderer: "canvas" });
  const entrada = { grafica, construir };
  graficas.push(entrada);
  grafica.setOption(construir(), true);
  new ResizeObserver(() => grafica.resize()).observe(elemento);
  return entrada;
}
function redibujarTodo() {
  for (const { grafica, construir } of graficas) grafica.setOption(construir(), true);
}
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => redibujarTodo());

function lineaTooltip(color, nombre, valor) {
  return `<div style="display:flex;justify-content:space-between;gap:18px;align-items:center">
    <span><i style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};margin-right:6px"></i>${nombre}</span>
    <b style="font-variant-numeric:tabular-nums">${valor}</b></div>`;
}

// Tarjetas que explican las dos referencias (usadas en Experimentos y Resultados).
function pintarReferencias(contenedor, extra = {}) {
  contenedor.innerHTML = `
    <article class="tarjeta" style="border-top:3px solid var(--ingenuo)">
      <p class="etiqueta">Referencia del enunciado</p>
      <h3>Ingenuo</h3>
      <p class="mutado pequeno">Predice que el precio futuro será igual al <strong>último Brent spot conocido</strong>. Es la
        «regla de no hacer nada»: si una red no la mejora, no aporta nada.</p>
      <p class="mutado pequeno" style="margin:0">Matiz importante: a las 09:00 el último spot publicado suele ser de hace
        <strong>unos siete días hábiles</strong>, porque la EIA lo publica con retraso. Repetirlo es repetir un precio de hace una
        semana.${extra.ingenuo || ""}</p>
    </article>
    <article class="tarjeta" style="border-top:3px solid var(--futuros)">
      <p class="etiqueta">Referencia añadida en el estudio</p>
      <h3>Ingenuo con futuros</h3>
      <p class="mutado pequeno">Toma ese último spot conocido y le aplica <strong>lo que ha variado el futuro de Brent</strong>
        desde entonces, que sí se conoce del día anterior. Tampoco predice nada: solo «se pone al día» con el mercado.</p>
      <p class="mutado pequeno" style="margin:0">La añadimos al descubrir que buena parte de la mejora de las redes venía de
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
    if (!boton) return;
    contenedor.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b === boton)));
    alCambiar(boton.dataset.valor);
  });
}

document.addEventListener("DOMContentLoaded", montarCabecera);
