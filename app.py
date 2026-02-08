#!/usr/bin/env python3
"""
Finance Dashboard — browser-based interface.
Combines options analysis, stock quotes, and candlestick charts.
"""

from dotenv import load_dotenv
load_dotenv()

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import sqlite3
from flask import Flask, jsonify, render_template, request
from scipy.stats import norm

app = Flask(__name__)

CBOE_BASE = "https://cdn.cboe.com/api/global/delayed_quotes"
HEADERS = {"User-Agent": "Mozilla/5.0"}
DB_PATH = Path(__file__).parent / "iv_history.db"


# ── Database helpers ─────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS iv_history (
            symbol TEXT, date TEXT, iv30 REAL, price REAL,
            PRIMARY KEY (symbol, date)
        )
    """)
    conn.commit()
    return conn


def save_iv30(conn, symbol, iv30, price):
    today = datetime.now().strftime("%Y-%m-%d")
    conn.execute(
        "INSERT OR REPLACE INTO iv_history (symbol, date, iv30, price) VALUES (?,?,?,?)",
        (symbol.upper(), today, iv30, price),
    )
    conn.commit()


def get_iv_history(conn, symbol, days=252):
    return conn.execute(
        "SELECT date, iv30 FROM iv_history WHERE symbol=? ORDER BY date DESC LIMIT ?",
        (symbol.upper(), days),
    ).fetchall()


def calc_iv_rank(current, history):
    if len(history) < 2:
        return None
    vals = [r[1] for r in history]
    lo, hi = min(vals), max(vals)
    return ((current - lo) / (hi - lo)) * 100 if hi != lo else 50.0


def calc_iv_percentile(current, history):
    if len(history) < 2:
        return None
    vals = [r[1] for r in history]
    return (sum(1 for v in vals if v < current) / len(vals)) * 100


# ── CBOE helpers ─────────────────────────────────────────────────────────────

def fetch_cboe_quote(ticker):
    url = f"{CBOE_BASE}/quotes/{ticker.upper()}.json"
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    return resp.json().get("data", {})


def fetch_cboe_options(ticker):
    url = f"{CBOE_BASE}/options/{ticker.upper()}.json"
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    return resp.json().get("data", {}).get("options", [])


def parse_option_symbol(symbol):
    m = re.match(r"^([A-Z]+)(\d{6})([CP])(\d{8})$", symbol)
    if not m:
        return None
    ticker, exp, otype, strike = m.groups()
    return {
        "ticker": ticker,
        "expiration": datetime.strptime(exp, "%y%m%d").strftime("%Y-%m-%d"),
        "option_type": "call" if otype == "C" else "put",
        "strike": int(strike) / 1000.0,
    }


def prob_itm(otype, spot, strike, tte, iv, rf=0.045):
    if tte <= 0 or iv <= 0:
        return 0.0
    d2 = (np.log(spot / strike) + (rf - 0.5 * iv**2) * tte) / (iv * np.sqrt(tte))
    return (norm.cdf(d2) if otype == "call" else norm.cdf(-d2)) * 100


def prob_profit(otype, spot, strike, premium, tte, iv, rf=0.045):
    if premium <= 0:
        return 0.0
    be = strike + premium if otype == "call" else strike - premium
    return prob_itm(otype, spot, be, tte, iv, rf)


# ── Historical data helpers ─────────────────────────────────────────────────

def load_historical_files():
    """Find all historical JSON files."""
    files = sorted(Path(__file__).parent.glob("*_historical_*.json"), reverse=True)
    result = []
    for f in files:
        parts = f.stem.split("_")
        result.append({"filename": f.name, "ticker": parts[0]})
    return result


def parse_historical_json(filepath):
    """Parse a historical data JSON into OHLCV records."""
    with open(filepath) as f:
        data = json.load(f)
    body = data.get("body", {})
    records = []
    for key, val in body.items():
        if key != "events" and isinstance(val, dict) and "date" in val:
            records.append({
                "date": val["date"],
                "open": val.get("open"),
                "high": val.get("high"),
                "low": val.get("low"),
                "close": val.get("close"),
                "volume": val.get("volume", 0),
            })
    records.sort(key=lambda r: r["date"])
    return records, data.get("meta", {})


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/quote/<ticker>")
def api_quote(ticker):
    """Return stock quote + IV metrics."""
    try:
        quote = fetch_cboe_quote(ticker)
        price = quote.get("current_price", 0)
        iv30 = quote.get("iv30", 0)

        conn = init_db()
        save_iv30(conn, ticker, iv30, price)
        hist = get_iv_history(conn, ticker)
        conn.close()

        return jsonify({
            "ticker": ticker.upper(),
            "price": price,
            "iv30": iv30,
            "iv30_change": quote.get("iv30_change", 0),
            "iv_rank": calc_iv_rank(iv30, hist),
            "iv_percentile": calc_iv_percentile(iv30, hist),
            "iv_history_days": len(hist),
            "prev_close": quote.get("prev_day_close", 0),
            "change": quote.get("price_change", 0),
            "change_pct": quote.get("price_change_percent", 0),
            "high": quote.get("high", 0),
            "low": quote.get("low", 0),
            "open": quote.get("open", 0),
            "volume": quote.get("volume", 0),
        })
    except requests.exceptions.HTTPError:
        return jsonify({"error": f"Could not fetch data for {ticker.upper()}"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/options/<ticker>")
def api_options(ticker):
    """Return analysed options chain."""
    try:
        quote = fetch_cboe_quote(ticker)
        price = quote.get("current_price", 0)
        iv30 = quote.get("iv30", 0)
        raw = fetch_cboe_options(ticker)

        rows = []
        for opt in raw:
            parsed = parse_option_symbol(opt.get("option", ""))
            if not parsed:
                continue
            exp_dt = datetime.strptime(parsed["expiration"], "%Y-%m-%d")
            dte = (exp_dt - datetime.now()).days
            if dte < 0:
                continue
            tte = max(dte, 1) / 365.0
            iv_val = opt.get("iv", 0) or 0
            bid = opt.get("bid", 0) or 0
            ask = opt.get("ask", 0) or 0
            mid = round((bid + ask) / 2, 2) if bid and ask else (opt.get("last_trade_price", 0) or 0)
            iv_pct = round(iv_val * 100, 2)

            p_itm = round(prob_itm(parsed["option_type"], price, parsed["strike"], tte, iv_val), 1) if iv_val > 0 else 0
            p_prof = round(prob_profit(parsed["option_type"], price, parsed["strike"], mid, tte, iv_val), 1) if iv_val > 0 and mid > 0 else 0

            rows.append({
                "symbol": opt.get("option", ""),
                "type": parsed["option_type"],
                "expiration": parsed["expiration"],
                "dte": dte,
                "strike": parsed["strike"],
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "last": opt.get("last_trade_price", 0) or 0,
                "volume": int(opt.get("volume", 0) or 0),
                "oi": int(opt.get("open_interest", 0) or 0),
                "iv": iv_pct,
                "ivVsIV30": round(iv_pct - iv30, 2),
                "delta": opt.get("delta", 0) or 0,
                "gamma": opt.get("gamma", 0) or 0,
                "theta": opt.get("theta", 0) or 0,
                "vega": opt.get("vega", 0) or 0,
                "probITM": p_itm,
                "probProfit": p_prof,
                "moneyness": round((parsed["strike"] - price) / price * 100, 1),
            })

        # Collect unique expirations (limit to 6 nearest)
        expirations = sorted(set(r["expiration"] for r in rows))[:6]
        rows = [r for r in rows if r["expiration"] in expirations]

        return jsonify({
            "ticker": ticker.upper(),
            "price": price,
            "iv30": iv30,
            "expirations": expirations,
            "options": rows,
        })
    except requests.exceptions.HTTPError:
        return jsonify({"error": f"Could not fetch options for {ticker.upper()}"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


MBOUM_KEY = os.environ.get("MBOUM_KEY", "")
_chart_cache = {}  # (ticker, interval) -> records list

RANGE_DAYS = {
    "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "5y": 1825, "max": 999999,
}


def _fetch_mboum(ticker, interval):
    """Fetch all history from mboum for a ticker+interval, with simple cache."""
    cache_key = (ticker.upper(), interval)
    if cache_key in _chart_cache:
        return _chart_cache[cache_key]

    resp = requests.get(
        "https://api.mboum.com/v1/markets/stock/history",
        params={
            "symbol": ticker.upper(),
            "interval": interval,
            "diffandsplits": "false",
            "apikey": MBOUM_KEY,
        },
    )
    resp.raise_for_status()
    data = resp.json()
    body = data.get("body", {})
    records = []
    for key, val in body.items():
        if key != "events" and isinstance(val, dict) and "date" in val:
            records.append({
                "time": val["date"],
                "open": val.get("open"),
                "high": val.get("high"),
                "low": val.get("low"),
                "close": val.get("close"),
                "volume": val.get("volume", 0),
            })
    records.sort(key=lambda r: r["time"])
    _chart_cache[cache_key] = records
    return records


@app.route("/api/chart/<ticker>")
def api_chart_data(ticker):
    """Fetch OHLCV data for charting, filtered by range."""
    interval = request.args.get("interval", "1d")
    range_period = request.args.get("range", "1y")
    try:
        records = _fetch_mboum(ticker, interval)

        # Filter by range
        days = RANGE_DAYS.get(range_period, 365)
        if days < 999999:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            records = [r for r in records if r["time"] >= cutoff]

        return jsonify(records)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/historical")
def api_historical_list():
    """List available historical JSON files."""
    return jsonify(load_historical_files())


@app.route("/api/historical/<filename>")
def api_historical_data(filename):
    """Return parsed OHLCV data for a historical file."""
    filepath = Path(__file__).parent / filename
    if not filepath.exists():
        return jsonify({"error": "File not found"}), 404
    records, meta = parse_historical_json(filepath)
    return jsonify({"meta": meta, "records": records})


if __name__ == "__main__":
    print("Starting Finance Dashboard on http://localhost:5050")
    app.run(debug=True, port=5050)
