# Protocolo de comparación de RNN, LSTM y GRU

**Pregunta.** A las 09:00 de Madrid, ¿cuánto mejora cada red la predicción del precio spot del Brent frente a repetir el último precio conocido, a 5, 63 y 252 fechas del calendario del Brent?

Diseño acordado el 07/11/2026. El corte de datos es el 04/11/2026 y el paquete fijo es `20261106T142300_705279Z_all`. La [auditoría](../notebooks/01_auditoria_datos.ipynb) documenta las fuentes. El experimento principal reconstruye de forma aproximada qué se habría conocido desde 2000. Se conservan las limitaciones por revisiones posteriores del snapshot y los supuestos de publicación.

## Qué recibe y qué predice cada red

Cada muestra contiene **60 fechas consecutivas** del índice del Brent spot y termina en la mañana de la predicción. Cada fila contiene únicamente entradas admisibles en esa mañana histórica. Para cada horizonte se predice directamente el precio spot observado en USD/barril en la fecha exacta, contando desde la posición siguiente al origen. Una fecha sin cotización cuenta como posición. Si falta el objetivo, esa muestra se excluye solo de ese horizonte.

| Entrada | Disponibilidad en la reconstrucción principal a las 09:00 |
|---|---|
| Brent y WTI spot, gas natural, tipos USD/EUR y CNY/USD | Última observación con edad entre 7 y 10 días de lunes a viernes, ambos inclusive. |
| VIX | Última observación con edad entre 2 y 5 días inclusive. |
| Tipo de depósito BCE | Tipo vigente al cierre del día natural anterior. Se conserva hasta el siguiente cambio. |
| Yahoo: futuros Brent/WTI (OHLC y volumen), cierres de cobre, oro e índice dólar | Fila disponible por supuesto desde la jornada siguiente. Precio admisible hasta edad 5. El volumen ausente queda sin rellenar. |
| Cesta OPEP | Edad entre 2 y 5 días inclusive. Conservar como ausentes las fechas anteriores al comienzo del XML en 2003. |

La edad se mide desde la observación en días de lunes a viernes. Cada entrada lleva valor escalado e indicador de disponibilidad. Para una ausencia se usa el par (0, 0) después del escalado. Se registra procedencia, edad y motivo de ausencia. El escalador aprende exclusivamente de los valores admisibles de la parte de aprendizaje de cada corte. Los intervalos ALFRED de la auditoría sirven de contraste para los supuestos.

## Cómo se entrena y se compara

El horizonte fija **qué precio** se quiere predecir. Si el objetivo cae en la fecha T, se toma el Brent observado en T. Para reconstruir cuándo se podía entrenar o seleccionar con ese ejemplo, se considera conocido a las 09:00 del séptimo día de lunes a viernes posterior a T. Una etiqueta ya publicada sigue siendo válida para entrenar aunque tenga más de diez días. La caducidad de diez días corresponde al Brent utilizado como entrada.

| Etapa | Regla |
|---|---|
| Entrenamiento inicial | Histórico desde 2000 hasta 2017, sujeto a disponer de ventana y objetivo conocidos en el momento de ajuste. |
| Validación temporal | Cuatro cortes con entrenamiento creciente y años de predicción 2018, 2019, 2020 y 2021. En 2022 se conocen los últimos objetivos a 252 días de 2021. |
| Control temporal | En cada frontera, la etiqueta de entrenamiento solo se admite cuando el precio objetivo ya se habría publicado según el retraso acordado para Brent. El horizonte cuenta hasta la fecha del precio; el retraso determina cuándo podemos usarlo para aprender. |
| Parada temprana | Último 15 % cronológico de los orígenes elegibles de cada corte y horizonte como tramo interno. Solo entrenar con etiquetas disponibles antes de empezar ese tramo. Máximo 100 épocas, paciencia de 10 y recuperación de los pesos con menor MAE interno. |
| Presupuesto | Una capa recurrente de 32 o 64 unidades. Tres arquitecturas × tres horizontes × dos tamaños × cuatro cortes = **72 ajustes de validación** con semilla inicial común. Registrar parámetros y tiempo de entrenamiento. |
| Referencia ingenua | Repite el último Brent admisible en el origen. Dentro de cada horizonte, calcular todos los errores en las mismas fechas con referencia y objetivo observables. |

Para cada corte y horizonte se calcula la **mejora porcentual** como `100 × (1 − MAE_red / MAE_ingenuo)`. Para cada arquitectura y horizonte se conserva el tamaño con mayor mejora media en los cuatro cortes. El empate exacto favorece 32 unidades. Para seleccionar la arquitectura de la aplicación se promedian con igual peso los doce porcentajes de los tamaños seleccionados (cuatro años × tres horizontes). Entre las arquitecturas cuya puntuación quede a un punto porcentual o menos de la mejor, se elige la de menor tiempo total de entrenamiento en validación, medido sobre sus 24 ajustes en condiciones comparables. Se explicará también la estabilidad por año y horizonte. La aplicación empleará un modelo de esa arquitectura por horizonte.

## Evaluación final e incertidumbre

En cada ajuste, incluidos los nueve finales, se aplica la misma parada temprana. Primero se seleccionan los orígenes anteriores al ajuste con etiqueta ya disponible. Se reserva el último 15 % de esos orígenes para medir el MAE interno. Entre los orígenes restantes, solo se usan para ajustar pesos y escaladores aquellos cuya etiqueta ya se conocía al inicio del tramo interno. El modelo que predice conserva los pesos de su mejor época.

Antes del primer origen de test, **02/01/2023 a las 09:00**, se fijan configuraciones y márgenes. Para cada red y horizonte, el margen es el percentil 80 de los errores absolutos de sus predicciones de validación con el tamaño seleccionado y etiqueta ya conocida. El intervalo se expresa como precio previsto ± margen, en USD/barril.

Se hacen **9 ajustes finales**, uno por arquitectura y horizonte, usando los ejemplos disponibles al inicio del test (incluidos los de 2022 que sean elegibles). Los pesos y los escaladores permanecen fijos durante la evaluación. Cada mañana avanza la ventana de entradas. El último origen evaluable depende de que exista precio objetivo en el paquete fijo para ese horizonte.

La tabla final presentará por arquitectura y horizonte el número de orígenes evaluados, MSE, MAE, RMSE, mejora frente al ingenuo, parámetros y tiempo de entrenamiento. Para los intervalos se informará de su cobertura observada y su anchura. El 80 % es el nivel nominal. Los resultados de test se reservan para comunicar el desempeño de las decisiones ya fijadas.

**Pendiente antes del primer entrenamiento.** Concretar la transformación de escala, la función de pérdida, el optimizador y su tasa de aprendizaje, el tamaño de lote y el valor de la semilla común. Registrar la biblioteca, el dispositivo y sus versiones. Los entrenamientos y sus métricas todavía están pendientes.

**Al interpretar los resultados.** Los retrasos se eligieron tras auditar fechas de publicación del paquete completo, incluidas fechas posteriores a 2022. La evaluación es retrospectiva: se reservan los errores de predicción del test para el informe final, pero el diseño ya utilizó información sobre el calendario de publicación de ese periodo. Además, los mismos cortes de validación sirven para elegir tamaños y estimar los márgenes. La cobertura en test es la comprobación externa del intervalo nominal.
