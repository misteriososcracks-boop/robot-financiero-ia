"""Exploración de mercado tras el cierre; lectura pública desde un archivo JSON.

Fuentes: S&P 500 constituents (datasets/s-and-p-500-companies, derivados de Wikipedia)
y universo mexicano curado en universe_mx.txt. No ejecuta operaciones.
"""
import argparse
import csv
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
import yfinance as yf

from analysis import analyze_history, public_fields, validate_symbols

SP500_CSV = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
ALTERNATE_SP500_CSV = "https://raw.githubusercontent.com/lawcal/sp500-components-history/main/data/sp500_components.csv"


def load_sp500():
    """No se sustituye el índice completo con una lista pequeña sin avisar."""
    errors = []
    for url in (SP500_CSV, ALTERNATE_SP500_CSV):
        try:
            req = Request(url, headers={"User-Agent": "RobotFinancieroIA/3.0"})
            with urlopen(req, timeout=25) as response:
                content = response.read().decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(content))
            if not reader.fieldnames:
                raise ValueError("CSV sin columnas")
            column = next((c for c in reader.fieldnames if c.strip().lower() in ("symbol", "ticker")), None)
            if not column:
                raise ValueError("CSV sin columna Symbol")
            tickers = []
            for entry in reader:
                raw = (entry.get(column) or "").strip().upper()
                # BRK.B -> BRK-B en Yahoo Finance; evita ticks malformados.
                symbol = raw.replace(".", "-")
                if re.fullmatch(r"[A-Z][A-Z0-9-]{0,14}", symbol):
                    tickers.append(symbol)
            tickers = list(dict.fromkeys(tickers))
            if len(tickers) < 450:
                raise ValueError(f"Fuente incompleta ({len(tickers)} símbolos)")
            return tickers, url
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError("No se pudo obtener el S&P 500 completo. " + " | ".join(errors))


def load_mexico(path="universe_mx.txt"):
    file = Path(path)
    if not file.exists():
        raise FileNotFoundError(f"No existe {file}")
    values = [line.strip().upper() for line in file.read_text(encoding="utf-8").splitlines()
              if line.strip() and not line.lstrip().startswith("#")]
    # El archivo admite más de 20 activos (el editor manual mantiene su propio límite).
    tickers = validate_symbols(values, limit=1000)
    if any(not x.endswith(".MX") for x in tickers):
        raise ValueError("El universo mexicano solo debe contener símbolos terminados en .MX")
    return tickers


def extract_symbol_frame(downloaded, symbol, count):
    """Tolera el formato MultiIndex ticker→OHLCV o OHLCV→ticker de yfinance."""
    if downloaded is None or downloaded.empty:
        raise ValueError("Yahoo sin datos")
    if isinstance(downloaded.columns, pd.MultiIndex):
        if symbol in downloaded.columns.get_level_values(0):
            one = downloaded[symbol]
        elif symbol in downloaded.columns.get_level_values(1):
            one = downloaded.xs(symbol, axis=1, level=1)
        else:
            raise ValueError("Símbolo ausente del lote")
    elif count == 1:
        one = downloaded
    else:
        raise ValueError("Yahoo no devolvió columnas separadas para el lote")
    needed = ["Close", "High", "Low", "Volume"]
    if not all(k in one.columns for k in needed):
        raise ValueError("Datos OHLCV incompletos")
    result = one[needed].apply(pd.to_numeric, errors="coerce")
    # Yahoo puede dejar días NaN para un ticker cuando el otro mercado sí operó.
    return result.dropna(subset=["Close", "High", "Low", "Volume"])


