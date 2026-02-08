#!/usr/bin/env python3
"""
Sector ETF Dashboard — view all 35 sector ETFs in one place.
Charts with 8/21 EMAs + top 10 holdings per ETF.
Runs on port 5051, separate from the main Finance Dashboard (5050).
"""

from dotenv import load_dotenv
load_dotenv()

import os
import time
from datetime import datetime, timedelta
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
import requests
import yfinance as yf

app = Flask(__name__)
CORS(app)

# ── Mboum API (same key as main app) ────────────────────────────────────────
MBOUM_KEY = os.environ.get("MBOUM_KEY", "")
_chart_cache = {}  # (ticker, interval) -> records list

RANGE_DAYS = {
    "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "5y": 1825, "max": 999999,
}

# ── ETF Registry ────────────────────────────────────────────────────────────
ETF_REGISTRY = {
    "XLB": "Materials",
    "XLC": "Communication Services",
    "XLE": "Energy",
    "XLF": "Financials",
    "XLI": "Industrials",
    "XLK": "Technology",
    "XLP": "Consumer Staples",
    "XLU": "Utilities",
    "XLV": "Health Care",
    "XLY": "Consumer Discretionary",
    "XHB": "Homebuilders",
    "XME": "Metals & Mining",
    "XOP": "Oil & Gas Exploration",
    "XRT": "Retail",
    "KBE": "Banks",
    "KRE": "Regional Banks",
    "IBB": "Biotech",
    "IYR": "Real Estate",
    "IYT": "Transportation",
    "ITA": "Aerospace & Defense",
    "IGV": "Software",
    "SMH": "Semiconductors",
    "GDX": "Gold Miners",
    "SLV": "Silver",
    "GLD": "Gold",
    "URA": "Uranium",
    "TAN": "Solar Energy",
    "ARKK": "Innovation (ARK)",
    "HACK": "Cybersecurity",
    "JETS": "Airlines",
    "PAVE": "Infrastructure Development",
    "COPX": "Copper Miners",
    "LIT": "Lithium & Battery Tech",
    "BITO": "Bitcoin Strategy",
}

# ── International ETF Registry ─────────────────────────────────────────────
INTL_REGISTRY = {
    "EWJ": "Japan",
    "KWEB": "China Internet",
    "MCHI": "China Large-Cap",
    "EWZ": "Brazil",
    "INDA": "India",
    "EWT": "Taiwan",
    "EFA": "Developed Markets ex-US",
    "EEM": "Emerging Markets",
    "EWG": "Germany",
    "EWY": "South Korea",
}

# ── Live Holdings via yfinance (cached 24h) ──────────────────────────────────
_holdings_cache = {}  # ticker -> {"data": [...], "fetched_at": timestamp}
HOLDINGS_CACHE_TTL = 86400  # 24 hours

# Single-asset ETFs where yfinance has no holdings data
_SINGLE_ASSET_HOLDINGS = {
    "GLD": [{"ticker": "Gold", "name": "Physical Gold Bullion", "weight": 100.0}],
    "SLV": [{"ticker": "Silver", "name": "Physical Silver Bullion", "weight": 100.0}],
    "BITO": [{"ticker": "BTC", "name": "Bitcoin Futures (CME)", "weight": 100.0}],
}


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
        # Return cached data even if stale, or empty list
        if cached:
            return cached["data"]
        return []


# ── Mboum chart data fetcher (copied from app.py) ──────────────────────────

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


# ── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("sector_dashboard.html")


@app.route("/api/etfs")
def api_etfs():
    """Return the ETF registry as a list."""
    return jsonify([
        {"ticker": t, "description": d}
        for t, d in ETF_REGISTRY.items()
    ])


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


@app.route("/api/holdings")
def api_holdings():
    """Return all holdings for all ETFs (live from Yahoo Finance)."""
    result = {}
    for ticker in ETF_REGISTRY:
        result[ticker] = _fetch_holdings(ticker)
    return jsonify(result)


@app.route("/api/intl-etfs")
def api_intl_etfs():
    """Return the international ETF registry as a list."""
    return jsonify([
        {"ticker": t, "description": d}
        for t, d in INTL_REGISTRY.items()
    ])


@app.route("/api/intl-holdings")
def api_intl_holdings():
    """Return all holdings for international ETFs (live from Yahoo Finance)."""
    result = {}
    for ticker in INTL_REGISTRY:
        result[ticker] = _fetch_holdings(ticker)
    return jsonify(result)


if __name__ == "__main__":
    print("Starting Sector ETF Dashboard on http://localhost:5051")
    app.run(debug=True, port=5051)
