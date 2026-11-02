"""Reporte de tendencias al cierre; no genera órdenes de compra."""
import os
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from analysis import analyze_symbol, defaults_from_file


def make_report():
    now = datetime.now(ZoneInfo("America/New_York"))
    lines = ["ROBOT FINANCIERO IA 2.2 — TENDENCIAS Y NIVELES",
             f"Generado: {now:%Y-%m-%d %H:%M} hora Nueva York", "",
             "Solo tendencias alcistas. Los soportes son zonas de observación, NO órdenes de compra.", ""]
    rows, errors = [], []
    for symbol in defaults_from_file():
        try:
            rows.append(analyze_symbol(symbol))
        except Exception as exc:
            errors.append(f"{symbol}: {exc}")
    rising = [r for r in rows if r["Tendencia"] == "Alcista"]
    rising.sort(key=lambda r: r["Distancia a soporte %"] if r["Distancia a soporte %"] is not None else float("inf"))
    if not rising:
        lines.append("No hay tendencias alcistas confirmadas en la lista analizada.")
    for r in rising:
        ccy = r["Moneda"]
        support = f"${r['Soporte']:.2f}" if r["Soporte"] is not None else "no identificado"
        resistance = f"${r['Resistencia']:.2f}" if r["Resistencia"] is not None else "sin resistencia superior validada"
        lines.extend([f"{r['Símbolo']} | cierre ${r['Cierre']:.2f} {ccy} | dato {r['Fecha del dato']}",
                      f"  Soporte {support} | Resistencia {resistance}"])
        if r["Zona entrada desde"] is not None:
            lines.append(f"  ZONA DE OBSERVACIÓN ${r['Zona entrada desde']:.2f}–${r['Zona entrada hasta']:.2f} {ccy} | {r['Lectura']}")
        lines.append("")
    if errors:
        lines.extend(["Incidencias de datos:"] + errors)
    lines.extend(["", "Un soporte puede romperse. Verificar rebote, liquidez, noticias y posibles gaps antes de considerar cualquier operación."])
    return "\n".join(lines)


def email_report(report):
    sender = os.getenv("SMTP_USER", "").strip()
    pwd = os.getenv("SMTP_APP_PASSWORD", "").strip()
    recipient = os.getenv("REPORT_EMAIL", "").strip()
    if not all((sender, pwd, recipient)):
        print("Correo no enviado: configura SMTP_USER, SMTP_APP_PASSWORD y REPORT_EMAIL")
        return
    msg = EmailMessage()
    msg["From"], msg["To"] = sender, recipient
    msg["Subject"] = "Robot Financiero — tendencias alcistas al cierre"
    msg.set_content(report)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=40) as smtp:
        smtp.login(sender, pwd)
        smtp.send_message(msg)
    print("Correo enviado")


if __name__ == "__main__":
    report = make_report()
    print(report)
    email_report(report)
