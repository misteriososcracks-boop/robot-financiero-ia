"""Envía (opcionalmente) por Gmail SMTP el resumen del escaneo completo."""
import json
import os
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo


def make_report(snapshot_path="data/market_scan.json"):
    data = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    rows = [r for r in data["rows"] if r["Tendencia"] == "Alcista"
            and r.get("Distancia a soporte %") is not None]
    rows.sort(key=lambda r: r["Distancia a soporte %"])
    lines = ["ROBOT FINANCIERO IA 3.0 — RESUMEN AL CIERRE",
             f"Generado UTC: {data['generated_at_utc']}",
             f"Analizadas: {data['analyzed_count']}/{data['universe_count']} | Incidencias: {data['error_count']}",
             f"Tendencia alcista: {data['uptrend_count']}", "",
             "10 tendencias alcistas más cercanas al soporte (NO son señales automáticas):", ""]
    for i, r in enumerate(rows[:10], 1):
        ccy = r["Moneda"]
        support = f"{r['Soporte']:.2f}" if r.get("Soporte") is not None else "N/D"
        resistance = f"{r['Resistencia']:.2f}" if r.get("Resistencia") is not None else "N/D"
        zone = (f"{r['Zona entrada desde']:.2f}–{r['Zona entrada hasta']:.2f}"
                if r.get("Zona entrada desde") is not None else "N/D")
        lines.append(f"{i}. {r['Símbolo']} {ccy} | cierre {r['Cierre']:.2f} | soporte {support} | "
                     f"resistencia {resistance} | zona {zone} | distancia {r['Distancia a soporte %']:.2f}% | "
                     f"vela {r['Fecha del dato']}")
    if not rows:
        lines.append("No se detectaron tendencias alcistas válidas.")
    lines.extend(["", "IMPORTANTE: La zona de soporte puede fallar. Esperar confirmación, revisar liquidez,"
                  "resistencias, comisiones, noticias y riesgo antes de operar."])
    return "\n".join(lines)


def email_report(report):
    sender = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_APP_PASSWORD", "").strip()
    recipient = os.getenv("REPORT_EMAIL", "").strip()
    if not all((sender, password, recipient)):
        print("Correo no enviado: faltan secretos SMTP_USER, SMTP_APP_PASSWORD o REPORT_EMAIL")
        return False
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = "Robot Financiero IA 3.0 — exploración al cierre"
    msg.set_content(report)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=40) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)
    print("Correo enviado")
    return True


if __name__ == "__main__":
    message = make_report()
    print(message)
    email_report(message)
