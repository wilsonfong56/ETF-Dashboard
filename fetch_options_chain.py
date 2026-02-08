#!/usr/bin/env python3
"""
Fetch options chain data for a given ticker using mboum API.
"""

from dotenv import load_dotenv
load_dotenv()

import os
import requests
import json
from datetime import datetime

API_KEY = os.environ.get("MBOUM_KEY", "")
BASE_URL = "https://api.mboum.com/v1"


def fetch_options_chain(ticker: str, expiration_date: str = None) -> dict:
    """
    Fetch options chain for a given ticker.

    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL', 'TSLA')
        expiration_date: Optional expiration date in YYYY-MM-DD format

    Returns:
        Dictionary containing options chain data
    """
    url = f"{BASE_URL}/markets/options"

    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }

    params = {
        "symbol": ticker.upper()
    }

    if expiration_date:
        params["expiration"] = expiration_date

    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching options chain: {e}")
        return None


def display_options_chain(data: dict, ticker: str):
    """Display options chain data in a readable format."""
    if not data:
        print("No data available")
        return

    print(f"\n{'='*60}")
    print(f"Options Chain for {ticker.upper()}")
    print(f"{'='*60}")

    if "data" in data:
        options_data = data["data"]

        # Display expiration dates if available
        if "expirationDates" in options_data:
            print(f"\nAvailable Expiration Dates:")
            for date in options_data["expirationDates"][:10]:
                print(f"  - {date}")

        # Display calls
        if "calls" in options_data:
            print(f"\n{'='*40}")
            print("CALLS")
            print(f"{'='*40}")
            print(f"{'Strike':<10} {'Last':<10} {'Bid':<10} {'Ask':<10} {'Volume':<10} {'OI':<10}")
            print("-" * 60)
            for call in options_data["calls"][:15]:
                strike = call.get("strike", "N/A")
                last = call.get("lastPrice", "N/A")
                bid = call.get("bid", "N/A")
                ask = call.get("ask", "N/A")
                volume = call.get("volume", "N/A")
                oi = call.get("openInterest", "N/A")
                print(f"{strike:<10} {last:<10} {bid:<10} {ask:<10} {volume:<10} {oi:<10}")

        # Display puts
        if "puts" in options_data:
            print(f"\n{'='*40}")
            print("PUTS")
            print(f"{'='*40}")
            print(f"{'Strike':<10} {'Last':<10} {'Bid':<10} {'Ask':<10} {'Volume':<10} {'OI':<10}")
            print("-" * 60)
            for put in options_data["puts"][:15]:
                strike = put.get("strike", "N/A")
                last = put.get("lastPrice", "N/A")
                bid = put.get("bid", "N/A")
                ask = put.get("ask", "N/A")
                volume = put.get("volume", "N/A")
                oi = put.get("openInterest", "N/A")
                print(f"{strike:<10} {last:<10} {bid:<10} {ask:<10} {volume:<10} {oi:<10}")
    else:
        print(json.dumps(data, indent=2))


def main():
    ticker = input("Enter ticker symbol: ").strip()
    if not ticker:
        print("No ticker provided")
        return

    exp_date = input("Enter expiration date (YYYY-MM-DD) or press Enter for default: ").strip()
    exp_date = exp_date if exp_date else None

    print(f"\nFetching options chain for {ticker.upper()}...")
    data = fetch_options_chain(ticker, exp_date)

    if data:
        display_options_chain(data, ticker)

        # Save raw data to file
        filename = f"{ticker.upper()}_options_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"\nRaw data saved to {filename}")


if __name__ == "__main__":
    main()
