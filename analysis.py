"""Motor cuantitativo educativo; ningún precio calculado garantiza una ejecución."""
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

DEFAULTS = ["MSFT", "QQQ", "NVDA", "GOOGL", "AMZN", "SPY", "VTI", "AAPL"]
RISK = {"Conservador": 0.005, "Moderado": 0.01, "Alto": 0.015}


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
               if line.strip() and not line.strip().startswith("#")]
    try:
        return validate_symbols(entries) if entries else DEFAULTS.copy()
    except ValueError:
        return DEFAULTS.copy()


def symbol_currency(symbol):
    """Mercados admitidos: títulos sin sufijo de EE. UU. (USD) y .MX (MXN)."""
    return "MXN" if symbol.upper().endswith(".MX") else "USD"


def fetch_history(symbol):
    data = yf.download(symbol, period="1y", interval="1d", auto_adjust=True,
                       progress=False, threads=False, timeout=20)
    if data is None or data.empty:
        raise ValueError("Yahoo Finance no devolvió datos; comprueba el símbolo o reintenta")
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    columns = ["Close", "High", "Low", "Volume"]
    if any(c not in data.columns for c in columns):
        raise ValueError("Faltan columnas OHLCV del proveedor")
    return data[columns].apply(pd.to_numeric, errors="coerce").dropna()


def fetch_usdmxn():
    data = yf.download("MXN=X", period="7d", interval="1d", auto_adjust=True,
                       progress=False, threads=False, timeout=20)
    if data is None or data.empty:
        raise ValueError("Tipo de cambio USD/MXN no disponible")
    close = data["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = pd.to_numeric(close, errors="coerce").dropna()
    if close.empty or close.iloc[-1] <= 0:
        raise ValueError("Tipo de cambio USD/MXN inválido")
    return float(close.iloc[-1])


def rsi_series(close, period=14):
    diff = close.diff()
    gain = diff.clip(lower=0).ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    loss = (-diff.clip(upper=0)).ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100/(1+rs)).fillna(100).where(loss != 0, 100).where(gain != 0, 0).where(~((gain == 0) & (loss == 0)), 50)


def macd_histogram(close):
    macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd - signal


