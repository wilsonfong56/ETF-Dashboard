#!/usr/bin/env python3
"""
Fetch historical daily stock data for a given ticker using mboum API.
"""

from dotenv import load_dotenv
load_dotenv()

import os
import requests
import json
from datetime import datetime

API_KEY = os.environ.get("MBOUM_KEY", "")
BASE_URL = "https://api.mboum.com/v1"


def fetch_historical_data(ticker: str, interval: str = "1d", range_period: str = "1mo") -> dict:
    """
    Fetch historical stock data for a given ticker.

    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL', 'TSLA')
        interval: Data interval - '1d' for daily, '1wk' for weekly, '1mo' for monthly
        range_period: Time range - '1d', '5d', '1mo', '3mo', '6mo', '1y', '5y', 'max'

    Returns:
        Dictionary containing historical price data
    """
    url = f"{BASE_URL}/markets/stock/history"

    params = {
        "symbol": ticker.upper(),
        "interval": interval,
        "diffandsplits": "true",
        "apikey": API_KEY
    }

    if range_period:
        params["range"] = range_period

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching historical data: {e}")
        return None


def display_historical_data(data: dict, ticker: str):
    """Display historical data in a readable format."""
    if not data:
        print("No data available")
        return

    # Check for API error messages
    if data.get("success") is False:
        print(f"API Error: {data.get('message', 'Unknown error')}")
        return

    print(f"\n{'='*80}")
    print(f"Historical Data for {ticker.upper()}")
    print(f"{'='*80}")

    # Display meta info
    meta = data.get("meta", {})
    if meta:
        print(f"Exchange: {meta.get('fullExchangeName', 'N/A')}")
        print(f"Currency: {meta.get('currency', 'N/A')}")
        print(f"Current Price: ${meta.get('regularMarketPrice', 'N/A')}")
        print(f"52-Week Range: ${meta.get('fiftyTwoWeekLow', 'N/A')} - ${meta.get('fiftyTwoWeekHigh', 'N/A')}")

    # Parse body data
    body = data.get("body", {})
    if not body:
        print("No historical data in response")
        return

    # Filter out 'events' key and get price data
    price_data = []
    for key, value in body.items():
        if key != "events" and isinstance(value, dict) and "date" in value:
            price_data.append(value)

    # Sort by date
    price_data.sort(key=lambda x: x.get("date", ""), reverse=True)

    print(f"\n{'Date':<12} {'Open':<12} {'High':<12} {'Low':<12} {'Close':<12} {'Volume':<15}")
    print("-" * 80)

    for record in price_data[:30]:  # Show most recent 30 entries
        date_str = record.get("date", "N/A")
        open_p = f"{record.get('open', 0):.2f}"
        high_p = f"{record.get('high', 0):.2f}"
        low_p = f"{record.get('low', 0):.2f}"
        close_p = f"{record.get('close', 0):.2f}"
        vol = f"{record.get('volume', 0):,.0f}"

        print(f"{date_str:<12} {open_p:<12} {high_p:<12} {low_p:<12} {close_p:<12} {vol:<15}")

    print(f"\nTotal records: {len(price_data)}")


def main():
    ticker = input("Enter ticker symbol: ").strip()
    if not ticker:
        print("No ticker provided")
        return

    print("\nAvailable intervals: 1d (daily), 1wk (weekly), 1mo (monthly)")
    interval = input("Enter interval [1d]: ").strip() or "1d"

    print("\nAvailable ranges: 1d, 5d, 1mo, 3mo, 6mo, 1y, 5y, max")
    range_period = input("Enter range [1mo]: ").strip() or "1mo"

    print(f"\nFetching {interval} historical data for {ticker.upper()} ({range_period})...")
    data = fetch_historical_data(ticker, interval, range_period)

    if data:
        display_historical_data(data, ticker)

        # Save raw data to file
        filename = f"{ticker.upper()}_historical_{interval}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"\nRaw data saved to {filename}")


if __name__ == "__main__":
    main()
