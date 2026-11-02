# Robot Financiero IA — Beta pública

Prototipo educativo con **Streamlit** y **yfinance**. Analiza 8 acciones/ETF de EE. UU. mediante tendencias, medias móviles, ATR y una puntuación basada en reglas. Permite ingresar capital en pesos mexicanos, elegir riesgo y exportar CSV.

**Importante:** esta versión **no contiene IA entrenada**, no ejecuta operaciones, no es asesoría financiera y no ha demostrado rentabilidad. Los precios pueden llegar retrasados y la fuente puede aplicar límites de acceso. Los resultados de cada usuario son escenarios hipotéticos, no predicciones.

## Ejecutar en computadora

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Publicar gratis con Streamlit Community Cloud

1. En GitHub crea un repositorio y sube `app.py`, `requirements.txt` y este `README.md` en la raíz.
2. En https://share.streamlit.io/ inicia sesión con GitHub y selecciona **Create app**.
3. Escoge el repositorio, la rama principal y el archivo principal `app.py`.
4. Publica y copia la URL `*.streamlit.app` que Streamlit genere. Prueba en una ventana privada y compártela.
5. No subas contraseñas, tokens, datos financieros personales ni API keys al repositorio. Para una beta pública usa capital simulado.

El servicio gratuito puede dormirse y la descarga de precios puede fallar por restricciones de la fuente. Comprueba las condiciones de uso de los datos antes de un lanzamiento comercial.

## Próximos pasos

- Más activos (30–50), indicadores RSI/MACD y filtros de liquidez.
- Backtesting histórico sin sesgo de anticipación.
- Registro de pruebas y paper trading durante 4–8 semanas.
- Capa de IA explicativa solo tras validar el motor cuantitativo.
- Cuentas y base de datos para conservar pruebas entre usuarios.

No existe actualmente persistencia por usuario: cada visita permite hacer un análisis y descargar un CSV local.
