"""Robot Financiero — beta pública: análisis educativo de símbolos configurables."""
import re
from datetime import datetime

import pandas as pd
import streamlit as st
import yfinance as yf

DEFAULTS = ["MSFT", "QQQ", "NVDA", "GOOGL", "AMZN", "SPY", "VTI", "AAPL"]
RISK = {"Conservador": 0.005, "Moderado": 0.01, "Alto": 0.015}

st.set_page_config(page_title="Robot Financiero IA — Beta", page_icon="📈", layout="wide")
st.title("📈 Robot Financiero IA")
st.caption("Beta pública | Análisis técnico de acciones y ETF en dólares estadounidenses")
st.info("Herramienta educativa con reglas matemáticas. No utiliza aún un modelo de IA predictiva ni ejecuta órdenes. Un puntaje alto no es una probabilidad de ganancia.")

with st.form("analisis"):
    modo = st.radio("¿Qué quieres analizar?", ["Una acción o ETF", "Comparar varios símbolos"], horizontal=True)
    simbolo = st.text_input("Escribe el símbolo de la acción o ETF", value="NVDA", help="Ejemplos: AAPL, TSLA, MSFT, NVDA, SPY").strip().upper()
    varios = st.text_input("Símbolos para comparar, separados por comas", value=", ".join(DEFAULTS), help="Ejemplo: AAPL, MSFT, NVDA, TSLA") if modo == "Comparar varios símbolos" else ""
    c1, c2 = st.columns(2)
    with c1:
        capital = st.number_input("Capital simulado (MXN)", min_value=1000.0, max_value=100000000.0, value=10000.0, step=1000.0)
    with c2:
        riesgo = st.selectbox("Nivel de riesgo", list(RISK))
    enviado = st.form_submit_button("🔎 Analizar", type="primary")


def validar_simbolos():
    raw = [simbolo] if modo == "Una acción o ETF" else varios.split(",")
    symbols = list(dict.fromkeys(s.strip().upper() for s in raw if s.strip()))
    if not symbols:
        raise ValueError("Escribe al menos un símbolo de bolsa.")
    if len(symbols) > 12:
        raise ValueError("Para evitar sobrecarga, analiza hasta 12 símbolos a la vez.")
    for s in symbols:
        if not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=-]{0,14}", s):
            raise ValueError(f"Símbolo no válido: {s}. Usa el ticker bursátil, por ejemplo TSLA.")
    return symbols


@st.cache_data(ttl=1800, show_spinner=False)
def precios_historicos(symbol):
    return yf.download(symbol, period="1y", interval="1d", auto_adjust=True, progress=False, threads=False, timeout=15)


