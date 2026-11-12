# Brentcast · Previsión del Brent con redes recurrentes

Proyecto académico que compara **RNN, LSTM y GRU** para predecir el precio spot del petróleo Brent a
**una semana, tres meses y un año** (5, 63 y 252 fechas del calendario del Brent), y una aplicación que
publica cada mañana una previsión con el modelo seleccionado.

- **Web:** <https://brentcast.vercel.app> (previsión del día, histórico, datos y método, experimentos y resultados).
- **Modelo:** [`AvaroSantamaria/brent-rnn`](https://huggingface.co/AvaroSantamaria/brent-rnn) en Hugging Face (ONNX, escaladores y configuración).
- **Previsiones:** [`AvaroSantamaria/brent-predicciones`](https://huggingface.co/datasets/AvaroSantamaria/brent-predicciones) (previsión vigente e historial diario).

> **No es una recomendación de inversión.** Es un trabajo educativo; el precio del petróleo depende de
> decisiones políticas, conflictos y acontecimientos que ningún modelo basado en datos pasados anticipa.

## Índice

1. [Resultado en una frase](#resultado-en-una-frase)
2. [Estructura del repositorio](#estructura-del-repositorio)
3. [Datos](#datos)
4. [Método y decisiones principales](#método-y-decisiones-principales)
5. [Experimentos: qué se publica y qué no](#experimentos-qué-se-publica-y-qué-no)
6. [Resultados del test](#resultados-del-test)
7. [Reproducir el proyecto en otro ordenador](#reproducir-el-proyecto-en-otro-ordenador)
8. [La aplicación](#la-aplicación)
9. [Reentrenamiento del modelo de la aplicación](#reentrenamiento-del-modelo-de-la-aplicación)
10. [Limitaciones](#limitaciones)
11. [Posibles mejoras](#posibles-mejoras)

## Resultado en una frase

Con datos reconstruidos tal como se conocían a las 09:00 de Madrid, **las redes mejoran claramente a repetir
el último precio spot conocido a una semana, pero esa mejora procede de actualizar ese precio con los futuros
de Brent**: una regla simple que solo hace eso (el *ingenuo con futuros*) obtiene el mismo resultado o algo
mejor. A tres meses y a un año ninguna red mejora de forma fiable a las referencias.

## Estructura del repositorio

Solo lo que está en GitHub. Los datos descargados, los datos preparados, los experimentos descartados y las
salidas regenerables se quedan en local (ver [`.gitignore`](.gitignore)).

```text
oil-price-prediction/
├── README.md
├── pyproject.toml, poetry.lock         # Entorno (Poetry; PyTorch 2.11 con CUDA 12.8)
├── .gitattributes, .gitignore
├── .github/workflows/
│   ├── prevision-diaria.yml            # Previsión de cada mañana laborable (GitHub Actions)
│   └── recordatorio-reentreno.yml      # Issue trimestral recordando reentrenar (no reentrena)
├── configs/
│   └── config.json                     # Plantilla vacía; se rellena al lanzar un experimento de validación
├── data/
│   ├── petroleo_dataset.csv            # CSV inicial de la asignatura (no se usa en el estudio; ver «Datos»)
│   ├── raw/.gitkeep                    # Aquí van las descargas (ignoradas)
│   └── processed/.gitkeep              # Aquí van los datos preparados (ignorados)
├── docs/
│   ├── assignment/ENUNCIADO.pdf        # Enunciado del trabajo
│   └── protocolo_experimento.md        # Protocolo completo: reglas, experimentos, selección y test
├── notebooks/
│   └── 01_auditoria_datos.ipynb        # Auditoría de fuentes, huecos y fechas de publicación
├── scripts/                            # Descarga, preparación, evaluación, exportación y publicación
│   ├── download_data.py                # Original de la asignatura (genera el CSV inicial; no se modifica)
│   ├── download_raw_data.py            # Series de FRED y Yahoo sin rellenar
│   ├── download_alfred_data.py         # Versiones históricas de FRED (ALFRED) para la auditoría
│   ├── download_all_data.py            # Paquete completo: FRED/Yahoo + ALFRED + OPEP + BCE
│   ├── prepare_daily_inputs.py         # Tabla diaria a las 09:00 con reglas de disponibilidad
│   ├── prepare_windows.py              # Ventanas de 60 fechas y objetivos a +5/+63/+252
│   ├── prepare_splits.py               # Particiones de validación (2018–2021) y del ajuste final (2023)
│   ├── prepare_scalers.py              # Escaladores ajustados solo con el tramo de aprendizaje
│   ├── evaluate_naive.py               # Referencia ingenua en validación
│   ├── evaluate_seed_ensemble.py       # Promedio de semillas y selección entre familias
│   ├── evaluate_validation_uncertainty.py  # Bootstrap por bloques y Diebold-Mariano (E1–E2)
│   ├── compute_interval_margins.py     # Márgenes del intervalo al 80 %
│   ├── plot_validation.py              # Figuras de validación
│   ├── evaluate_test.py                # Evaluación única del test
│   ├── export_onnx.py                  # Exporta la RNN seleccionada a ONNX
│   ├── publicar_hf.py                  # Publica el modelo en Hugging Face
│   └── datos_web.py                    # Genera web/datos/estudio.json
├── src/oil_price_prediction/
│   ├── train_validation.py             # Un ajuste de validación (arquitectura, unidades, horizonte, corte)
│   ├── train_final.py                  # Un ajuste final (arquitectura, horizonte, semilla)
│   ├── referencias.py                  # Ingenuo con futuros
│   ├── actualizar.py                   # Previsión diaria con ONNX (sin PyTorch)
│   └── reentrenar.py                   # Reentrenamiento de la aplicación con datos hasta hoy
├── reports/
│   ├── evaluacion_test.csv             # Tabla completa del test
│   ├── margenes_validacion.json        # Márgenes del intervalo fijados antes del test
│   ├── experimentos/
│   │   ├── E14/, E15/, E16/            # Familia seleccionada: config.json + 72 ajustes cada uno
│   │   └── final/                      # config.json + 27 ajustes finales (3 arquitecturas × 3 horizontes × 3 semillas)
│   └── figuras/E14-E16/
│       ├── validacion/                 # Seis figuras de la validación 2018–2021
│       └── test/                       # Las mismas seis figuras en el test
└── web/                                # Web estática (Vercel): HTML, CSS, JS y datos/estudio.json
```

Cada ajuste publicado (en `E14/validacion/`, `E15/validacion/`, `E16/validacion/` y `final/`) tiene una
carpeta `<instante>_<arquitectura>_h<horizonte>_u<unidades>_<corte|semilla>` con:

| Archivo | Contenido |
|---|---|
| `registro.json` | Configuración efectiva, tramos de fechas, épocas, tiempo, versiones, commit y sha256 del script y del protocolo |
| `modelo.pt` | Pesos de la mejor época (unos 16 KB) |
| `escalador.json` | Medias, desviaciones y orden de las 42 entradas |
| `predicciones.csv` / `predicciones_test.csv` | Predicciones de validación o de test junto a las dos referencias |
| `epocas.csv`, `curvas.png` | MAE de aprendizaje y de parada temprana por época |

## Datos

### Fuentes

Se usan **21 variables**, descargadas de su origen en un paquete fijo del **6 de noviembre de 2026** con corte el
**4 de noviembre de 2026** (`20261106T142300_705279Z_all`):

| Variable | Fuente | Primer uso (días hábiles) | Caducidad |
|---|---|---|---|
| **Brent spot** (objetivo y entrada), WTI spot, gas natural Henry Hub | EIA vía FRED | 7 | 10 |
| Dólares por euro, yuanes por dólar | Reserva Federal vía FRED | 7 | 10 |
| VIX | CBOE vía FRED | 2 | 5 |
| Tipo de depósito del BCE | Tabla oficial del BCE | día siguiente | vigente hasta el siguiente cambio |
| Futuros de Brent y WTI: apertura, máximo, mínimo y cierre | Yahoo Finance (`BZ=F`, `CL=F`) | 1 | 5 |
| Volumen de los futuros | Yahoo Finance | 1 | 1 (sin relleno) |
| Cobre, oro, índice dólar | Yahoo Finance (`HG=F`, `GC=F`, `DX-Y.NYB`) | 1 | 5 |
| Cesta de referencia de la OPEP | XML de la OPEP (desde 2003) | 2 | 5 |

«Primer uso» es la antigüedad mínima para considerar un dato conocido a las 09:00 de Madrid y «caducidad», la
máxima: si el último dato es más viejo, la variable se marca como ausente. El futuro de Brent existe desde julio
de 2007; antes, la variable está ausente.

### Por qué no se usa el CSV inicial

`data/petroleo_dataset.csv` (generado por el script original `scripts/download_data.py`) une las fuentes por
fecha y **rellena hacia delante** los huecos. Eso tiene dos problemas para un estudio honesto:

1. **Mezcla el futuro con el presente.** En la fila de un día aparece el Brent spot de ese mismo día, que no se
   publica hasta días después. Con ALFRED (el archivo de versiones de FRED) se midió que el Brent tarda una
   mediana de 5 días hábiles en publicarse y 7 en el 95 % de los casos.
2. **Oculta la ausencia.** Un dato antiguo rellenado parece de hoy y se pierde la diferencia entre «no hubo
   mercado» y «no hay dato».

**Decisión:** descargar de nuevo cada fuente, congelar una copia fija y reconstruir, fecha a fecha, lo que se
habría conocido a las 09:00 de Madrid. Es más trabajo y hace el problema más difícil, pero evita usar
información futura. El CSV se conserva como referencia y la auditoría lo compara con el paquete.

### Qué ve la red y qué predice

- **Calendario:** las 7.001 fechas del índice del Brent de FRED entre enero de 2000 y noviembre de 2026 (unas
  500 sin precio). Los horizontes cuentan posiciones de este calendario.
- **Ventana:** 60 fechas consecutivas × 42 entradas (las 21 variables, cada una con su valor escalado y su
  indicador de disponibilidad). Un dato ausente se representa como (0, 0).
- **Objetivo:** el Brent spot exacto 5, 63 o 252 posiciones después. Si ese día no hay precio, la muestra se
  descarta solo para ese horizonte.
- **Etiqueta utilizable:** el precio objetivo solo se usa para entrenar cuando ya se habría publicado, siete días
  hábiles después de su fecha.

La [auditoría](notebooks/01_auditoria_datos.ipynb) documenta inventario, huecos, extremos y fechas de
publicación (ALFRED), que justifican estas reglas.

## Método y decisiones principales

El protocolo completo, con cada regla fijada antes de entrenar y cada resultado, está en
[`docs/protocolo_experimento.md`](docs/protocolo_experimento.md). Resumen de las decisiones y su motivo:

| Decisión | Por qué |
|---|---|
| **Validación temporal con cuatro cortes** (predecir 2018, 2019, 2020 y 2021 con todo lo anterior) | Un solo año podría engañar; cuatro años distintos, con la pandemia en medio, dan una idea más estable. 2022 queda libre para que maduren las etiquetas a un año de 2021. |
| **Test desde el 02/01/2023, evaluado una sola vez** | Comprobación independiente de decisiones ya cerradas (configuración, tamaños y márgenes). |
| **Purga por etiquetas no publicadas** | En cada frontera solo se entrena con objetivos que ya se habrían publicado. |
| **Parada temprana con el último 15 % cronológico** (máximo 100 épocas, paciencia 10, pesos de la mejor época) | Elegir el número de épocas sin tocar validación ni test. |
| **Escalado con el tramo de aprendizaje** de cada corte y horizonte | Evitar que las estadísticas incluyan información posterior. |
| **Objetivo: cambio de precio** respecto a una base (desde E2) | Predecir el nivel anclaba las redes a un precio (E1). Con salida nula, la red reproduce la referencia. |
| **Entradas de precio en variación logarítmica diaria** (desde E11) | Un nivel de 70 USD no significa lo mismo en 2005 que en 2018; las variaciones son comparables entre épocas. |
| **Tasa 0,001 a +5 y 0,0001 a +63 y +252** (desde E8) | Con 0,001 la mejor época a horizontes largos solía ser la primera. |
| **Dos referencias: ingenuo e ingenuo con futuros** | Por las reglas de publicación, el spot conocido cada mañana tiene unos 7 días hábiles de antigüedad y el futuro de Brent, 1. El *ingenuo con futuros* (spot × futuro actual / futuro en la fecha del spot) separa lo que aporta la red de lo que aporta ponerse al día. |
| **Base con futuros** (E14–E16): la red predice el cambio desde el ingenuo con futuros | Medir si la red aporta algo más allá de esa actualización. |
| **Tres semillas (42, 43, 44) y promedio de sus predicciones** | La variación entre semillas era del mismo orden que las diferencias entre arquitecturas. |
| **Selección:** tamaño (32 o 64 unidades) por mejora media; arquitectura por la media de 12 porcentajes (4 años × 3 horizontes); a un punto o menos, la de menor tiempo de entrenamiento | Regla fijada antes de ver los resultados. |
| **Intervalo al 80 %:** previsión ± percentil 80 del error absoluto en validación (±4,10 / ±15,99 / ±39,94 USD para la RNN) | Calibrado sin mirar el test; un margen proporcional al precio no mejoró la cobertura. |
| **Pérdida MAE en USD/barril, Adam, lotes de 32, una capa recurrente** | Igual para las tres arquitecturas, para compararlas en las mismas condiciones. |

**Modelo seleccionado:** RNN de una capa con 32 unidades en los tres horizontes, objetivo de cambio desde el
ingenuo con futuros, entradas en variaciones y media de tres semillas. Las tres arquitecturas de la familia
quedaron a menos de un punto, así que decidió el tiempo de entrenamiento.

## Experimentos: qué se publica y qué no

Se hicieron **16 experimentos de validación (1.080 ajustes)**. Cada uno cambió una sola cosa a partir de un
problema observado y con la regla fijada antes de entrenar:

| Experimentos | Qué cambia | Puntuación media en validación frente al ingenuo |
|---|---|---|
| E1 | Objetivo: precio | RNN −16,8 %, GRU −22,2 %, LSTM −53,1 % (las redes se anclan a un nivel) |
| E2–E4 | Objetivo: cambio desde el spot (semillas 42/43/44) | LSTM −1,5 %, GRU −1,8 %, RNN −4,5 % |
| E5–E7 | Objetivo: cambio en porcentaje | Peor que el cambio en USD; descartado |
| E8–E10 | Tasa 0,0001 a +63 y +252 | GRU +4,6 %, LSTM +3,2 %, RNN +1,3 % |
| E11–E13 | Entradas de precio en variaciones | LSTM +6,5 %, GRU +6,4 %, RNN +5,3 % |
| **E14–E16** | **Cambio medido desde el ingenuo con futuros** | **GRU +8,5 %, RNN +8,5 %, LSTM +7,9 %** |

El ingenuo con futuros obtiene por sí solo **+10,2 %** con la misma regla; frente a él, toda la familia
E14–E16 queda por debajo (RNN −1,9 %, GRU −1,9 %, LSTM −2,5 %).

**Qué está en GitHub:**

- **E14, E15 y E16** (la familia seleccionada, 216 ajustes) y los **27 ajustes finales** de `final/`, con sus
  pesos, predicciones y registros. Son la evidencia de la selección y del test.
- **Las figuras de E14–E16** (validación y test) en `reports/figuras/E14-E16/`.
- La tabla del test y los márgenes del intervalo.

**Qué no está (ignorado por Git):** las carpetas de E1–E13 y sus figuras. Se conservan en local; sus resultados
están en el protocolo y en la web (`web/datos/estudio.json`), y cada `registro.json` guarda el commit con el que
se ejecutó. Tampoco se publican los datos (`data/raw/`, `data/processed/`) ni `dist/` (exportaciones y
reentrenamientos locales).

## Resultados del test

Orígenes del 02/01/2023 en adelante; media de tres semillas; mejora del MAE en porcentaje
(`100 × (1 − MAE_modelo / MAE_referencia)`). Tabla completa en
[`reports/evaluacion_test.csv`](reports/evaluacion_test.csv) y figuras en
[`reports/figuras/E14-E16/test/`](reports/figuras/E14-E16/test/).

| Horizonte | Orígenes | Ingenuo con futuros frente al ingenuo | RNN frente al ingenuo | RNN frente al ingenuo con futuros | Cobertura del intervalo 80 % (RNN) |
|---|---|---|---|---|---|
| +5 | 967 | +20,5 % (p < 0,001) | +18,9 % | −2,0 % (IC95 [−3,9; −0,3]) | 64 % |
| +63 | 909 | +2,2 % (p 0,16) | −2,2 % | −4,5 % | 78 % |
| +252 | 726 | +0,1 % | −7,6 % | −7,7 % | 86 % |

- A una semana, redes e ingenuo con futuros aciertan la dirección en torno al 70 % de las veces; la RNN queda
  ligeramente por debajo del ingenuo con futuros, con una diferencia significativa.
- A tres meses ninguna red mejora a ninguna referencia.
- A un año solo la LSTM mejora a ambas (+7,3 %), pero no era la seleccionada, no lo hacía en validación y tres
  años de test equivalen a unas tres observaciones independientes. **No se cambió la selección a la vista del test.**
- Los intervalos de anchura fija se quedan cortos en los periodos más volátiles (por ejemplo, cobertura del
  34 % a +5 en 2026).

## Reproducir el proyecto en otro ordenador

Los comandos son para **PowerShell** (Windows), desde la raíz del repositorio. En Linux o macOS son iguales salvo
la sintaxis de variables de entorno (`export FRED_API_KEY=...`) y de los bucles (`for ... do ... done`).

### 1. Requisitos

- **Python 3.12–3.14** (se usó 3.13) y [**Poetry**](https://python-poetry.org/).
- **GPU NVIDIA con CUDA 12.8** para entrenar: `pyproject.toml` instala PyTorch `2.11.0+cu128` y los scripts de
  entrenamiento exigen CUDA (se usó una RTX 3060 Ti). La preparación de datos, las evaluaciones y la previsión
  con ONNX funcionan en CPU.
- Una **clave gratuita de la API de FRED** (<https://fred.stlouisfed.org/docs/api/api_key.html>) para descargar el
  paquete completo, que incluye las versiones históricas de ALFRED.

### 2. Instalación

```powershell
git clone https://github.com/AlvaroSantamariaAnton/oil-price-prediction.git
cd oil-price-prediction
poetry install
```

### 3. Datos originales (`data/raw/`)

El paquete original **no está en GitHub** (datos de terceros y reproducibles desde su origen). Hay que volver a
descargarlo con el mismo corte:

```powershell
$env:FRED_API_KEY = "tu_clave"
poetry run python -m scripts.download_all_data --start 2000-01-01 --end 2026-11-04 --alfred-end 2026-11-03
```

Crea `data/raw/<instante_UTC>_all/` con `manifest.json` (fechas, hashes y estado de cada componente), la
subcarpeta de series FRED y Yahoo sin rellenar, las versiones ALFRED, el XML de la OPEP, la tabla del BCE y una
copia del CSV inicial. Si falla una fuente, el estado queda `incomplete` y hay que repetir la descarga (crea otra
carpeta; no sobrescribe).

El código espera el nombre del paquete del estudio (`SNAPSHOT` en `scripts/prepare_windows.py`, `BUNDLE` en
`scripts/prepare_daily_inputs.py` y el campo `snapshot` de las configuraciones), así que hay que renombrar la
carpeta descargada:

```powershell
Rename-Item data\raw\<instante_UTC>_all 20261106T142300_705279Z_all
```

> **Importante.** Una descarga nueva **no es idéntica** al paquete del 06/11/2026: FRED, Yahoo, la OPEP y el BCE
> pueden revisar o ajustar datos históricos. El flujo funcionará igual, pero las tablas y los resultados pueden
> diferir ligeramente de los publicados. Con el paquete original, el flujo es determinista: se ha comprobado que
> repetirlo reproduce byte a byte los datos preparados y exactamente los pesos y predicciones de los ajustes
> finales (`src/oil_price_prediction/reentrenar.py --reproducir-estudio`).

### 4. Datos preparados (`data/processed/20261106T142300_705279Z_all/`)

Ejecutar en este orden; cada paso lee lo que escribió el anterior:

```powershell
poetry run python -m scripts.prepare_daily_inputs
poetry run python -m scripts.prepare_windows
poetry run python -m scripts.prepare_splits
poetry run python -m scripts.prepare_splits --fase final
poetry run python -m scripts.prepare_scalers --entradas variaciones
poetry run python -m scripts.prepare_scalers --entradas variaciones --fase final
poetry run python -m scripts.evaluate_naive
```

| Paso | Escribe | Qué hace |
|---|---|---|
| `prepare_daily_inputs` | `entradas_diarias.csv` | Para cada fecha del calendario, el último valor admisible de cada variable a las 09:00, con indicador, fecha de origen, edad y estado |
| `prepare_windows` | `ventanas_objetivos.csv` | Ventanas de 60 fechas y objetivos a +5/+63/+252, con la fecha desde la que se conoce cada etiqueta |
| `prepare_splits` | `particiones_validacion.csv` | Aprendizaje, parada temprana y validación para los cortes 2018–2021 |
| `prepare_splits --fase final` | `particiones_final.csv` | Lo mismo con frontera el 02/01/2023 y el test |
| `prepare_scalers --entradas variaciones` | `escalado_validacion_variaciones.zip` | Precios en variaciones y escalado por corte y horizonte |
| `prepare_scalers ... --fase final` | `escalado_final_variaciones.zip` | Escalado del ajuste final |
| `evaluate_naive` | `referencia_ingenua_validacion.zip` | Predicciones y MAE de la referencia ingenua en validación |

Sin `--entradas variaciones`, `prepare_scalers` genera las entradas en niveles que usaron E1–E10.

### 5. Validación de la familia seleccionada (E14–E16)

`train_validation.py` lee `configs/config.json` y guarda cada ajuste en `reports/experimentos/<experimento>/`.
Como el repositorio ya trae E14–E16 y `final/`, **primero hay que apartar esas carpetas** (si no, los ajustes
nuevos se mezclarían con los publicados). Se dejan fuera del repositorio como referencia para comparar:

```powershell
New-Item -ItemType Directory ..\referencia | Out-Null
Move-Item reports\experimentos\E14, reports\experimentos\E15, reports\experimentos\E16, reports\experimentos\final ..\referencia\
```

Cada experimento son 72 ajustes (3 arquitecturas × 2 tamaños × 3 horizontes × 4 cortes) con su semilla:

```powershell
foreach ($e in "E14", "E15", "E16") {
  Copy-Item "..\referencia\$e\config.json" configs\config.json
  foreach ($a in "RNN", "LSTM", "GRU") { foreach ($u in 32, 64) { foreach ($h in 5, 63, 252) { foreach ($c in 2018, 2019, 2020, 2021) {
    poetry run python -m src.oil_price_prediction.train_validation --arquitectura $a --unidades $u --horizonte $h --corte $c
  } } } }
}
git restore configs/config.json
```

Según los tiempos registrados, el entrenamiento de los 216 ajustes suma unos 20 minutos en la GPU usada, a los
que se añade el arranque de cada proceso.
Después, los márgenes del intervalo y las figuras de validación:

```powershell
poetry run python -m scripts.compute_interval_margins
poetry run python -m scripts.plot_validation --familia futuros
```

### 6. Ajustes finales y test

```powershell
New-Item -ItemType Directory reports\experimentos\final -Force | Out-Null
Copy-Item ..\referencia\final\config.json reports\experimentos\final\
foreach ($a in "RNN", "LSTM", "GRU") { foreach ($h in 5, 63, 252) { foreach ($s in 42, 43, 44) {
  poetry run python -m src.oil_price_prediction.train_final --arquitectura $a --horizonte $h --semilla $s
} } }
poetry run python -m scripts.evaluate_test
```

`train_final.py` comprueba que su configuración coincide con E14–E16, no calcula ninguna métrica de test y se
niega a repetir un ajuste que ya existe. `evaluate_test.py` escribe `reports/evaluacion_test.csv` y las figuras
de `reports/figuras/E14-E16/test/`; en el estudio se ejecutó una sola vez, al final.

Para comparar con lo publicado, basta con confrontar las carpetas nuevas con las de `..\referencia\` (por
ejemplo, `predicciones_test.csv`) o restaurar las versionadas con `git restore reports`.

### 7. Lo que no se puede regenerar solo con el clon

- **La selección entre familias** (`scripts/evaluate_seed_ensemble.py`), la incertidumbre de E1–E2
  (`scripts/evaluate_validation_uncertainty.py`) y **los datos de la web** (`scripts/datos_web.py`) necesitan
  las carpetas de E1–E13, que no se publican. Sus configuraciones y resultados están descritos en el protocolo;
  para regenerarlos habría que crear cada `config.json` siguiendo esas descripciones.
- **La auditoría** (`notebooks/01_auditoria_datos.ipynb`) necesita el paquete completo; su ruta se indica en la
  primera celda. Requiere el grupo de desarrollo (`matplotlib` e `ipykernel`, incluidos en `poetry install`).

## La aplicación

### Cómo funciona

1. **Cada mañana laborable a las 09:15 de Madrid**, GitHub Actions
   ([`prevision-diaria.yml`](.github/workflows/prevision-diaria.yml)) descarga los datos en vivo, construye la
   tabla con las mismas reglas de disponibilidad, descarga el modelo de Hugging Face, predice con
   **onnxruntime** (sin PyTorch) y sube `prediccion.json` y una copia en `historial/` al repositorio de datos.
2. **La web** (carpeta `web/`, desplegada en Vercel con Root Directory `web`) es estática: lee esa previsión
   de Hugging Face y los datos del estudio de `web/datos/estudio.json`.

La previsión es **base + media del cambio previsto por las tres semillas**, donde la base es el ingenuo con
futuros, con el intervalo del 80 % calibrado en validación. Desde la nube, la web de la OPEP rechaza las
descargas: la cesta se trata como dato ausente y la web lo avisa (en el test, eso cambió la previsión de media
entre 0,13 y 0,27 USD). Si falla la tabla del BCE, se usa el mismo tipo publicado en FRED.

### Ejecutarla en local

```powershell
poetry run python -m src.oil_price_prediction.actualizar --repo-modelo AvaroSantamaria/brent-rnn
```

Escribe `dist/huggingface/datos/prediccion.json`. Opciones: `--origen AAAA-MM-DD` (otra fecha), `--modelo
<carpeta>` (modelo local, por ejemplo el exportado con `scripts/export_onnx.py`) y `--paquete` (usa el paquete
del estudio en lugar de descargar). Publicar en Hugging Face (`--repo-datos`) requiere un token con permiso de
escritura (`hf auth login` o la variable `HF_TOKEN`); el flujo de GitHub lo toma del secreto `HF_TOKEN`.

Para ver la web en local:

```powershell
python -m http.server 8770 --directory web
```

y abrir <http://localhost:8770>. Abrir los HTML directamente desde el disco no funciona (el navegador bloquea la
carga de datos). La página «Hoy» muestra siempre la previsión publicada en Hugging Face. Si esa previsión se
calculó antes de las 09:00 de Madrid (por ejemplo, en una ejecución manual de madrugada), la página lo avisa e
indica la hora real de los datos.

### Del estudio al modelo publicado

```powershell
poetry run python -m scripts.export_onnx
poetry run python -m scripts.publicar_hf --repo <usuario>/brent-rnn
```

`export_onnx.py` exporta las nueve RNN finales a `dist/huggingface/modelo/` con sus escaladores y un
`config.json` (versión, márgenes, tramos de entrenamiento y evaluación del test). Se comprobó en todo el test
que ONNX coincide con PyTorch (diferencia máxima 3,8·10⁻⁶) y que la previsión de precio coincide con
`predicciones_test.csv` (diferencia máxima 4,8·10⁻⁵ USD). `publicar_hf.py` escribe la ficha del modelo y lo
sube; cada versión queda etiquetada en el repositorio de Hugging Face (`estudio-2023-01-02`,
`reentreno-2026-11-12`, …).

## Reentrenamiento del modelo de la aplicación

El estudio y su test quedan congelados. Para que la aplicación use datos recientes, se reentrena **con el mismo
método** del ajuste final (`reports/experimentos/final/config.json`: RNN de 32 unidades, objetivo de cambio,
entradas en variaciones, base con futuros, semillas 42/43/44 y parada temprana con el último 15 %) y frontera en
la fecha del reentrenamiento. La versión publicada ahora es **`reentreno-2026-11-12`**.

Se hace **a mano, en local con GPU**: la cesta OPEP es obligatoria para reentrenar (sin ella cambiaría la
entrada en todo el histórico) y su descarga falla desde la nube. Frecuencia recomendada: **cada 3–6 meses, o
tras un acontecimiento importante** en el mercado. El flujo
[`recordatorio-reentreno.yml`](.github/workflows/recordatorio-reentreno.yml) abre una issue el 1 de enero,
abril, julio y octubre con los pasos y la versión publicada; no reentrena y no abre otra si ya hay una abierta.

1. **Si ha cambiado el código** de preparación o entrenamiento, comprobar primero que se reproduce el estudio
   (necesita el paquete original en `data/raw/`):

   ```powershell
   poetry run python -m src.oil_price_prediction.reentrenar --reproducir-estudio
   ```

   Con el paquete y la frontera del 02/01/2023 deben salir idénticos los datos preparados, los pesos y las
   predicciones de test de `reports/experimentos/final/` (la opción `--solo-datos` comprueba solo los datos).

2. **Reentrenar:**

   ```powershell
   poetry run python -m src.oil_price_prediction.reentrenar
   ```

   Descarga los datos en `data/raw/<instante>_reentreno/`, prepara `data/processed/reentreno-AAAA-MM-DD/`,
   entrena los nueve modelos y escribe en `dist/reentrenos/reentreno-AAAA-MM-DD/` los pesos y registros
   (`ajustes/`), el modelo listo para publicar (`modelo/`) e `informe_cordura.json`.

3. **Revisar el informe de cordura:** error en el tramo de parada temprana frente al ingenuo con futuros,
   previsión de hoy del modelo nuevo y del publicado, con y sin la cesta OPEP, y diferencia entre ONNX y
   PyTorch.

4. **Publicar en este orden:** primero el código en GitHub (si ha cambiado), después el modelo y por último
   lanzar a mano la previsión diaria (*Actions → Previsión diaria → Run workflow*):

   ```powershell
   poetry run python -m scripts.publicar_hf --repo AvaroSantamaria/brent-rnn --carpeta dist/reentrenos/reentreno-AAAA-MM-DD/modelo
   ```

**Qué significa un reentreno:**

- **No tiene test propio.** La web y la ficha muestran las métricas del test del estudio como fiabilidad del
  método, no de esos pesos.
- **El error en el tramo de parada temprana no es una evaluación nueva, sino una comprobación de cordura:** ese
  tramo decide la época de cada semilla y se solapa con el periodo de test del estudio.
- **Los datos más recientes solo deciden cuándo parar.** Con el 15 % reservado y el retraso de las etiquetas, el
  aprendizaje termina años antes de la frontera. En `reentreno-2026-11-12`, los orígenes de aprendizaje llegan
  hasta diciembre de 2022 (+5), julio de 2022 (+63) y marzo de 2021 (+252), y 2023–2026 solo se usa para la
  parada temprana. Por eso la web indica, por horizonte, hasta dónde llegan el aprendizaje y la parada temprana.
- Reentrenar no garantiza mejores previsiones.

## Limitaciones

- **Las redes no superan al ingenuo con futuros.** Su ventaja frente al ingenuo del enunciado procede de
  actualizar el último spot con los futuros.
- **Reconstrucción aproximada.** Los retrasos de publicación se fijaron tras auditar fechas de todo el paquete,
  incluido el periodo de test; las series de FRED y Yahoo descargadas en 2026 pueden incluir revisiones
  posteriores; para los futuros de Yahoo se asume que cada cierre se conoce al día siguiente. El futuro continuo
  de Yahoo tiene saltos al cambiar de vencimiento.
- **Selección optimista.** Todas las elecciones se hicieron sobre la misma validación; las cifras de validación
  de la familia seleccionada son optimistas. El test es la comprobación independiente.
- **Horizontes largos con poca información.** A +252, cada año equivale a una observación independiente;
  cuatro años de validación y tres de test no permiten conclusiones firmes.
- **Intervalos de anchura fija** en USD: cubren menos de lo nominal en periodos muy volátiles.
- **El ajuste final no aprende directamente de 2019–2022**, que se usa como tramo de parada temprana; en los
  reentrenamientos ocurre lo mismo con los años más recientes.

## Posibles mejoras

- Web: seguimiento de las previsiones pasadas frente a los precios reales, a partir del historial publicado.
