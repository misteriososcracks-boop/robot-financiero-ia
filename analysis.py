"""Robot Financiero IA 2.2: tendencias y niveles técnicos orientativos.

No es un sistema de ejecución, no pronostica precios y no emite órdenes.
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

DEFAULTS = ["MSFT", "QQQ", "NVDA", "GOOGL", "AMZN", "SPY", "VTI", "AAPL"]


def validate_symbols(items, limit=20):
    symbols = list(dict.fromkeys(str(s).strip().upper() for s in items if str(s).strip()))
    if not symbols:
        raise ValueError("Escribe al menos un símbolo bursátil.")
    if len(symbols) > limit:
        raise ValueError(f"Máximo {limit} acciones o ETF por análisis.")
    for symbol in symbols:
        if not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=-]{0,14}", symbol):
            raise ValueError(f"Símbolo inválido: {symbol}")
    return symbols


def defaults_from_file(file="watchlist.txt"):
    path = Path(file)
    if not path.exists():
        return DEFAULTS.copy()
    entries = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
               if line.strip() and not line.lstrip().startswith("#")]
    try:
        return validate_symbols(entries) if entries else DEFAULTS.copy()
    except ValueError:
        return DEFAULTS.copy()


def symbol_currency(symbol):
    """Los sufijos .MX indican MXN; ticker estadounidense sin sufijo, USD."""
    return "MXN" if symbol.upper().endswith(".MX") else "USD"


def fetch_history(symbol):
    df = yf.download(symbol, period="1y", interval="1d", auto_adjust=True,
                     progress=False, threads=False, timeout=20)
    if df is None or df.empty:
        raise ValueError("Sin datos de Yahoo Finance: revisa el símbolo")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    fields = ["Close", "High", "Low", "Volume"]
    if any(c not in df.columns for c in fields):
        raise ValueError("Faltan datos de OHLCV")
    return df[fields].apply(pd.to_numeric, errors="coerce").dropna()


def analyze_history(symbol, prices):
    """Detecta tendencia y últimos niveles estructurales, sin filtrar por RSI/MACD.

    La zona es una referencia técnica para observar rebote; NO es orden de compra.
    """
    p = prices.copy()
    if isinstance(p.columns, pd.MultiIndex):
        p.columns = p.columns.get_level_values(0)
    fields = ["Close", "High", "Low", "Volume"]
    if any(k not in p.columns for k in fields):
        raise ValueError("Faltan columnas de precio")
    p = p[fields].apply(pd.to_numeric, errors="coerce").dropna()
    if len(p) < 65:
        raise ValueError("Se necesitan 65 sesiones para calcular la tendencia y los niveles")

    close, high, low = p["Close"], p["High"], p["Low"]
    last = float(close.iloc[-1])
    if not np.isfinite(last) or last <= 0:
        raise ValueError("Último cierre inválido")
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    m20, m50 = float(sma20.iloc[-1]), float(sma50.iloc[-1])
    if last > m20 > m50 and m20 >= float(sma20.iloc[-6]):
        trend = "Alcista"
    elif last < m20 < m50 and m20 <= float(sma20.iloc[-6]):
        trend = "Bajista"
    else:
        trend = "Lateral / mixta"

    prev_close = close.shift(1)
    tr = pd.concat([high-low, (high-prev_close).abs(), (low-prev_close).abs()], axis=1).max(axis=1)
    atr = float(tr.tail(14).mean())
    if not np.isfinite(atr) or atr <= 0:
        raise ValueError("Volatilidad insuficiente para calcular la zona")

    # Pivotes confirmados con 2 sesiones a ambos lados, últimas 60 sesiones.
    pivots_low, pivots_high = [], []
    for i in range(max(2, len(p)-61), len(p)-2):
        if float(low.iloc[i]) <= float(low.iloc[i-2:i+3].min()):
            pivots_low.append(float(low.iloc[i]))
        if float(high.iloc[i]) >= float(high.iloc[i-2:i+3].max()):
            pivots_high.append(float(high.iloc[i]))
    supports = [x for x in pivots_low if 0 < x < last]
    resistances = [x for x in pivots_high if x > last]
    support = max(supports) if supports else float(low.tail(20).min())
    if not 0 < support < last:
        support = float(low.tail(60).min())
    if not 0 < support < last:
        support = None  # No inventar un soporte si nunca se observó uno inferior.
    resistance = min(resistances) if resistances else float(high.tail(60).max())
    if resistance <= last:
        resistance = None  # En máximos / ruptura, no hay techo superior validado.

    # Banda visual: soporte hasta +min(25% ATR, 0.5% del soporte).
    # El piso y techo NO aseguran que sea buen negocio ni que habrá rebote.
    zone_low, zone_high, status, gap = None, None, "Sin soporte identificable", None
    if support is not None:
        zone_low = round(support, 2)
        zone_high = round(min(support + .25*atr, support*1.005), 2)
        zone_high = max(zone_low, zone_high)
        gap = round(100*(last/support-1), 2)
        status = "Cerca del soporte: observar rebote" if last <= zone_high + .5*atr else "Esperar retroceso al soporte"
        if trend != "Alcista":
            status = "Niveles de referencia (sin tendencia alcista)"

    # Potencial hasta techo visible: NO es rendimiento garantizado.
    room = round(100*(resistance/last-1), 2) if resistance is not None else None
    return {
        "Símbolo": symbol,
        "Fecha del dato": str(pd.Timestamp(close.index[-1]).date()),
        "Moneda": symbol_currency(symbol),
        "Cierre": round(last, 2),
        "Tendencia": trend,
        "Soporte": round(support, 2) if support is not None else None,
        "Resistencia": round(resistance, 2) if resistance is not None else None,
        "Zona entrada desde": zone_low,
        "Zona entrada hasta": zone_high,
        "Distancia a soporte %": gap,
        "Espacio hasta resistencia %": room,
        "Lectura": status,
        "Media 20": round(m20, 2),
        "Media 50": round(m50, 2),
        "ATR 14": round(atr, 2),
        "_series": pd.DataFrame({"Cierre": close, "Media 20": sma20, "Media 50": sma50,
                                  "Soporte": support if support is not None else np.nan,
                                  "Resistencia": resistance if resistance is not None else np.nan}),
    }


def analyze_symbol(symbol):
    return analyze_history(symbol, fetch_history(symbol))


def public_fields(row):
    return {key: value for key, value in row.items() if not key.startswith("_")}
