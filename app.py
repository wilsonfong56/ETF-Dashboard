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
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import sqlite3
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from scipy.stats import norm
import yfinance as yf

app = Flask(__name__)
CORS(app)

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
_chart_cache = {}  # (ticker, interval) -> {"data": [...], "fetched_at": ts}
CHART_CACHE_TTL = 900  # 15 minutes (matches Mboum API delay)
_signals_cache = {"data": None, "fetched_at": 0}
SIGNALS_CACHE_TTL = 900  # 15 minutes

RANGE_DAYS = {
    "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "5y": 1825, "max": 999999,
}

# ── ETF Registry ────────────────────────────────────────────────────────────
ETF_REGISTRY = {
    "XLB": "Materials", "XLC": "Communication Services", "XLE": "Energy",
    "XLF": "Financials", "XLI": "Industrials", "XLK": "Technology",
    "XLP": "Consumer Staples", "XLU": "Utilities", "XLV": "Health Care",
    "XLY": "Consumer Discretionary", "XHB": "Homebuilders",
    "XME": "Metals & Mining", "XOP": "Oil & Gas Exploration", "XRT": "Retail",
    "KBE": "Banks", "KRE": "Regional Banks", "IBB": "Biotech",
    "IYR": "Real Estate", "IYT": "Transportation", "ITA": "Aerospace & Defense",
    "IGV": "Software", "SMH": "Semiconductors", "GDX": "Gold Miners",
    "SLV": "Silver", "GLD": "Gold", "URA": "Uranium", "TAN": "Solar Energy",
    "ARKK": "Innovation (ARK)", "HACK": "Cybersecurity", "JETS": "Airlines",
    "PAVE": "Infrastructure Development", "COPX": "Copper Miners",
    "LIT": "Lithium & Battery Tech", "BITO": "Bitcoin Strategy",
}

INTL_REGISTRY = {
    "EWJ": "Japan", "KWEB": "China Internet", "MCHI": "China Large-Cap",
    "EWZ": "Brazil", "INDA": "India", "EWT": "Taiwan",
    "EFA": "Developed Markets ex-US", "EEM": "Emerging Markets",
    "EWG": "Germany", "EWY": "South Korea",
}

# ── Live Holdings via yfinance (cached 24h) ──────────────────────────────────
_holdings_cache = {}
HOLDINGS_CACHE_TTL = 86400

_SINGLE_ASSET_HOLDINGS = {
    "GLD": [{"ticker": "Gold", "name": "Physical Gold Bullion", "weight": 100.0}],
    "SLV": [{"ticker": "Silver", "name": "Physical Silver Bullion", "weight": 100.0}],
    "BITO": [{"ticker": "BTC", "name": "Bitcoin Futures (CME)", "weight": 100.0}],
}

# ── Risk Classification ─────────────────────────────────────────────────────
RISK_CLASS = {}
for _t in ("XLC", "XLY", "XLK", "XHB", "XRT", "IBB", "IGV", "SMH", "ARKK",
           "HACK", "JETS", "LIT", "BITO", "TAN", "XME", "XOP", "COPX", "URA",
           "KWEB", "EWT", "EWY", "EWZ", "INDA"):
    RISK_CLASS[_t] = "risk-on"
for _t in ("XLP", "XLU", "XLV", "GLD", "SLV", "GDX", "IYR", "EWJ", "EWG"):
    RISK_CLASS[_t] = "risk-off"
for _t in ("XLB", "XLE", "XLF", "XLI", "IYT", "ITA", "KBE", "KRE", "PAVE",
           "MCHI", "EFA", "EEM"):
    RISK_CLASS[_t] = "neutral"


def _fetch_holdings(etf_ticker):
    """Fetch top holdings for an ETF from Yahoo Finance, with 24h cache."""
    if etf_ticker in _SINGLE_ASSET_HOLDINGS:
        return _SINGLE_ASSET_HOLDINGS[etf_ticker]
    cached = _holdings_cache.get(etf_ticker)
    if cached and (time.time() - cached["fetched_at"]) < HOLDINGS_CACHE_TTL:
        return cached["data"]
    try:
        etf = yf.Ticker(etf_ticker)
        df = etf.funds_data.top_holdings
        holdings = []
        for symbol, row in df.iterrows():
            holdings.append({
                "ticker": symbol,
                "name": row["Name"],
                "weight": round(row["Holding Percent"] * 100, 2),
            })
        _holdings_cache[etf_ticker] = {"data": holdings, "fetched_at": time.time()}
        return holdings
    except Exception:
        if cached:
            return cached["data"]
        return []


def _fetch_mboum(ticker, interval):
    """Fetch all history from mboum for a ticker+interval, with simple cache."""
    cache_key = (ticker.upper(), interval)
    cached = _chart_cache.get(cache_key)
    if cached and (time.time() - cached["fetched_at"]) < CHART_CACHE_TTL:
        return cached["data"]

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
    _chart_cache[cache_key] = {"data": records, "fetched_at": time.time()}
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


# ── Signal indicator helpers ────────────────────────────────────────────────

