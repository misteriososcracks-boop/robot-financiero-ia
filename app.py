"""Interfaz pública del Robot Financiero IA 2.2 — tendencias y niveles."""
from datetime import datetime

import pandas as pd
import streamlit as st
from analysis import analyze_history, defaults_from_file, fetch_history, public_fields, validate_symbols

st.set_page_config(page_title="Robot Financiero IA 2.2", page_icon="📈", layout="wide")
st.title("📈 Robot Financiero IA 2.2")
st.caption("México (MXN) y Estados Unidos (USD) · Tendencia alcista · Soportes y resistencias")
st.info("Los niveles son estimaciones técnicas, no órdenes de compra. El soporte puede fallar. Los datos pueden estar retrasados y una vela diaria podría estar en formación si consultas antes del cierre.")

@st.cache_data(ttl=1800, show_spinner=False)
def history(symbol):
    return fetch_history(symbol)

if "watch_v22" not in st.session_state:
    st.session_state.watch_v22 = defaults_from_file()
if "results_v22" not in st.session_state:
    st.session_state.results_v22 = []

st.subheader("1. Selecciona las acciones que quieres analizar")
st.caption("Puedes agregar o eliminar símbolos aquí. Ejemplos: AAPL, NVDA, GMEXICOB.MX, AMXB.MX. La selección se conserva solo durante tu sesión; no cambia las alertas públicas.")
with st.expander("Importar una lista guardada en CSV"):
    uploaded = st.file_uploader("CSV con columna Símbolo / Simbolo / Symbol / Ticker", type="csv")
    if uploaded and st.button("Importar símbolos"):
        try:
            df_upload = pd.read_csv(uploaded)
            col = next((c for c in df_upload.columns if c.strip().lower() in ["símbolo", "simbolo", "symbol", "ticker"]), None)
            if col is None:
                raise ValueError("No encontré una columna de símbolos")
            st.session_state.watch_v22 = validate_symbols(df_upload[col].dropna().tolist())
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

editor = st.data_editor(pd.DataFrame({"Símbolo": st.session_state.watch_v22}),
                        num_rows="dynamic", hide_index=True, use_container_width=True,
                        key="editor_v22")
try:
    symbols = validate_symbols(editor["Símbolo"].fillna("").tolist())
    st.session_state.watch_v22 = symbols
except ValueError as exc:
    st.warning(str(exc))
    symbols = []
if symbols:
    csv = pd.DataFrame({"Símbolo": symbols}).to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇️ Descargar mi lista CSV", csv, "mis_acciones.csv", "text/csv")

c1, c2 = st.columns([3, 1])
with c1:
    run = st.button("🔎 Analizar tendencias, soportes y resistencias", type="primary", use_container_width=True, disabled=not symbols)
with c2:
    if st.button("Actualizar cotizaciones", use_container_width=True):
        history.clear()
        st.info("Datos en caché borrados. Pulsa Analizar otra vez.")
if run:
    results, errors = [], []
    with st.spinner("Consultando cotizaciones y calculando niveles técnicos..."):
        for symbol in symbols:
            try:
                results.append(analyze_history(symbol, history(symbol)))
            except Exception as exc:
                errors.append(f"{symbol}: {exc}")
    st.session_state.results_v22 = results
    for error in errors:
        st.warning(error)
    if not results:
        st.error("No se obtuvieron resultados. Revisa los símbolos e inténtalo otra vez.")

results = st.session_state.results_v22
if results:
    st.divider()
    st.subheader("2. Tendencias y niveles de referencia")
    only_up = st.toggle("Mostrar solo tendencia alcista", value=True)
    visible = [r for r in results if r["Tendencia"] == "Alcista"] if only_up else results
    if not visible:
        st.warning("No se detectó ninguna tendencia alcista con estas reglas. Desactiva el filtro para ver el resto; no significa que debas comprar otras acciones.")
    else:
        df = pd.DataFrame([public_fields(r) for r in visible])
        df = df.sort_values(["Distancia a soporte %", "Símbolo"], na_position="last")
        columns = ["Símbolo", "Moneda", "Fecha del dato", "Cierre", "Tendencia", "Soporte", "Resistencia",
                   "Zona entrada desde", "Zona entrada hasta", "Distancia a soporte %", "Lectura"]
        st.dataframe(df[columns], hide_index=True, use_container_width=True)
        st.download_button("📥 Descargar análisis CSV", df.to_csv(index=False).encode("utf-8-sig"),
                           f"robot_tendencias_{datetime.now():%Y%m%d_%H%M}.csv", "text/csv")

    st.subheader("3. Gráfica y explicación de cada acción")
    options = [r["Símbolo"] for r in visible]
    if options:
        choice = st.selectbox("Selecciona la acción", options)
        item = next(r for r in visible if r["Símbolo"] == choice)
        ccy = item["Moneda"]
        a, b, c, d = st.columns(4)
        a.metric("Cierre", f"${item['Cierre']:,.2f} {ccy}")
        b.metric("Soporte", f"${item['Soporte']:,.2f} {ccy}" if item["Soporte"] is not None else "No identificado")
        c.metric("Resistencia", f"${item['Resistencia']:,.2f} {ccy}" if item["Resistencia"] is not None else "Sin techo claro")
        d.metric("Tendencia", item["Tendencia"])
        st.line_chart(item["_series"].tail(90), use_container_width=True)
        if item["Soporte"] is not None:
            st.info(f"**Zona de entrada de referencia:** ${item['Zona entrada desde']:,.2f}–${item['Zona entrada hasta']:,.2f} {ccy}. "
                    f"**Lectura:** {item['Lectura']}. Esperar acercamiento y confirmación de rebote; "
                    "si rompe soporte, NO asumir que el nivel seguirá funcionando.")
        else:
            st.warning("No hay un soporte inferior identificable en este período. No se propone zona de entrada.")
        if item["Resistencia"] is None:
            st.caption("Sin resistencia superior confirmada en el historial reciente; evita inventar un objetivo.")
        st.caption(f"Último dato: {item['Fecha del dato']}. Los niveles son aproximaciones basadas en velas diarias y pueden cambiar con el mercado.")

st.divider()
st.caption("Para modificar la lista de los reportes por correo debes editar watchlist.txt en GitHub. La página pública no deja cambiar el archivo central por seguridad.")
