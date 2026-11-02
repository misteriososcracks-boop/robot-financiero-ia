"""Robot Financiero IA 3.0 — exploración automática y análisis manual."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st
from analysis import analyze_history, defaults_from_file, fetch_history, public_fields, validate_symbols

st.set_page_config(page_title="Robot Financiero IA 3.0", page_icon="📈", layout="wide")
st.title("📈 Robot Financiero IA 3.0")
st.caption("México y Estados Unidos · Explorador diario y análisis individual")
st.info("Herramienta de investigación, no órdenes de compra. La zona junto al soporte requiere confirmación de rebote. Los precios pueden estar retrasados; revisa fecha, liquidez y noticias.")

@st.cache_data(ttl=600, show_spinner=False)
def read_snapshot():
    p = Path("data/market_scan.json")
    if not p.exists():
        return None
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        if obj.get("schema_version") != 1 or not isinstance(obj.get("rows"), list):
            return None
        return obj
    except (OSError, ValueError):
        return None

@st.cache_data(ttl=1800, show_spinner=False)
def history(symbol):
    return fetch_history(symbol)


def fmt_price(v, ccy):
    if v is None or pd.isna(v):
        return "No disponible"
    return f"${float(v):,.2f} {ccy}"


def show_detail(row):
    st.write(f"**{row['Símbolo']} · {row['Tendencia']}**")
    ccy = row["Moneda"]
    one, two, three, four = st.columns(4)
    one.metric("Cierre", fmt_price(row.get("Cierre"), ccy))
    two.metric("Soporte", fmt_price(row.get("Soporte"), ccy))
    three.metric("Resistencia", fmt_price(row.get("Resistencia"), ccy))
    four.metric("Distancia al soporte", f"{row['Distancia a soporte %']:.2f}%" if row.get("Distancia a soporte %") is not None else "N/D")
    if row.get("Zona entrada desde") is not None:
        st.write("**Zona de observación:** " + fmt_price(row["Zona entrada desde"], ccy) + " a " + fmt_price(row["Zona entrada hasta"], ccy))
        st.caption("Esta zona NO es un precio garantizado de compra. Si el soporte se pierde, no asumir que habrá rebote.")
        if row.get("Objetivo +1% desde zona") is not None:
            st.write("**Objetivo hipotético +1% desde el extremo superior de la zona:** " + fmt_price(row["Objetivo +1% desde zona"], ccy))
            if row.get("Espacio resistencia desde zona %") is not None and row["Espacio resistencia desde zona %"] < 1:
                st.warning("La resistencia está a menos del 1% de esta referencia: el objetivo podría chocar con ella.")
    st.caption(f"Última vela: {row.get('Fecha del dato', 'N/D')} · {row.get('Lectura', '')}")

explorer, manual, guide = st.tabs(["🔭 Explorador automático", "🔎 Mis acciones", "⚙️ Cómo actualizar"])

with explorer:
    st.subheader("Exploración de los mercados al cierre")
    if st.button("🔄 Actualizar reporte publicado", key="refresh_scan"):
        read_snapshot.clear()
        st.rerun()
    data = read_snapshot()
    if data is None:
        st.warning("Todavía no hay un reporte automático. Ejecuta una vez el flujo 'Explorador diario' en GitHub → Actions → Run workflow; luego vuelve a esta página.")
        st.write("La exploración no se ejecuta al abrir la web: así evitamos saturar los servidores y mantenemos la página rápida.")
    else:
        generated = datetime.fromisoformat(data["generated_at_utc"].replace("Z", "+00:00"))
        days_old = (datetime.now(timezone.utc)-generated).total_seconds()/86400
        if days_old > 4:
            st.warning(f"⚠️ Reporte de hace {days_old:.1f} días; podría estar desactualizado. Verifica GitHub Actions.")
        st.caption("Última exploración: " + generated.strftime("%Y-%m-%d %H:%M UTC") +
                   " · Revisa la fecha de cada acción antes de operar.")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Símbolos del universo", data["universe_count"])
        m2.metric("Con datos válidos", data["analyzed_count"])
        m3.metric("Tendencias alcistas", data["uptrend_count"])
        m4.metric("Sin analizar", data["error_count"])
        st.caption("México: lista curada en universe_mx.txt, NO catálogo exhaustivo de la BMV. "
                   "EE. UU.: componentes descargados del S&P 500. Cobertura según respuesta real del proveedor.")
        if data["error_count"]:
            with st.expander("Incidencias y símbolos sin datos"):
                st.dataframe(pd.DataFrame(data.get("errors", [])), hide_index=True, use_container_width=True)
        frame = pd.DataFrame(data["rows"])
        if frame.empty:
            st.warning("El reporte no contiene acciones utilizables.")
        else:
            a, b, c = st.columns([2, 2, 2])
            with a:
                market = st.selectbox("Bolsa", ["Ambas", "México", "Estados Unidos"])
            with b:
                only_up = st.toggle("Solo tendencias alcistas", value=True)
            with c:
                near = st.checkbox("Solo a 5% o menos del soporte", value=False)
            view = frame.copy()
            if market != "Ambas":
                view = view[view["Mercado"] == market]
            if only_up:
                view = view[view["Tendencia"] == "Alcista"]
            if near:
                view = view[view["Distancia a soporte %"].notna() & (view["Distancia a soporte %"] <= 5)]
            view = view.sort_values(["Distancia a soporte %", "Símbolo"], na_position="last")
            st.write(f"**{len(view)} acciones cumplen los filtros** · Ordenadas por cercanía al soporte")
            if view.empty:
                st.info("No hay resultados con estos filtros. Puedes desactivarlos para examinar otras acciones; eso no implica señal de compra.")
            else:
                # Ambas vistas están disponibles y usan las mismas cotizaciones del reporte.
                tab_table, tab_cards = st.tabs(["📋 Tabla completa", "🗂️ Tarjetas — 10 primeras"])
                with tab_table:
                    names = ["Símbolo", "Mercado", "Moneda", "Fecha del dato", "Cierre",
                             "Tendencia", "Soporte", "Resistencia", "Zona entrada desde", "Zona entrada hasta",
                             "Entrada de referencia", "Objetivo +1% desde zona",
                             "Distancia a soporte %", "Importe promedio 20", "Lectura"]
                    columns = [col for col in names if col in view.columns]
                    st.dataframe(view[columns], hide_index=True, use_container_width=True)
                    st.download_button("⬇️ Descargar resultados CSV", view.to_csv(index=False).encode("utf-8-sig"),
                                       "explorador_bursatil.csv", "text/csv")
                with tab_cards:
                    for n, (_, row) in enumerate(view.head(10).iterrows()):
                        with st.container(border=True):
                            st.markdown(f"### {n+1}. {row['Símbolo']} · {row['Mercado']}")
                            c1, c2, c3 = st.columns(3)
                            c1.metric("Cierre", fmt_price(row.get("Cierre"), row["Moneda"]))
                            c2.metric("Soporte", fmt_price(row.get("Soporte"), row["Moneda"]))
                            c3.metric("Resistencia", fmt_price(row.get("Resistencia"), row["Moneda"]))
                            if row.get("Zona entrada desde") is not None:
                                st.write("**Zona de observación:** " + fmt_price(row["Zona entrada desde"], row["Moneda"]) +
                                         " — " + fmt_price(row["Zona entrada hasta"], row["Moneda"]))
                            st.caption(f"Cercanía al soporte: {row.get('Distancia a soporte %')}% · Última vela: {row['Fecha del dato']}")
                st.subheader("Detalle de una acción del explorador")
                select = st.selectbox("Elegir acción para ver sus niveles", view["Símbolo"].tolist(), key="explorer_symbol")
                show_detail(view.loc[view["Símbolo"] == select].iloc[0].to_dict())

with manual:
    st.subheader("Agrega o elimina tus acciones")
    st.caption("Puedes analizarlas sin que estén en el explorador. Los cambios son de tu sesión, no de la lista programada.")
    if "manual_watch_v3" not in st.session_state:
        st.session_state.manual_watch_v3 = defaults_from_file()
    if "manual_results_v3" not in st.session_state:
        st.session_state.manual_results_v3 = []
    with st.expander("Importar CSV de símbolos"):
        upload = st.file_uploader("CSV con columna Símbolo, Simbolo, Symbol o Ticker", type="csv")
        if upload and st.button("Importar CSV", key="csv_import"):
            try:
                imported = pd.read_csv(upload)
                col = next((x for x in imported.columns if x.strip().lower() in ("símbolo", "simbolo", "symbol", "ticker")), None)
                if col is None:
                    raise ValueError("No encuentro una columna de símbolos")
                st.session_state.manual_watch_v3 = validate_symbols(imported[col].dropna().tolist())
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    edited = st.data_editor(pd.DataFrame({"Símbolo": st.session_state.manual_watch_v3}),
                            num_rows="dynamic", hide_index=True, use_container_width=True, key="editor_v3")
    try:
        symbols = validate_symbols(edited["Símbolo"].fillna("").tolist())
        st.session_state.manual_watch_v3 = symbols
    except ValueError as exc:
        symbols = []
        st.warning(str(exc))
    if symbols:
        st.download_button("⬇️ Guardar mi lista CSV", pd.DataFrame({"Símbolo": symbols}).to_csv(index=False).encode("utf-8-sig"),
                           "mis_acciones.csv", "text/csv")
    left, right = st.columns([3, 1])
    with left:
        run = st.button("🔍 Analizar mis acciones ahora", type="primary", use_container_width=True, disabled=not symbols)
    with right:
        if st.button("Actualizar cotizaciones", use_container_width=True):
            history.clear()
            st.info("Caché de precios borrada. Pulsa Analizar.")
    if run:
        rows, failed = [], []
        with st.spinner("Descargando y calculando soportes y resistencias..."):
            for symbol in symbols:
                try:
                    rows.append(analyze_history(symbol, history(symbol)))
                except Exception as exc:
                    failed.append(f"{symbol}: {exc}")
        st.session_state.manual_results_v3 = rows
        for message in failed:
            st.warning(message)
        if not rows:
            st.error("No fue posible consultar las acciones.")
    rows = st.session_state.manual_results_v3
    if rows:
        up = st.toggle("Solo tendencia alcista", value=True, key="manual_up")
        view = [r for r in rows if r["Tendencia"] == "Alcista"] if up else rows
        if not view:
            st.info("No hay tendencias alcistas entre tus acciones. Desactiva el filtro si quieres verlas todas.")
        else:
            view = sorted(view, key=lambda r: (r["Distancia a soporte %"] if r["Distancia a soporte %"] is not None else 1e10))
            st.dataframe(pd.DataFrame([public_fields(r) for r in view]), hide_index=True, use_container_width=True)
            choice = st.selectbox("Acción para gráfica y análisis", [r["Símbolo"] for r in view], key="manual_detail")
            selected = next(r for r in view if r["Símbolo"] == choice)
            show_detail(selected)
            st.line_chart(selected["_series"].tail(90), use_container_width=True)

with guide:
    st.markdown("""
    **Para crear el primer reporte:** abre tu repositorio GitHub, entra a **Actions → Explorador diario → Run workflow**.
    Al finalizar correctamente, el flujo guarda `data/market_scan.json` en GitHub y la página lo muestra.

    **Después:** GitHub Actions lo intentará automáticamente de lunes a viernes después del cierre de las dos bolsas.
    Los días feriados pueden generar reportes con la última vela disponible y la programación de GitHub puede retrasarse.

    **Para cambiar el mercado mexicano:** edita `universe_mx.txt` en GitHub (símbolos Yahoo terminados en `.MX`).
    La lista americana viene del S&P 500 y se actualiza desde su fuente externa en cada exploración.

    **Importante:** soporte no significa entrada automática. Una resistencia demasiado cercana, un hueco de apertura,
    liquidez insuficiente o ruptura del soporte pueden invalidar el planteamiento.
    """)