def _calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas]
    losses = [abs(min(d, 0)) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _calc_ema(closes, period):
    k = 2 / (period + 1)
    ema = [closes[0]]
    for i in range(1, len(closes)):
        ema.append(closes[i] * k + ema[i - 1] * (1 - k))
    return ema


def _clamp(val, lo, hi):
    return max(lo, min(hi, val))


def _linear_score(val, lo, hi):
    if hi == lo:
        return 5.0
    return _clamp(1 + 9 * (val - lo) / (hi - lo), 1, 10)


def _compute_signals_for_etf(ticker, description):
    try:
        records = _fetch_mboum(ticker, "1d")
    except Exception:
        return None
    if not records or len(records) < 50:
        return None
    closes = [r["close"] for r in records]
    price = closes[-1]
    rsi = _calc_rsi(closes, 14)
    ema21 = _calc_ema(closes, 21)
    if rsi < 30:
        rsi_score = _linear_score(rsi, 0, 30) * 2 / 10
        rsi_score = _clamp(rsi_score, 1, 2)
    elif rsi < 50:
        rsi_score = 3 + (rsi - 30) / 20
    elif rsi < 70:
        rsi_score = 5 + 2 * (rsi - 50) / 20
    else:
        rsi_score = 7 + 3 * (rsi - 70) / 30
    rsi_score = _clamp(rsi_score, 1, 10)
    pct_from_ema = (price - ema21[-1]) / ema21[-1] * 100
    ema_score = _linear_score(pct_from_ema, -10, 10)
    idx_1m = max(0, len(closes) - 22)
    ret_1m = (price - closes[idx_1m]) / closes[idx_1m] * 100
    ret_score = _linear_score(ret_1m, -15, 15)
    momentum = round(rsi_score * 0.4 + ema_score * 0.3 + ret_score * 0.3, 1)
    recent = records[-10:]
    up_vol = sum(r["volume"] for r in recent if r["close"] >= r["open"])
    total_vol = sum(r["volume"] for r in recent)
    up_vol_ratio = up_vol / total_vol if total_vol > 0 else 0.5
    if up_vol_ratio > 0.58:
        flow = "Accum"
    elif up_vol_ratio < 0.42:
        flow = "Distrib"
    else:
        flow = "Neutral"
    return {
        "ticker": ticker, "description": description,
        "price": round(price, 2), "change_1m": round(ret_1m, 2),
        "risk_class": RISK_CLASS.get(ticker, "neutral"),
        "momentum": momentum, "rs": 5.0, "flow": flow,
    }


@app.route("/api/etfs")
def api_etfs():
    return jsonify([{"ticker": t, "description": d} for t, d in ETF_REGISTRY.items()])


@app.route("/api/holdings")
def api_holdings():
    result = {}
    for ticker in ETF_REGISTRY:
        result[ticker] = _fetch_holdings(ticker)
    return jsonify(result)


@app.route("/api/intl-etfs")
def api_intl_etfs():
    return jsonify([{"ticker": t, "description": d} for t, d in INTL_REGISTRY.items()])


@app.route("/api/intl-holdings")
def api_intl_holdings():
    result = {}
    for ticker in INTL_REGISTRY:
        result[ticker] = _fetch_holdings(ticker)
    return jsonify(result)


@app.route("/api/signals")
def api_signals():
    now = time.time()
    if _signals_cache["data"] is not None and (now - _signals_cache["fetched_at"]) < SIGNALS_CACHE_TTL:
        return jsonify(_signals_cache["data"])
    results = []
    for ticker, desc in ETF_REGISTRY.items():
        sig = _compute_signals_for_etf(ticker, desc)
        if sig:
            sig["group"] = "sector"
            results.append(sig)
    for ticker, desc in INTL_REGISTRY.items():
        sig = _compute_signals_for_etf(ticker, desc)
        if sig:
            sig["group"] = "intl"
            results.append(sig)
    if results:
        avg_ret = sum(r["change_1m"] for r in results) / len(results)
        for r in results:
            r["rs"] = round(_linear_score(r["change_1m"] - avg_ret, -10, 10), 1)
    risk_on = [r for r in results if r["risk_class"] == "risk-on"]
    risk_off = [r for r in results if r["risk_class"] == "risk-off"]
    ro_breadth = (sum(1 for r in risk_on if r["momentum"] >= 5.5) / len(risk_on) * 100) if risk_on else 0
    rf_breadth = (sum(1 for r in risk_off if r["momentum"] >= 5.5) / len(risk_off) * 100) if risk_off else 0
    ro_avg_mom = round(sum(r["momentum"] for r in risk_on) / len(risk_on), 1) if risk_on else 0
    rf_avg_mom = round(sum(r["momentum"] for r in risk_off) / len(risk_off), 1) if risk_off else 0
    accum_count = sum(1 for r in results if r["flow"] == "Accum")
    distrib_count = sum(1 for r in results if r["flow"] == "Distrib")
    if ro_breadth > 50 and rf_breadth < 50:
        regime_label = "RISK-ON"
    elif rf_breadth > 50 and ro_breadth < 50:
        regime_label = "RISK-OFF"
    elif ro_breadth < 40 and rf_breadth < 40:
        regime_label = "LIQUIDATION"
    else:
        regime_label = "MIXED"
    regime = {
        "label": regime_label, "risk_on_avg_mom": ro_avg_mom,
        "risk_off_avg_mom": rf_avg_mom, "risk_on_breadth": round(ro_breadth, 1),
        "risk_off_breadth": round(rf_breadth, 1),
        "accum_count": accum_count, "distrib_count": distrib_count,
    }
    payload = {"regime": regime, "etfs": results}
    _signals_cache["data"] = payload
    _signals_cache["fetched_at"] = now
    return jsonify(payload)


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
