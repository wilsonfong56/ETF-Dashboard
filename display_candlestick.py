#!/usr/bin/env python3
"""
Display candlestick chart from historical data JSON files.
Supports both matplotlib (mplfinance) and plotly backends.
"""

import argparse
import json
import glob
import sys
import pandas as pd


def load_json_data(filepath: str) -> dict:
    """Load JSON data from file."""
    with open(filepath, 'r') as f:
        return json.load(f)


def parse_historical_data(data: dict) -> pd.DataFrame:
    """Parse historical data into a DataFrame suitable for candlestick charts."""
    body = data.get("body", {})

    records = []
    for key, value in body.items():
        if key != "events" and isinstance(value, dict) and "date" in value:
            records.append({
                "Date": value.get("date"),
                "Open": value.get("open"),
                "High": value.get("high"),
                "Low": value.get("low"),
                "Close": value.get("close"),
                "Volume": value.get("volume", 0)
            })

    if not records:
        return None

    df = pd.DataFrame(records)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date")
    df = df.sort_index()

    return df


def display_candlestick_mpl(df: pd.DataFrame, title: str = "Stock Price"):
    """Display candlestick chart using mplfinance (static)."""
    import mplfinance as mpf

    mpf.plot(
        df,
        type="candle",
        style="charles",
        title=title,
        ylabel="Price",
        volume=True,
        ylabel_lower="Volume",
        figsize=(12, 8),
        tight_layout=True
    )


def display_candlestick_plotly(df: pd.DataFrame, title: str = "Stock Price"):
    """Display interactive candlestick chart using plotly."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    # Create subplots with shared x-axis
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        subplot_titles=(title, "Volume"),
        row_heights=[0.7, 0.3]
    )

    # Add candlestick chart
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="OHLC",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350"
        ),
        row=1, col=1
    )

    # Add volume bars with colors based on price direction
    colors = ["#26a69a" if close >= open else "#ef5350"
              for close, open in zip(df["Close"], df["Open"])]

    fig.add_trace(
        go.Bar(
            x=df.index,
            y=df["Volume"],
            name="Volume",
            marker_color=colors,
            opacity=0.7
        ),
        row=2, col=1
    )

    # Update layout for TradingView-like appearance
    fig.update_layout(
        title=title,
        yaxis_title="Price",
        yaxis2_title="Volume",
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        height=800,
        showlegend=False,
        hovermode="x unified",
        # Range selector buttons
        xaxis=dict(
            rangeselector=dict(
                buttons=list([
                    dict(count=1, label="1M", step="month", stepmode="backward"),
                    dict(count=3, label="3M", step="month", stepmode="backward"),
                    dict(count=6, label="6M", step="month", stepmode="backward"),
                    dict(count=1, label="YTD", step="year", stepmode="todate"),
                    dict(count=1, label="1Y", step="year", stepmode="backward"),
                    dict(step="all", label="All")
                ]),
                bgcolor="#1e1e1e",
                activecolor="#424242",
                font=dict(color="white")
            ),
            rangeslider=dict(visible=True, thickness=0.05),
            type="date"
        ),
        # Dark theme styling
        paper_bgcolor="#1e1e1e",
        plot_bgcolor="#1e1e1e",
        font=dict(color="white"),
        xaxis2_rangeslider_visible=False
    )

    # Update axes styling
    fig.update_xaxes(
        gridcolor="#333333",
        showgrid=True,
        zeroline=False
    )
    fig.update_yaxes(
        gridcolor="#333333",
        showgrid=True,
        zeroline=False
    )

    # Show the interactive chart
    fig.show()


def list_available_files() -> list:
    """List available historical data JSON files."""
    files = glob.glob("*_historical_*.json")
    return sorted(files, key=lambda x: x, reverse=True)


def select_file() -> str:
    """Interactive file selection."""
    files = list_available_files()

    if not files:
        print("No historical data JSON files found in current directory.")
        print("Run fetch_historical_data.py first to download data.")
        return None

    print("Available historical data files:")
    for i, f in enumerate(files, 1):
        print(f"  {i}. {f}")

    choice = input("\nEnter file number or filename: ").strip()

    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(files):
            return files[idx]
        else:
            print("Invalid selection")
            return None
    else:
        return choice


def select_backend() -> str:
    """Interactive backend selection."""
    print("\nSelect chart backend:")
    print("  1. plotly   - Interactive (zoom, pan, hover) - opens in browser")
    print("  2. mpl      - Static matplotlib chart")

    choice = input("\nEnter choice [1]: ").strip()

    if choice == "2" or choice.lower() == "mpl":
        return "mpl"
    return "plotly"


def main():
    parser = argparse.ArgumentParser(
        description="Display candlestick chart from historical data JSON files."
    )
    parser.add_argument(
        "file",
        nargs="?",
        help="Path to the JSON file (optional, will prompt if not provided)"
    )
    parser.add_argument(
        "--plotly", "-p",
        action="store_true",
        help="Use plotly backend (interactive, opens in browser)"
    )
    parser.add_argument(
        "--mpl", "-m",
        action="store_true",
        help="Use mplfinance backend (static matplotlib chart)"
    )

    args = parser.parse_args()

    # Determine file path
    if args.file:
        filepath = args.file
    else:
        filepath = select_file()
        if not filepath:
            return

    # Determine backend
    if args.plotly:
        backend = "plotly"
    elif args.mpl:
        backend = "mpl"
    else:
        backend = select_backend()

    # Load and parse data
    print(f"\nLoading {filepath}...")
    try:
        data = load_json_data(filepath)
    except FileNotFoundError:
        print(f"File not found: {filepath}")
        return
    except json.JSONDecodeError:
        print(f"Invalid JSON file: {filepath}")
        return

    # Get ticker from meta or filename
    meta = data.get("meta", {})
    ticker = meta.get("symbol", filepath.split("_")[0])

    # Parse data
    df = parse_historical_data(data)

    if df is None or df.empty:
        print("No valid price data found in file")
        return

    print(f"Loaded {len(df)} records for {ticker}")
    print(f"Date range: {df.index.min().strftime('%Y-%m-%d')} to {df.index.max().strftime('%Y-%m-%d')}")

    # Display chart
    title = f"{ticker} - Candlestick Chart"

    if backend == "plotly":
        print("\nOpening interactive chart in browser...")
        display_candlestick_plotly(df, title)
    else:
        print("\nDisplaying static chart...")
        display_candlestick_mpl(df, title)


if __name__ == "__main__":
    main()
