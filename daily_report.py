"""Resumen de cierre para la watchlist guardada en el repositorio.

SMTP solo a través de GitHub Actions Secrets. No publicar credenciales.
"""
import os
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from analysis import analyze_symbol, defaults_from_file, public_fields


def make_report():
    now = datetime.now(ZoneInfo("America/New_York"))
    lines = ["ROBOT FINANCIERO IA — REPORTE DE CIERRE", f"Generado: {now:%Y-%m-%d %H:%M} hora Nueva York",
             "", "Entrada y objetivo son CONDICIONALES, no señales de compra aseguradas.",
             "La meta 1% es bruta, no asegura resultado; solo tras rebote confirmado.", ""]
    rows, errors = [], []
    for symbol in defaults_from_file():
        try:
            rows.append(analyze_symbol(symbol))
        except Exception as exc:
            errors.append(f"{symbol}: {exc}")
    rows.sort(key=lambda d: (d["Señal"] == "VIGILAR ENTRADA", d["Puntuación"]), reverse=True)
    for r in rows:
        lines.append(f"{r['Símbolo']} | {r['Señal']} | puntaje {r['Puntuación']}/100 | dato {r['Fecha del dato']}")
        lines.append(f"  Cierre ${r['Cierre USD']:.2f} | Soporte ${r['Soporte USD']:.2f} | Resistencia {('$%.2f' % r['Resistencia USD']) if r['Resistencia USD'] else 'sin techo confirmado'}")
        if r["Entrada sugerida USD"]:
            lines.append(f"  ENTRADA ${r['Entrada sugerida USD']:.2f} | OBJETIVO +1% ${r['Objetivo +1% USD']:.2f} | STOP ${r['Stop USD']:.2f} | R/B {r['Riesgo/beneficio']}")
        else:
            lines.append(f"  SIN ENTRADA. Motivo: {r['Condiciones']}")
        lines.append("")
    if errors:
        lines.extend(["ERRORES DE DATOS:"] + errors)
    lines.append("Aviso: no comprar si hay gap, ruptura del soporte, falta de confirmación o cambios en el contexto.")
    return "\n".join(lines)


def email_report(report):
    sender = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_APP_PASSWORD", "").strip()
    recipient = os.getenv("REPORT_EMAIL", "").strip()
    if not (sender and password and recipient):
        print("Correo NO enviado: faltan secretos SMTP_USER, SMTP_APP_PASSWORD o REPORT_EMAIL")
        return
    mail = EmailMessage()
    mail["From"] = sender
    mail["To"] = recipient
    mail["Subject"] = "Robot Financiero IA — oportunidades al cierre"
    mail.set_content(report)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=40) as smtp:
        smtp.login(sender, password)
        smtp.send_message(mail)
    print("Reporte enviado al correo configurado.")


if __name__ == "__main__":
    text = make_report()
    print(text)
    email_report(text)
