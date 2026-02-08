"""
Yahoo Finance API Demo via RapidAPI
Using yahoo-finance166 by davethebeast
"""

import requests
import json

# Configuration
RAPIDAPI_KEY = "94ab48fd9amsh754957a02a8fd66p1e35e2jsnd266f229c96a"
RAPIDAPI_HOST = "yahoo-finance166.p.rapidapi.com"

headers = {
    "x-rapidapi-key": RAPIDAPI_KEY,
    "x-rapidapi-host": RAPIDAPI_HOST
}


def get_stock_price(symbol: str) -> dict:
    """Get real-time stock price for a given symbol."""
    url = f"https://{RAPIDAPI_HOST}/api/stock/get-price"
    params = {"region": "US", "symbol": symbol}
    response = requests.get(url, headers=headers, params=params)
    return response.json()


def get_stock_statistics(symbol: str) -> dict:
    """Get stock statistics (PE ratio, market cap, shares, etc.)."""
    url = f"https://{RAPIDAPI_HOST}/api/stock/get-statistics"
    params = {"symbol": symbol, "region": "US"}
    response = requests.get(url, headers=headers, params=params)
    return response.json()


def get_news(symbol: str) -> dict:
    """Get news for a stock."""
    url = f"https://{RAPIDAPI_HOST}/api/news/list"
    params = {"symbol": symbol, "region": "US"}
    response = requests.get(url, headers=headers, params=params)
    return response.json()


def print_price_info(data: dict):
    """Pretty print price information."""
    if "quoteSummary" in data and data["quoteSummary"]["result"]:
        price = data["quoteSummary"]["result"][0]["price"]
        print(f"  Symbol: {price['symbol']}")
        print(f"  Name: {price['shortName']}")
        print(f"  Price: ${price['regularMarketPrice']['raw']}")
        print(f"  Change: {price['regularMarketChange']['fmt']} ({price['regularMarketChangePercent']['fmt']})")
        print(f"  Day Range: ${price['regularMarketDayLow']['raw']} - ${price['regularMarketDayHigh']['raw']}")
        print(f"  Volume: {price['regularMarketVolume']['fmt']}")
        print(f"  Market Cap: {price['marketCap']['fmt']}")
    else:
        print(json.dumps(data, indent=2))


def print_stats_info(data: dict):
    """Pretty print statistics information."""
    if "quoteSummary" in data and data["quoteSummary"]["result"]:
        stats = data["quoteSummary"]["result"][0]["defaultKeyStatistics"]
        print(f"  Enterprise Value: {stats.get('enterpriseValue', {}).get('fmt', 'N/A')}")
        print(f"  Forward P/E: {stats.get('forwardPE', {}).get('fmt', 'N/A')}")
        print(f"  Profit Margins: {stats.get('profitMargins', {}).get('fmt', 'N/A')}")
        print(f"  Beta: {stats.get('beta', {}).get('fmt', 'N/A')}")
        print(f"  Shares Outstanding: {stats.get('sharesOutstanding', {}).get('fmt', 'N/A')}")
        print(f"  Held by Institutions: {stats.get('heldPercentInstitutions', {}).get('fmt', 'N/A')}")
    else:
        print(json.dumps(data, indent=2))


def print_news(data: dict, limit: int = 5):
    """Pretty print news articles."""
    if "data" in data and "main" in data["data"]:
        articles = data["data"]["main"]["stream"][:limit]
        for i, article in enumerate(articles, 1):
            content = article.get("content", {})
            title = content.get("title", "No title")
            pub_date = content.get("pubDate", "")[:10]
            print(f"  {i}. [{pub_date}] {title}")
    else:
        print(json.dumps(data, indent=2)[:500])


def main():
    print("=" * 60)
    print("Yahoo Finance API Demo (yahoo-finance166)")
    print("=" * 60)

    # Example 1: Get stock price
    print("\n1. Getting price for AAPL...")
    try:
        price = get_stock_price("AAPL")
        print_price_info(price)
    except Exception as e:
        print(f"Error: {e}")

    # Example 2: Get stock statistics
    print("\n2. Getting statistics for MSFT...")
    try:
        stats = get_stock_statistics("MSFT")
        print_stats_info(stats)
    except Exception as e:
        print(f"Error: {e}")

    # Example 3: Get price for another stock
    print("\n3. Getting price for GOOGL...")
    try:
        price = get_stock_price("GOOGL")
        print_price_info(price)
    except Exception as e:
        print(f"Error: {e}")

    # Example 4: Get news
    print("\n4. Getting news for TSLA...")
    try:
        news = get_news("TSLA")
        print_news(news)
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
