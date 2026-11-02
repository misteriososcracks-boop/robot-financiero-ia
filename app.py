"""Primera página del Robot Financiero: análisis educativo de acciones."""

from datetime import datetime

import pandas as pd
import streamlit as st
import yfinance as yf


SYMBOLS = ["MSFT", "QQQ", "NVDA", "GOOGL", "AMZN", "SPY", "VTI", "AAPL"]

st.set_page_config(page_title="Robot Financiero", page_icon="📈", layout="wide")
st.title("Robot Financiero")
st.caption("Escáner de prueba · acciones y ETF de Estados Unidos")
st.info(
    "Esta primera versión usa reglas matemáticas, no un modelo de IA entrenado. "
    "Muestra escenarios educativos, no órdenes ni recomendaciones de compra."
)

with st.form("configuracion"):
    capital = st.number_input(
        "Capital disponible (MXN)", min_value=1000.0, max_value=100000000.0,
        value=10000.0, step=1000.0
    )
    riesgo = st.selectbox("Nivel de riesgo", ["Conservador", "Moderado", "Alto"])
    enviado = st.form_submit_button("Analizar acciones")


@st.cache_data(ttl=1800, show_spinner=False)
def descargar_datos():
    # Se usan cierres ajustados por dividendos y desdoblamientos.
    precios = yf.download(
        SYMBOLS, period="6mo", interval="1d", auto_adjust=True,
        group_by="ticker", progress=False, threads=True, timeout=10
    )
    cambio = yf.download(
        "MXN=X", period="5d", interval="1d", auto_adjust=True,
        progress=False, timeout=10
    )
    return precios, cambio


def serie_por_simbolo(datos, simbolo):
    if not isinstance(datos.columns, pd.MultiIndex):
        return None
    if simbolo in datos.columns.get_level_values(0):
        return datos[simbolo].dropna(subset=["Close"])
    if simbolo in datos.columns.get_level_values(1):
        return datos.xs(simbolo, axis=1, level=1).dropna(subset=["Close"])
    return None


def ultimo_numero(columna):
    valores = pd.to_numeric(columna, errors="coerce").dropna()
    return float(valores.iloc[-1]) if len(valores) else None


def calcular_candidatos(precios, tipo_cambio):
    candidatos = []
    for simbolo in SYMBOLS:
        tabla = serie_por_simbolo(precios, simbolo)
        if tabla is None or len(tabla) < 51:
            continue
        cierre = pd.to_numeric(tabla["Close"], errors="coerce").dropna()
        alto = pd.to_numeric(tabla["High"], errors="coerce")
        bajo = pd.to_numeric(tabla["Low"], errors="coerce")
        if len(cierre) < 51:
            continue
        precio = float(cierre.iloc[-1])
        cambio_20d = (precio / float(cierre.iloc[-21]) - 1) * 100
        media_20 = float(cierre.tail(20).mean())
        media_50 = float(cierre.tail(50).mean())
        anterior = cierre.shift(1)
        rango = pd.concat(
            [alto - bajo, (alto - anterior).abs(), (bajo - anterior).abs()],
            axis=1,
        ).max(axis=1)
        atr = float(rango.tail(14).mean())
        if not pd.notna(atr) or atr <= 0 or precio <= 0:
            continue
        # Puntuación explícita y sencilla; no es una probabilidad de ganancia.
        puntuacion = max(
            0, min(100, round(
                50 + max(-15, min(15, cambio_20d)) * 1.5
                + (15 if precio > media_20 else -15)
                + (10 if media_20 > media_50 else -10)
            ))
        )
        stop = max(0.01, precio - 2 * atr)
        candidatos.append({
            "Símbolo": simbolo,
            "Precio USD": precio,
            "Cambio 20 días %": cambio_20d,
            "Puntuación": puntuacion,
            "Tendencia": "Alcista" if precio > media_20 > media_50 else "Sin confirmar",
            "Stop orientativo USD": stop,
            "Distancia al stop MXN": (precio - stop) * tipo_cambio,
            "Fecha de datos": str(cierre.index[-1].date()),
        })
    return sorted(candidatos, key=lambda fila: fila["Puntuación"], reverse=True)


if enviado:
    with st.spinner("Descargando precios y calculando escenarios…"):
        try:
            datos, datos_cambio = descargar_datos()
            cambio_cierre = datos_cambio["Close"]
            if isinstance(cambio_cierre, pd.DataFrame):
                cambio_cierre = cambio_cierre.iloc[:, 0]
            tipo_cambio = ultimo_numero(cambio_cierre)
            if tipo_cambio is None or tipo_cambio <= 0:
                raise ValueError("No se pudo obtener el tipo de cambio USD/MXN.")
            candidatos = calcular_candidatos(datos, tipo_cambio)
            if not candidatos:
                raise ValueError("No llegaron suficientes datos de precios para analizar.")
        except Exception as exc:
            st.error(f"No se pudo completar el análisis: {exc}")
            st.stop()

    riesgo_por_operacion = {
        "Conservador": 0.005, "Moderado": 0.01, "Alto": 0.015
    }[riesgo]
    st.success(f"Análisis terminado · datos hasta {max(c['Fecha de datos'] for c in candidatos)}")
    st.write(
        f"Tipo de cambio consultado: **{tipo_cambio:.2f} MXN por USD**. "
        f"Riesgo máximo teórico por operación: **{capital * riesgo_por_operacion:,.2f} MXN**."
    )
    st.caption(
        "La fecha corresponde al último cierre disponible. Los datos pueden tener retraso; "
        "confirma precio y tipo de cambio antes de cualquier decisión."
    )

    restante = capital
    filas = []
    for candidato in candidatos[:5]:
        precio_mxn = candidato["Precio USD"] * tipo_cambio
        limite_por_posicion = capital * 0.20
        distancia = candidato["Distancia al stop MXN"]
        limite_por_riesgo = (
            capital * riesgo_por_operacion / distancia if distancia > 0 else 0.0
        )
        fracciones = max(
            0.0, min(limite_por_posicion / precio_mxn,
                     limite_por_riesgo, restante / precio_mxn)
        )
        costo = fracciones * precio_mxn
        restante -= costo
        filas.append({
            "Símbolo": candidato["Símbolo"],
            "Puntuación (reglas)": candidato["Puntuación"],
            "Tendencia": candidato["Tendencia"],
            "Cambio 20 días": f"{candidato['Cambio 20 días %']:+.2f}%",
            "Precio USD": f"{candidato['Precio USD']:.2f}",
            "Stop orientativo USD": f"{candidato['Stop orientativo USD']:.2f}",
            "Fracción teórica": f"{fracciones:.3f}",
            "Capital teórico MXN": f"{costo:,.2f}",
            "Pérdida al stop MXN": f"{fracciones * candidato['Distancia al stop MXN']:,.2f}",
        })

    st.subheader("Oportunidades según las reglas")
    st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)
    st.metric("Capital sin asignar (escenario)", f"${restante:,.2f} MXN")
    st.caption(
        "Se calculan fracciones teóricas, que tu bróker puede no permitir. "
        "El stop es 2 × ATR(14), una estimación de volatilidad; una salida real "
        "puede ocurrir a otro precio. La puntuación sólo ordena candidatos."
    )
    st.download_button(
        "Descargar tabla CSV",
        pd.DataFrame(filas).to_csv(index=False).encode("utf-8-sig"),
        file_name=f"robot_financiero_{datetime.now():%Y%m%d}.csv",
        mime="text/csv",
    )
