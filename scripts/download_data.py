# =============================================================
#  Descarga de datos - Caso de uso: precio del petróleo (Brent)
#  Periodo: desde el 1 de enero de 2000 hasta hoy
#
#  Todos los datos son DIARIOS (días hábiles)
#  Fuente general: portal FRED (EIA, BCE, Fed, Cboe), gratis y sin clave
#  Complementaria: Yahoo Finance (futuros y mercados mundiales)
# =============================================================
import pandas as pd
from datetime import datetime
from pathlib import Path

START = '2000-01-01'
END = datetime.now().strftime('%Y-%m-%d')

# ---------------------------------------------------------------
# 1) FRED: series diarias (sin clave)
# ---------------------------------------------------------------
SERIES_FRED = {
    'DCOILBRENTEU': 'brent',        # EIA, Brent spot  -> VARIABLE OBJETIVO
    'DCOILWTICO':   'wti',          # EIA, WTI spot
    'DHHNGSP':      'gas_natural',  # EIA, Henry Hub
    'ECBDFR':       'tipo_bce',     # BCE, facilidad de depósito
    'DEXUSEU':      'usd_por_eur',  # dólares por euro
    'DEXCHUS':      'cny_por_usd',  # yuanes por dólar (China)
    'VIXCLS':       'vix',          # volatilidad de los mercados
}

def descargar_fred(serie):
    url = (f'https://fred.stlouisfed.org/graph/fredgraph.csv'
           f'?id={serie}&cosd={START}&coed={END}')
    s = pd.read_csv(url, index_col=0, parse_dates=True, na_values='.').iloc[:, 0]
    return s.rename(SERIES_FRED[serie])

print('Descargando FRED...')
fred = pd.concat([descargar_fred(s) for s in SERIES_FRED], axis=1)

# ---------------------------------------------------------------
# 2) Yahoo Finance: futuros y mercados mundiales (datos diarios)
#    Nota: BZ=F (Brent) solo tiene datos desde ~2007; el resto desde ~2000
# ---------------------------------------------------------------
def descargar_ohlcv(ticker, prefijo):
    import yfinance as yf
    df = yf.download(ticker, start=START, end=END,
                     auto_adjust=False, progress=False)
    if isinstance(df.columns, pd.MultiIndex):   # versiones recientes de yfinance
        df.columns = df.columns.get_level_values(0)
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
    return df.add_prefix(f'{prefijo}_')

def descargar_cierres(tickers):
    import yfinance as yf
    df = yf.download(list(tickers), start=START, end=END,
                     auto_adjust=False, progress=False)['Close']
    return df.rename(columns=tickers)

OTROS_YAHOO = {'HG=F': 'cobre', 'GC=F': 'oro', 'DX-Y.NYB': 'indice_dolar'}

try:
    print('Descargando Yahoo Finance...')
    yahoo = (descargar_ohlcv('BZ=F', 'brent_fut')
             .join(descargar_ohlcv('CL=F', 'wti_fut'), how='outer')
             .join(descargar_cierres(OTROS_YAHOO), how='outer'))
except Exception as e:                           # si yfinance falla, se sigue sin él
    print('Aviso: no se pudo descargar Yahoo Finance ->', e)
    yahoo = None

# ---------------------------------------------------------------
# 3) Unión en un único DataFrame diario y guardado
# ---------------------------------------------------------------
datos = fred.copy()
if yahoo is not None:
    datos = datos.join(yahoo, how='outer')

# Festivos distintos en cada mercado -> se propaga el último valor
datos = datos.sort_index().ffill()
datos = datos.dropna(subset=['brent'])        # solo días con precio del Brent
datos = datos[datos.index.dayofweek < 5]      # días laborables
datos = datos.loc[START:]
datos.index.name = 'Date'

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

datos.to_csv(DATA_DIR / "petroleo_dataset.csv")
print(datos.shape)
print(datos.tail())
