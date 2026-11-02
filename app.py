"""Robot Financiero IA 2.0 — beta educativa pública."""
from datetime import datetime
from io import StringIO

import pandas as pd
import streamlit as st

from analysis import (RISK, analyze_history, defaults_from_file, fetch_history,
                      fetch_usdmxn, public_fields, validate_symbols)

st.set_page_config(page_title="Robot Financiero IA 2.0", page_icon="📈", layout="wide")
st.title("📈 Robot Financiero IA 2.0")
st.caption("Acciones y ETF de EE. UU. (USD) y México (MXN) · Análisis al cierre · Plan condicional para la siguiente sesión")
st.info("Herramienta educativa basada en reglas técnicas, no en IA predictiva. No ejecuta compras, no garantiza ganar 1% y puede tener precios retrasados.")

@st.cache_data(ttl=1800, show_spinner=False)
def cached_history(symbol):
    return fetch_history(symbol)

@st.cache_data(ttl=1800, show_spinner=False)
def cached_fx():
    return fetch_usdmxn()

if "watch" not in st.session_state:
    st.session_state.watch = defaults_from_file()
if "results" not in st.session_state:
    st.session_state.results = []

st.subheader("1. Edita tus acciones desde esta página")
st.caption("Agrega o elimina filas y escribe el símbolo (ej. NVDA, AAPL, GMEXICOB.MX, WALMEX.MX). El cambio es temporal para tu sesión. Descarga tu lista para recuperarla otro día; NO modifica GitHub ni la lista de alertas automáticas.")
with st.expander("Importar lista CSV (opcional)"):
    upload = st.file_uploader("Sube un CSV con columna 'Símbolo' o 'symbol'", type="csv")
    if upload and st.button("Cargar lista del archivo"):
        try:
            frame = pd.read_csv(upload)
            col = next((c for c in frame.columns if c.strip().lower() in ["símbolo", "simbolo", "symbol", "ticker"]), None)
            if col is None:
                raise ValueError("El archivo requiere una columna Símbolo o symbol")
            st.session_state.watch = validate_symbols(frame[col].dropna().astype(str).tolist())
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

edited = st.data_editor(pd.DataFrame({"Símbolo": st.session_state.watch}),
                        num_rows="dynamic", hide_index=True, use_container_width=True,
                        key="ticker_editor")
raw = edited["Símbolo"].fillna("").astype(str).tolist()
try:
    symbols = validate_symbols(raw)
    st.session_state.watch = symbols
except ValueError as exc:
    symbols = []
    st.warning(str(exc))

if symbols:
    csv_content = pd.DataFrame({"Símbolo": symbols}).to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇️ Guardar mi lista CSV", csv_content, "mis_acciones.csv", "text/csv")

c1, c2, c3 = st.columns(3)
with c1:
    capital = st.number_input("Capital simulado (MXN)", min_value=1000., max_value=100000000., value=10000., step=1000.)
with c2:
    risk = st.selectbox("Nivel de riesgo", list(RISK), index=1)
with c3:
    commission = st.number_input("Comisión por lado (%)", min_value=0., max_value=5., value=0., step=0.05,
                                 help="Porcentaje por compra y por venta, por separado.")

col_a, col_b = st.columns([3, 1])
with col_a:
    run = st.button("🔎 Analizar precios y buscar entradas", type="primary", use_container_width=True, disabled=not symbols)
with col_b:
    if st.button("Actualizar datos", use_container_width=True):
        cached_history.clear()
        cached_fx.clear()
        st.info("Caché borrada. Pulsa Analizar para descargar datos nuevos.")

