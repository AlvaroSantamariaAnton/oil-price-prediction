// Página «Experimentos»: familias, recorrido, antes y después y familia seleccionada.
const PASOS = {
  precio: {
    titulo: "Predecir el precio directamente", motivo: "Punto de partida del enunciado.",
    cambio: "Cada red recibe la ventana de 60 días y devuelve el precio del Brent en la fecha objetivo. Una sola semilla.",
    leccion: "Las redes se anclan a un nivel de precio: en varios años devuelven casi el mismo valor todo el tiempo. Ninguna supera al ingenuo.",
  },
  cambio: {
    titulo: "Predecir el cambio y promediar tres semillas", motivo: "Problema: el anclaje a un nivel.",
    cambio: "La red predice cuánto variará el precio desde el último spot conocido. Al ver que el ganador cambiaba con la semilla, cada configuración se entrena con tres semillas y se promedian.",
    leccion: "Desaparece el anclaje y la mejora a una semana pasa a ser estadísticamente sólida, pero en conjunto todavía no se supera al ingenuo.",
  },
  porcentaje: {
    titulo: "Cambio en porcentaje", motivo: "Idea: un movimiento de 5 dólares no significa lo mismo con el barril a 20 que a 100.",
    cambio: "La red predice la variación porcentual en lugar de la variación en dólares.",
    leccion: "Peor en las tres redes. Se descarta según la regla fijada de antemano.", descartado: true,
  },
  cambio_tasa_menor: {
    titulo: "Pasos más pequeños en los horizontes largos", motivo: "Problema: a un año, la mejor época solía ser la primera.",
    cambio: "Tasa de aprendizaje diez veces menor (0,0001) a tres meses y a un año, para que la parada temprana encuentre un punto mejor.",
    leccion: "Primera vez que las tres redes quedan por encima del ingenuo en la media de la validación.",
  },
  variaciones: {
    titulo: "Entradas en variaciones", motivo: "Problema: los niveles de precio no son comparables entre épocas.",
    cambio: "Las 17 variables de precio entran como variación diaria en lugar de como nivel.",
    leccion: "Gran salto a una semana. Pero un acierto direccional del 73 % levantó la sospecha: buena parte venía de los futuros.",
  },
  futuros: {
    titulo: "Medir el cambio desde el precio actualizado con futuros", motivo: "Descubrimiento: una regla simple con futuros superaba a todas las redes.",
    cambio: "La base pasa a ser el último spot actualizado con el futuro de Brent. La red solo tiene que aportar lo que los futuros no saben.",
    leccion: "Mejor puntuación de todo el estudio, pero ninguna red supera a la regla simple con futuros. Familia seleccionada.", elegido: true,
  },
};

document.addEventListener("DOMContentLoaded", async () => {
  const estudio = await cargarJSON(URL_ESTUDIO);
  pintarReferencias(document.getElementById("referencias"), {
    futuros: ` En validación, esta regla por sí sola mejora al ingenuo un ${fmt(estudio.referencia_futuros_validacion.global, 1)} % con la misma puntuación que las redes.`,
  });
  pintarFamilias(estudio);
  pintarRecorrido(estudio);
  pintarAntesDespues(estudio);
  pintarTablaFinal(estudio);
});