@st.cache_data(ttl=1800, show_spinner=False)
def tipo_cambio_mxn():
    data = yf.download("MXN=X", period="5d", interval="1d", auto_adjust=True, progress=False, threads=False, timeout=15)
    if data.empty:
        raise ValueError("No se pudo consultar el tipo de cambio USD/MXN.")
    close = data["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    rate = pd.to_numeric(close, errors="coerce").dropna()
    if rate.empty or float(rate.iloc[-1]) <= 0:
        raise ValueError("El tipo de cambio disponible no es válido.")
    return float(rate.iloc[-1])


def analizar(symbol, mxn_usd):
    data = precios_historicos(symbol)
    if data.empty:
        raise ValueError("sin datos de precio; revisa si existe el símbolo")
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    needed = ["Close", "High", "Low"]
    if not all(c in data.columns for c in needed):
        raise ValueError("faltan precios necesarios para el análisis")
    prices = data[needed].apply(pd.to_numeric, errors="coerce").dropna()
    if len(prices) < 51:
        raise ValueError("historial insuficiente (se necesitan 51 sesiones)")
    close, high, low = prices["Close"], prices["High"], prices["Low"]
    current = float(close.iloc[-1]); previous = close.shift(1)
    sma20 = float(close.tail(20).mean()); sma50 = float(close.tail(50).mean())
    change20 = 100 * (current / float(close.iloc[-21]) - 1)
    tr = pd.concat([high-low, (high-previous).abs(), (low-previous).abs()], axis=1).max(axis=1)
    atr = float(tr.tail(14).mean())
    if current <= 0 or not pd.notna(atr) or atr <= 0:
        raise ValueError("precio o volatilidad inválidos")
    score = int(max(0, min(100, round(50 + max(-15, min(15, change20))*1.5 + (15 if current>sma20 else -15) + (10 if sma20>sma50 else -10)))))
    stop = max(0.01, current - 2*atr)
    distance = (current-stop)*mxn_usd
    per_trade_risk = capital*RISK[riesgo]
    price_mxn = current*mxn_usd
    shares = max(0.0, min(capital*0.20/price_mxn, per_trade_risk/distance if distance>0 else 0, capital/price_mxn))
    return {
        "Símbolo": symbol,
        "Puntuación (0-100)": score,
        "Tendencia": "Alcista" if current>sma20>sma50 else "Sin confirmar",
        "Precio (USD)": round(current, 2),
        "Cambio 20 sesiones (%)": round(change20, 2),
        "Media 20 (USD)": round(sma20, 2),
        "Media 50 (USD)": round(sma50, 2),
        "ATR 14 (USD)": round(atr, 2),
        "Stop orientativo (USD)": round(stop, 2),
        "Fracciones simuladas": round(shares, 4),
        "Capital simulado (MXN)": round(shares*price_mxn, 2),
        "Pérdida orientativa al stop (MXN)": round(shares*distance, 2),
        "Fecha del dato": str(close.index[-1].date()),
        "Cierre": close,
    }


if enviado:
    try:
        symbols = validar_simbolos()
        with st.spinner("Consultando precios y calculando indicadores..."):
            usd_mxn = tipo_cambio_mxn()
            results, errors = [], []
            for sym in symbols:
                try:
                    results.append(analizar(sym, usd_mxn))
                except Exception as e:
                    errors.append(f"{sym}: {e}")
        for e in errors:
            st.warning(e)
        if not results:
            st.error("No fue posible analizar ningún símbolo. Revisa los códigos o intenta más tarde.")
            st.stop()
        st.success(f"Análisis completado · Tipo de cambio consultado: {usd_mxn:.2f} MXN/USD")
        if modo == "Una acción o ETF":
            r = results[0]
            a,b,c = st.columns(3)
            a.metric("Precio (USD)", f"${r['Precio (USD)']:,.2f}", f"{r['Cambio 20 sesiones (%)']:+.2f}% / 20 sesiones")
            b.metric("Puntuación por reglas", f"{r['Puntuación (0-100)']}/100")
            c.metric("Tendencia", r["Tendencia"])
            st.line_chart(r["Cierre"].rename("Cierre ajustado (USD)"))
            st.write(f"**Stop orientativo:** ${r['Stop orientativo (USD)']:,.2f} USD · **Capital simulado:** ${r['Capital simulado (MXN)']:,.2f} MXN · **Pérdida estimada al stop:** ${r['Pérdida orientativa al stop (MXN)']:,.2f} MXN")
        else:
            st.subheader("Comparación de acciones y ETF")
        rows = [{k:v for k,v in r.items() if k!="Cierre"} for r in results]
        df = pd.DataFrame(rows).sort_values("Puntuación (0-100)", ascending=False)
        st.dataframe(df, hide_index=True, use_container_width=True)
        st.download_button("Descargar resultados CSV", df.to_csv(index=False).encode("utf-8-sig"), file_name=f"analisis_financiero_{datetime.now():%Y%m%d}.csv", mime="text/csv")
        st.caption("Los datos pueden tener retrasos. El stop es una referencia basada en 2 × ATR(14), no una orden ni un límite de pérdida garantizado. El tamaño simulado admite fracciones de acciones que algunos brókeres no permiten. El puntaje solo resume las reglas técnicas, no pronostica rendimientos.")
    except Exception as e:
        st.error(str(e))