def scan_batch(symbols, download_fn=yf.download):
    df = download_fn(tickers=" ".join(symbols), period="1y", interval="1d",
                     auto_adjust=True, group_by="ticker", progress=False,
                     threads=False, timeout=40)
    results, errors = [], []
    for symbol in symbols:
        try:
            history = extract_symbol_frame(df, symbol, len(symbols))
            row = public_fields(analyze_history(symbol, history))
            # No considerar una acción operable con 0 volumen medio.
            row["Volumen promedio 20"] = int(history["Volume"].tail(20).mean())
            row["Importe promedio 20"] = round(float(
                (history["Close"] * history["Volume"]).tail(20).mean()), 2)
            row["Mercado"] = "México" if symbol.endswith(".MX") else "Estados Unidos"
            row["Entrada de referencia"] = row["Zona entrada hasta"]
            row["Objetivo +1% desde zona"] = round(row["Zona entrada hasta"] * 1.01, 2) if row["Zona entrada hasta"] is not None else None
            row["Espacio resistencia desde zona %"] = (
                round(100 * (row["Resistencia"] / row["Zona entrada hasta"] - 1), 2)
                if row["Zona entrada hasta"] and row["Resistencia"] else None)
            row["Advertencia entrada"] = (
                "Vigilar rebote, no comprar automáticamente" if row["Zona entrada hasta"] is not None
                else "Sin soporte de referencia")
            results.append(row)
        except Exception as exc:
            errors.append({"symbol": symbol, "reason": str(exc)[:160]})
    return results, errors


def run_scan(market="ambos", batch_size=25, pause=1.5, limit=0, download_fn=yf.download):
    universe, sources = [], {}
    if market in ("ambos", "mexico"):
        mx = load_mexico()
        universe.extend(mx)
        sources["México"] = "universe_mx.txt (lista curada; no todas las emisoras BMV)"
    if market in ("ambos", "usa"):
        usa, url = load_sp500()
        universe.extend(usa)
        sources["Estados Unidos"] = url
    universe = list(dict.fromkeys(universe))
    if limit:
        universe = universe[:limit]
    results, errors = [], []
    for offset in range(0, len(universe), batch_size):
        chunk = universe[offset:offset+batch_size]
        try:
            rows, bad = scan_batch(chunk, download_fn=download_fn)
            # En caso de fallo por lote, conservar errores reales y continuar.
            results.extend(rows)
            errors.extend(bad)
        except Exception as exc:
            errors.extend({"symbol": s, "reason": f"Lote fallido: {exc}"} for s in chunk)
        print(f"Lote {offset // batch_size + 1}: {min(offset+batch_size,len(universe))}/{len(universe)}, con datos: {len(results)}", flush=True)
        if pause and offset + batch_size < len(universe):
            time.sleep(pause)
    rising = sum(r["Tendencia"] == "Alcista" for r in results)
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "market_requested": market,
        "universe_count": len(universe),
        "analyzed_count": len(results),
        "error_count": len(errors),
        "uptrend_count": rising,
        "sources": sources,
        "rows": results,
        "errors": errors,
    }


def write_snapshot(data, target, minimum_coverage=0.5):
    if not data["universe_count"]:
        raise ValueError("Universo vacío")
    proportion = data["analyzed_count"] / data["universe_count"]
    if proportion < minimum_coverage:
        raise RuntimeError(
            f"Cobertura insuficiente: {data['analyzed_count']}/{data['universe_count']} "
            f"({proportion:.0%}). Se conserva el reporte anterior.")
    dest = Path(target)
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temp.replace(dest)


def main():
    parser = argparse.ArgumentParser(description="Escaneo masivo México + S&P 500")
    parser.add_argument("--market", choices=["ambos", "mexico", "usa"], default="ambos")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--pause", type=float, default=1.5)
    parser.add_argument("--limit", type=int, default=0, help="Solo pruebas; 0=universo completo")
    parser.add_argument("--out", default="data/market_scan.json")
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 75:
        parser.error("--batch-size debe estar entre 1 y 75")
    data = run_scan(args.market, args.batch_size, args.pause, args.limit)
    print(json.dumps({k: v for k, v in data.items() if k not in ("rows", "errors")}, ensure_ascii=False))
    write_snapshot(data, args.out)
    print("Guardado:", args.out)


if __name__ == "__main__":
    main()