function pintarFamilias(e) {
  let referencia = "ingenuo";
  segmentado(document.getElementById("selector-referencia"), [["ingenuo", "Frente al ingenuo"], ["futuros", "Frente al ingenuo con futuros"]], (v) => {
    referencia = v; actualizarTexto(); entrada.grafica.setOption(construir(), true);
  }, referencia);
  const textos = {
    ingenuo: `Cada barra mide cuánto mejora la red al ingenuo (repetir el último spot conocido), que es la línea del 0 %. Las familias mejoran paso a paso hasta superarlo con claridad. Como comparación, el ingenuo con futuros, sin ninguna red, mejora al ingenuo un ${fmt(e.referencia_futuros_validacion.global, 1)} %: lo ves en la otra vista.`,
    futuros: "Ahora la línea del 0 % es el ingenuo con futuros. Ninguna familia la supera: lo mejor que consiguen las redes es quedarse cerca de esa regla sencilla.",
  };
  const actualizarTexto = () => {
    document.getElementById("explicacion-referencia").textContent = textos[referencia];
    const barras = ["RNN", "LSTM", "GRU"].map((a) => `<span><i style="background:${VAR[a]};height:10px"></i>${a}</span>`).join("");
    document.getElementById("leyenda-familias").innerHTML = barras +
      `<span><i style="background:${VAR.tinta3}"></i>${referencia === "ingenuo" ? "Ingenuo" : "Ingenuo con futuros"} (0 %)</span>`;
  };
  actualizarTexto();
  const etiquetas = e.familias.map((f) => f.experimentos.replace("_", " + "));
  const construir = () => {
    const c = colores();
    const campo = referencia === "ingenuo" ? "puntuacion" : "frente_futuros";
    return {
      ...baseOpciones(),
      grid: { left: 52, right: 20, top: 24, bottom: 56 },
      tooltip: {
        ...baseOpciones().tooltip, axisPointer: { type: "shadow", shadowStyle: { color: c.rejilla, opacity: .35 } },
        formatter: (ps) => `<b>${ps[0].axisValue}</b><div style="color:${c.tinta3};margin:2px 0 6px">${PASOS[e.familias[ps[0].dataIndex].id].titulo}</div>` +
          ps.filter((p) => p.seriesType === "bar").map((p) => lineaTooltip(p.color, p.seriesName, fmtPct(p.value))).join(""),
      },
      xAxis: { type: "category", data: etiquetas, axisTick: { show: false }, axisLine: { lineStyle: { color: c.rejilla } }, axisLabel: { color: c.tinta2, fontWeight: 600, interval: 0 } },
      yAxis: ejeValor({ name: "%", scale: false }),
      series: [
        ...["RNN", "LSTM", "GRU"].map((a, i) => ({
          name: a, type: "bar", barGap: "12%", barCategoryGap: "32%", data: e.familias.map((f) => f.arquitecturas[a][campo]),
          itemStyle: { color: c[a], borderRadius: [4, 4, 0, 0] },
          markLine: i > 0 ? undefined : {
            silent: true, symbol: "none",
            data: [{ yAxis: 0, lineStyle: { color: c.tinta3, width: 1, type: "solid" }, label: { show: false } }],
          },
        })),
      ],
    };
  };
  const entrada = crearGrafica(document.getElementById("grafica-familias"), construir);
}

function pintarRecorrido(e) {
  document.getElementById("recorrido").innerHTML = e.familias.map((f) => {
    const paso = PASOS[f.id];
    const mejor = f.arquitecturas[f.principal];
    return `<article class="tarjeta paso ${paso.elegido ? "elegido" : ""} ${paso.descartado ? "descartado" : ""}">
      <div class="codigo">${f.experimentos.replace("_", " + ")}<small>${f.semillas === 1 ? "una semilla" : "tres semillas"}</small></div>
      <div>
        <h3>${paso.titulo}</h3>
        <p><strong>${paso.motivo}</strong> ${paso.cambio}</p>
        <p>${paso.leccion}</p>
      </div>
      <div class="resultado">
        <span class="chip ${paso.elegido ? "acento" : ""}">${paso.elegido ? "Seleccionada · " : paso.descartado ? "Descartada · " : ""}${f.principal}</span>
        <div class="cifra-media num ${claseSigno(mejor.puntuacion)}" style="margin-top:10px">${fmtPct(mejor.puntuacion, 2)}</div>
        <div class="pequeno mutado num">(${fmtPct(mejor.frente_futuros, 2)} con futuros)</div>
      </div>
    </article>`;
  }).join("");
}