def analyze_history(symbol, prices, capital_mxn=10000.0, risk_name="Moderado", mxn_usd=None,
                    fee_pct=0.0):
    """Análisis a partir de barras DIARIAS COMPLETAS: nunca usa barras futuras.

    Support: máximo pivot low en las últimas 60 sesiones, por debajo del cierre;
    resistance: mínimo pivot high sobre el cierre. Si no hay pivotes, bandas de
    mínimos/máximos recientes. La entrada es una orden límite CONDICIONAL,
    no una instrucción de comprar al precio de cierre.
    """
    prices = prices.copy()
    if isinstance(prices.columns, pd.MultiIndex):
        prices.columns = prices.columns.get_level_values(0)
    required = ["Close", "High", "Low", "Volume"]
    if any(c not in prices.columns for c in required):
        raise ValueError("Faltan datos de precio y volumen")
    p = prices[required].apply(pd.to_numeric, errors="coerce").dropna()
    if len(p) < 65:
        raise ValueError("Historial insuficiente; se requieren 65 sesiones completas")
    close, high, low, vol = (p[x] for x in required)
    last = float(close.iloc[-1])
    if not np.isfinite(last) or last <= 0:
        raise ValueError("Cierre inválido")
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    sma20, sma50 = float(ma20.iloc[-1]), float(ma50.iloc[-1])
    previous = close.shift()
    tr = pd.concat([high-low, (high-previous).abs(), (low-previous).abs()], axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1])
    if not np.isfinite(atr) or atr <= 0:
        raise ValueError("ATR insuficiente o nulo")
    rsi = float(rsi_series(close).iloc[-1])
    hist = macd_histogram(close)
    momentum = float(hist.iloc[-1]) > float(hist.iloc[-2])
    vmean = float(vol.tail(20).mean())
    vol_ratio = float(vol.iloc[-1] / vmean) if vmean > 0 else np.nan
    change20 = 100 * (last/float(close.iloc[-21])-1)

    if last > sma20 > sma50:
        trend = "Alcista"
    elif last < sma20 < sma50:
        trend = "Bajista"
    else:
        trend = "Lateral / mixta"

    # Confirmación de pivote de 5 velas, sin recurrir a datos posteriores al último cierre.
    piv_lo, piv_hi = [], []
    for i in range(max(2, len(p)-61), len(p)-2):
        if float(low.iloc[i]) == float(low.iloc[i-2:i+3].min()):
            piv_lo.append(float(low.iloc[i]))
        if float(high.iloc[i]) == float(high.iloc[i-2:i+3].max()):
            piv_hi.append(float(high.iloc[i]))
    below = [v for v in piv_lo if v < last]
    above = [v for v in piv_hi if v > last]
    support = max(below) if below else float(low.tail(20).min())
    resistance = min(above) if above else float(high.tail(20).max())
    if support >= last:
        support = float(low.tail(40).min())
    if resistance <= last:
        resistance = float(high.tail(60).max())
    # Si no hay resistencia superior observable, indicar ruptura sin techo validado.
    resistance_valid = resistance > last

    entry = round(support + 0.15 * atr, 2)  # Zona justo encima del soporte
    distance_pct = (last / entry - 1) * 100 if entry > 0 else float("inf")
    # Stop siempre inferior al soporte, con margen de volatilidad.
    stop = round(max(0.01, min(support - .30 * atr, entry * .992)), 2)
    target = round(entry * 1.01, 2)
    # Se mantiene objetivo bruto 1%; las comisiones reducen resultado neto.
    net_pct = ((target/entry)-1)*100 - 2*fee_pct if entry else None
    risk_per_share = entry - stop
    rr = (target - entry)/risk_per_share if risk_per_share > 0 else 0.0
    room = resistance_valid and target <= resistance * 0.998

    reasons = []
    if trend != "Alcista":
        reasons.append("tendencia alcista no confirmada")
    if not (45 <= rsi <= 72):
        reasons.append("RSI fuera de rango de entrada (45–72)")
    if not momentum:
        reasons.append("impulso MACD sin mejora")
    if not room:
        reasons.append("resistencia demasiado cerca del objetivo +1%")
    if not (0 <= distance_pct <= 3.0):
        reasons.append("precio de cierre demasiado alejado del soporte o entrada ya superada")
    if not (entry > support and stop < support and rr >= 1.0):
        reasons.append("relación beneficio/riesgo inferior a 1")
    if not np.isfinite(vol_ratio) or vol_ratio < 0.7:
        reasons.append("volumen inferior al filtro mínimo")
    if net_pct is not None and net_pct <= 0:
        reasons.append("comisiones absorben el objetivo bruto")

    actionable = not reasons
    signal = "VIGILAR ENTRADA" if actionable else "NO OPERAR"
    # No señalar un precio de compra como ejecutable si filtros no se cumplen.
    display_entry = entry if actionable else None
    currency = symbol_currency(symbol)
    # El tipo de cambio solo aplica si la acción cotiza en USD.
    conversion_to_mxn = 1.0 if currency == "MXN" else mxn_usd
    score = round(max(0, min(100,
        40 + (20 if trend == "Alcista" else -15)
        + (10 if 45 <= rsi <= 72 else -5)
        + (10 if momentum else -5)
        + (10 if room else -10)
        + (5 if distance_pct >= 0 and distance_pct <= 3 else -5)
        + (5 if rr >= 1 else -5))))

    risk_pct = RISK.get(risk_name, RISK["Moderado"])
    shares = 0.0
    if conversion_to_mxn and actionable and risk_per_share > 0:
        # Máximo 20% del capital invertido; riesgo por stop según perfil.
        shares = max(0, min(0.2 * capital_mxn/(entry*conversion_to_mxn),
                            capital_mxn*risk_pct/(risk_per_share*conversion_to_mxn)))

    return {
        "Símbolo": symbol,
        "Fecha del dato": str(pd.Timestamp(close.index[-1]).date()),
        "Moneda": currency,
        "Cierre": round(last, 2),
        "Tendencia": trend,
        "Puntuación": score,
        "Señal": signal,
        "Soporte": round(support, 2),
        "Resistencia": round(resistance, 2) if resistance_valid else None,
        "Entrada sugerida": display_entry,
        "Entrada condicional": entry,
        "Objetivo +1%": target if actionable else None,
        "Stop": stop if actionable else None,
        "Riesgo/beneficio": round(rr, 2),
        "RSI 14": round(rsi, 1),
        "MACD mejora": "Sí" if momentum else "No",
        "Volumen vs 20d": round(vol_ratio, 2) if np.isfinite(vol_ratio) else None,
        "Cambio 20 sesiones %": round(change20, 2),
        "Media 20": round(sma20, 2),
        "Media 50": round(sma50, 2),
        "ATR 14": round(atr, 2),
        "Fracciones simuladas": round(shares, 4) if (actionable and conversion_to_mxn) else None,
        "Capital simulado MXN": round(shares * entry * conversion_to_mxn, 2) if conversion_to_mxn else None,
        "Pérdida teórica al stop MXN": round(shares * risk_per_share * conversion_to_mxn, 2) if conversion_to_mxn else None,
        "Objetivo bruto %": 1.0,
        "Objetivo neto est. %": round(net_pct, 2),
        "Condiciones": "Esperar retroceso al precio límite y rebote confirmado; cancelar si rompe soporte." if actionable else "; ".join(reasons),
        "_series": pd.DataFrame({"Cierre": close, "SMA 20": ma20, "SMA 50": ma50,
                                 "Soporte": support, "Resistencia": resistance if resistance_valid else np.nan}),
    }


def analyze_symbol(symbol, **kwargs):
    return analyze_history(symbol, fetch_history(symbol), **kwargs)


def public_fields(record):
    return {key: value for key, value in record.items() if not key.startswith("_")}
