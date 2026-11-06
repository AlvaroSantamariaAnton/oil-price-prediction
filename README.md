# oil-price-prediction

Proyecto académico de predicción del Brent mediante RNN, LSTM y GRU.
Auditoría de fuentes completada; siguiente fase: diseño del experimento.
Todavía no hay modelos entrenados ni dataset preparado para entrenamiento.

## Notebook de auditoría

### Descarga unificada

Con `FRED_API_KEY` configurada en la terminal:

```powershell
poetry run python scripts/download_all_data.py --start 2000-01-01 --end 2026-11-04 --alfred-end 2026-11-03
```

Crea una carpeta `data/raw/<UTC>_all/` con un manifiesto global, las 12 fuentes
raw, las siete series ALFRED (incluidos Brent, WTI y gas), XML OPEP, HTML de la
tabla oficial BCE y copia del CSV inicial para comparación. Los subdirectorios
de cada descargador conservan sus manifiestos y hashes. Los archivos simples
tienen hashes en el manifiesto global. Si falta una fuente, sale con código 1
y estado incomplete. No borra ni sobrescribe snapshots anteriores.
OPEP y BCE se consultan mediante curl_cffi, ya instalado con yfinance, con
perfil HTTP de navegador y validación de certificados activa. Los fallos muestran
un diagnóstico saneado. Cada nueva ejecución repite todas las fuentes desde cero.

Pegar el nombre de la carpeta completa en `BUNDLE`, en la primera celda del
notebook, reiniciar el kernel y ejecutar desde el principio. Ya no lee ZIP ni
archivos de Descargas. Las salidas anteriores se han retirado al migrar el
notebook: no representan la nueva descarga. Validar el nuevo paquete y la
ejecución completa antes de decidir eliminar datos antiguos.

Aunque se mantenga el corte, raw/OPEP/BCE pueden contener revisiones actuales;
el XML y la tabla pueden incluir fechas posteriores que deben filtrarse.
No sustituir el dataset de comparación sin revisar esas diferencias.

`notebooks/01_auditoria_datos.ipynb` calcula inventario, integridad de snapshots,
faltantes, gráficos, extremos y cobertura histórica ALFRED/OPEP. Solo lee archivos
locales; no descarga, transforma en disco ni entrena. Configurar las rutas en la
primera celda y ejecutar de arriba abajo con el kernel del entorno Poetry.
Requiere `matplotlib` e `ipykernel` además de las dependencias actuales. Si faltan,
el usuario puede incorporarlas con `poetry add --group dev matplotlib ipykernel`.
El usuario ya incorporó estas dependencias al grupo dev mediante Poetry.
El paquete unificado completo es obligatorio. Su ruta se configura en la celda inicial.
Los archivos locales ignorados no vienen con el clon: se necesitan los originales
conservados, porque repetir descargas puede producir datos revisados.
La referencia de auditoría aprobada es `20261106T142300_705279Z_all`, con corte
04/11/2026; el usuario confirmó ejecución completa del notebook sin errores.
Una descarga nueva no garantiza reproducir exactamente ese snapshot.

## Versiones históricas de ALFRED

Requiere una clave personal de la API de FRED en la variable de entorno
`FRED_API_KEY` de la terminal actual. No guardar la clave en código ni en Git.
Con esa variable configurada, ejecutar desde la raíz:

```powershell
poetry run python scripts/download_alfred_data.py --series VIXCLS --start 2000-01-01 --end 2026-11-03 --vintage-end 2026-11-04
```

`--end` limita las fechas de observación; `--vintage-end` limita las versiones
históricas. Ambos límites son inclusivos. Se solicitan intervalos de vigencia
(`output_type=1`), sin transformar valores ni agregar la frecuencia.
Cada ejecución crea `data/raw/<instante_UTC>_alfred_<serie>/` con páginas JSON
originales y manifiesto de parámetros sin credencial, recuentos y hashes.
Gestiona paginación y reintentos limitados ante fallos transitorios.
Si FRED rechaza el número de versiones, divide automáticamente el periodo
histórico en bloques contiguos sin solapamiento y pagina cada bloque.
El manifiesto registra los límites y recuentos de cada bloque. Los intervalos
devueltos pueden quedar recortados en esos límites; no confundir el inicio de
un bloque con una nueva publicación ni contar sus filas como versiones únicas.
Ante un fallo conserva las páginas válidas, marca `incomplete` y sale con código 1.
Una interrupción puede dejar `in_progress`; para repetir, ejecutar de nuevo
(crea otro snapshot, no reanuda el anterior).
`complete` acredita el recuento de la API, no disponibilidad desde 2000 ni
horas de publicación. No modifica los descargadores anteriores ni sus datos.
Documentación: https://fred.stlouisfed.org/docs/api/fred/series_observations.html .

## Preparación y descarga

Requiere Python >= 3.12 y Poetry. Desde la raíz:

```powershell
poetry install
poetry run python scripts/download_raw_data.py
```

Para solicitar un corte fijo (fechas inclusivas):

```powershell
poetry run python scripts/download_raw_data.py --start 2000-01-01 --end 2026-11-04
```

Cada ejecución crea `data/raw/<instante_UTC>/` con 12 CSV de series FRED/Yahoo
y un `manifest.json` con fechas solicitadas, versiones, filas, faltantes,
hashes y estado por fuente. Conserva fechas y huecos tal como los entregan
pandas/yfinance, sin unir calendarios ni rellenar valores. No son copias HTTP.

Si una fuente falla, conserva las obtenidas, marca `incomplete` y termina con
código 1. Una ejecución interrumpida puede quedar `in_progress`. `complete`
significa éxito de las 12 series configuradas, no validación económica ni
cobertura total. La cesta OPEP todavía no está incorporada.

La fecha final solicitada no garantiza observaciones hasta ese día. La fecha de
observación no identifica su publicación. Los proveedores pueden revisar datos:
repetir el mismo periodo no garantiza un snapshot idéntico.

`data/petroleo_dataset.csv` conserva la descarga inicial del 4/11/2026, rellenada
por el script original. El nuevo script no la modifica. Aún no se ha elegido
un nuevo snapshot para los experimentos.

`data/processed/` está reservado para la preparación posterior. Las reglas de
relleno y la tabla de seguimiento (valor original, relleno, fecha de procedencia)
se implementarán cuando se acuerde el tratamiento por variable.

Los snapshots locales y datos derivados se ignoran en Git; el CSV inicial sigue
versionado. Antes de entrenar se acordará cómo preservar y compartir el snapshot
seleccionado para reproducir exactamente los experimentos.