function pintarAntesDespues(e) {
  let h = "63";
  const textos = {
    5: "A una semana, el primer experimento ya seguía al precio, pero con retraso y errores grandes; el seleccionado se pega a la referencia actualizada con futuros.",
    63: "A tres meses se ve el anclaje del primer experimento: en 2018 su previsión es una línea casi plana muy por debajo del precio. El seleccionado sigue el nivel del mercado, aunque tampoco anticipa la caída de 2020 ni la subida de 2022.",
    252: "A un año, el primer experimento predice niveles casi fijos; el seleccionado se mueve con el mercado, pero ninguno anticipa la subida de 2022.",
  };
  segmentado(document.getElementById("selector-horizonte"), [["5", "1 semana"], ["63", "3 meses"], ["252", "1 año"]], (v) => {
    h = v; document.getElementById("texto-antes-despues").textContent = textos[h]; entrada.grafica.setOption(construir(), true);
  }, h);
  document.getElementById("texto-antes-despues").textContent = textos[h];
  const c0 = VAR;
  document.getElementById("leyenda-antes").innerHTML = `
    <span><i style="background:${c0.real}"></i>Brent real en la fecha objetivo</span>
    <span><i style="background:${c0.ingenuo}"></i>E1 · ${e.validacion.precio.principal} prediciendo el precio</span>
    <span><i style="background:${c0.RNN}"></i>E14–E16 · ${e.validacion.futuros.principal} seleccionada</span>`;
  const construir = () => {
    const c = colores();
    const a = e.validacion.precio[h], b = e.validacion.futuros[h];
    const pares = (s, campo) => s.objetivo.map((d, i) => [d, s[campo][i]]);
    const porAnio = (s, campo) => {
      const salida = []; let anterior = null;
      s.origen.forEach((o, i) => { const anio = o.slice(0, 4); if (anterior && anio !== anterior) salida.push([s.objetivo[i], null]); salida.push([s.objetivo[i], s[campo][i]]); anterior = anio; });
      return salida;
    };
    return {
      ...baseOpciones(),
      grid: { left: 52, right: 20, top: 24, bottom: 40 },
      tooltip: {
        ...baseOpciones().tooltip,
        formatter: (ps) => `<div style="color:${c.tinta3};margin-bottom:4px">Objetivo: ${fmtFecha(String(ps[0].value[0]).slice(0, 10))}</div>` +
          ps.filter((x) => x.value[1] != null).map((x) => lineaTooltip(x.color, x.seriesName, fmtUSD(x.value[1]))).join(""),
      },
      xAxis: ejeTiempo(),
      yAxis: ejeValor({ name: "USD/barril" }),
      series: [
        { name: "Brent real", type: "line", data: pares(b, "real"), showSymbol: false, lineStyle: { width: 1.6, color: c.real }, itemStyle: { color: c.real }, connectNulls: false },
        { name: "E1 · precio", type: "line", data: porAnio(a, "red"), showSymbol: false, lineStyle: { width: 1.6, color: c.ingenuo }, itemStyle: { color: c.ingenuo } },
        { name: "E14–E16 · seleccionada", type: "line", data: porAnio(b, "red"), showSymbol: false, lineStyle: { width: 1.6, color: c.RNN }, itemStyle: { color: c.RNN } },
      ],
    };
  };
  const entrada = crearGrafica(document.getElementById("grafica-antes"), construir);
}

function pintarTablaFinal(e) {
  const final = e.familias.find((f) => f.id === "futuros");
  const filas = ["RNN", "LSTM", "GRU"].map((a) => {
    const v = final.arquitecturas[a];
    const u = e.horizontes.map((h) => v.horizontes[h].unidades).join(" / ");
    return `<tr class="${a === e.seleccionada ? "destacada" : ""}"><td><span class="marca-serie" style="background:var(--${a.toLowerCase()})"></span>${a}</td>
      <td class="num">${u}</td><td class="num">${fmtPct(v.puntuacion, 2)}</td><td class="num">${fmtPct(v.frente_futuros, 2)}</td><td class="num">${v.pares_positivos}/12</td></tr>`;
  }).join("");
  document.getElementById("tabla-final").outerHTML = `<div class="tabla-envoltura"><table>
    <thead><tr><th>Red</th><th>Unidades</th><th>Frente al ingenuo</th><th>Frente al ingenuo con futuros</th><th>Años y horizontes con mejora</th></tr></thead>
    <tbody>${filas}</tbody></table></div>
    <p class="nota">Unidades a una semana / tres meses / un año. El ingenuo con futuros obtiene +${fmt(e.referencia_futuros_validacion.global, 2)} % frente al ingenuo con la misma regla.</p>`;
}
