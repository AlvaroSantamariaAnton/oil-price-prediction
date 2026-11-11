# Experimentos de validación

Cada carpeta `E<n>` es una ejecución con una única configuración, copiada en `E<n>/config.json`. Dentro de `validacion/` hay una carpeta por ajuste: arquitectura, horizonte, unidades y corte. Cada ajuste contiene `registro.json`, `epocas.csv`, `curvas.png`, `predicciones.csv`, `modelo.pt` y `escalador.json`. El protocolo completo está en [`docs/protocolo_experimento.md`](../../docs/protocolo_experimento.md).

Solo se publican **E14, E15 y E16**, la familia seleccionada. El resto se conserva en local y se puede reproducir con su configuración y el commit que figura en cada `registro.json`.

## Familia seleccionada: E14–E16

E14, E15 y E16 usan **la misma configuración con tres semillas distintas** (42, 43 y 44). La predicción de cada arquitectura y horizonte es **la media de las tres**.

- Objetivo: cambio del precio respecto a una base.
- Base: último Brent spot admisible actualizado con el futuro de Brent (ingenuo con futuros).
- Entradas: precios como variación diaria.
- Tasa de aprendizaje: 0,001 a +5 y 0,0001 a +63 y +252.
- Cuadrícula: RNN, LSTM y GRU, con 32 o 64 unidades, en los cortes 2018–2021.

Seleccionada: **RNN con 32 unidades en los tres horizontes**. Figuras en [`reports/figuras/E14-E16/`](../figuras/E14-E16/).

## Todas las ejecuciones

| Experimentos | Qué cambia | Resultado |
|---|---|---|
| E1 | Objetivo: precio | Las redes se anclan a un nivel de precio. El bloque GRU +5 se ejecutó dos veces con resultados idénticos; cuenta una vez. |
| E2–E4 | Objetivo: cambio desde el spot (semillas 42/43/44) | Mejora a E1 y elimina el anclaje. |
| E5–E7 | Objetivo: cambio en porcentaje (semillas 42/43/44) | Peor que el cambio en USD; descartado. |
| E8–E10 | Tasa 0,0001 a +63 y +252 (semillas 42/43/44; +5 de E2–E4) | Mejora los horizontes largos. |
| E11–E13 | Entradas de precio en variaciones (semillas 42/43/44) | Mejora sobre todo +5. |
| E14–E16 | Cambio medido desde el ingenuo con futuros (semillas 42/43/44) | Familia seleccionada. |

Ninguna familia supera de forma consistente al ingenuo con futuros. La mejora de las redes frente al ingenuo del enunciado procede sobre todo de actualizar el último spot conocido con la información más reciente de los futuros.

## Ajustes finales y test

Los ajustes finales, con las tres semillas de cada modelo, se guardarán juntos en `final/`. Las figuras del test irán en `reports/figuras/E14-E16/test/`.