if run:
    results, errors = [], []
    with st.spinner("Descargando cierres y analizando soportes, resistencias y entrada..."):
        try:
            usd_mxn = cached_fx()
        except Exception as exc:
            usd_mxn = None
            st.warning(f"No se pudo consultar USD/MXN. Los precios se mostrarán en su moneda original, pero no se calcularán posiciones en MXN para acciones estadounidenses: {exc}")
        for symbol in symbols:
            try:
                result = analyze_history(symbol, cached_history(symbol), capital, risk, usd_mxn, commission)
                results.append(result)
            except Exception as exc:
                errors.append(f"{symbol}: {exc}")
    st.session_state.results = results
    for msg in errors:
        st.warning(msg)
    if not results:
        st.error("No hay resultados válidos; comprueba los símbolos y la fuente de precios.")

results = st.session_state.results
if results:
    st.divider()
    st.subheader("2. Tabla de oportunidades para la próxima sesión")
    st.caption("Los precios se muestran en la moneda de cotización indicada (MXN o USD). 'VIGILAR ENTRADA' exige retroceso al nivel indicado y confirmación del rebote; nunca es una compra a mercado. 'NO OPERAR' significa que no hay precio de entrada validado por las reglas.")
    rows = [public_fields(r) for r in results]
    df = pd.DataFrame(rows).sort_values(["Señal", "Puntuación"], ascending=[False, False])
    preferred = ["Símbolo", "Moneda", "Fecha del dato", "Cierre", "Tendencia", "Señal", "Puntuación",
                 "Soporte", "Resistencia", "Entrada sugerida", "Objetivo +1%",
                 "Stop", "Riesgo/beneficio", "RSI 14", "MACD mejora", "Volumen vs 20d"]
    st.dataframe(df[preferred], hide_index=True, use_container_width=True)
    st.download_button("📥 Descargar análisis completo CSV", df.to_csv(index=False).encode("utf-8-sig"),
                       f"analisis_robot_{datetime.now():%Y%m%d_%H%M}.csv", "text/csv")
    st.subheader("3. Justificación y gráfica por acción")
    selection = st.selectbox("Selecciona una acción", [r["Símbolo"] for r in results])
    chosen = next(r for r in results if r["Símbolo"] == selection)
    a, b, c, d = st.columns(4)
    currency = chosen["Moneda"]
    a.metric("Cierre", f"${chosen['Cierre']:,.2f} {currency}")
    b.metric("Soporte", f"${chosen['Soporte']:,.2f} {currency}")
    c.metric("Resistencia", f"${chosen['Resistencia']:,.2f} {currency}" if chosen["Resistencia"] else "Sin techo claro")
    d.metric("Entrada sugerida", f"${chosen['Entrada sugerida']:,.2f} {currency}" if chosen["Entrada sugerida"] else "NO OPERAR")
    st.line_chart(chosen["_series"].tail(90), use_container_width=True)
    if chosen["Señal"] == "VIGILAR ENTRADA":
        st.success(f"Entrada condicional: ${chosen['Entrada sugerida']:.2f} {currency} | Objetivo +1% bruto: ${chosen['Objetivo +1%']:.2f} {currency} | Stop teórico: ${chosen['Stop']:.2f} {currency} | Relación B/R: {chosen['Riesgo/beneficio']:.2f}. Solo vigilar si hay retroceso y confirmación de rebote.")
    else:
        st.warning("NO OPERAR: no hay entrada validada en esta sesión. Precio de referencia NO operable para observar futuros retrocesos: "
                   f"${chosen['Entrada condicional']:.2f} {currency}. Motivos: {chosen['Condiciones']}")
    st.caption(f"Última vela diaria usada: {chosen['Fecha del dato']}. Los cálculos NO incorporan noticias, resultados trimestrales ni eventos premercado. Un gap puede invalidar la entrada y el stop. La ganancia del 1% es BRUTA y las comisiones, spreads e impuestos pueden reducirla o volverla negativa.")

st.divider()
st.caption("Lista pública compartida para reportes automáticos: edita watchlist.txt en GitHub. Esta app no guarda la selección entre dispositivos/sesiones ni escribe en el repositorio para evitar que visitantes públicos cambien tus alertas.")
