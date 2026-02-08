#!/usr/bin/env python3
"""
Sector ETF Dashboard — view all 35 sector ETFs in one place.
Charts with 8/21 EMAs + top 10 holdings per ETF.
Runs on port 5051, separate from the main Finance Dashboard (5050).
"""

from dotenv import load_dotenv
load_dotenv()

import os
from datetime import datetime, timedelta
from flask import Flask, jsonify, render_template, request
import requests

app = Flask(__name__)

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

# ── Hardcoded Top 10 Holdings ───────────────────────────────────────────────
ETF_HOLDINGS = {
    "XLB": [
        {"ticker": "LIN", "name": "Linde plc", "weight": 16.82},
        {"ticker": "SHW", "name": "Sherwin-Williams", "weight": 9.12},
        {"ticker": "FCX", "name": "Freeport-McMoRan", "weight": 7.85},
        {"ticker": "APD", "name": "Air Products & Chem", "weight": 7.24},
        {"ticker": "ECL", "name": "Ecolab", "weight": 5.98},
        {"ticker": "NEM", "name": "Newmont Corp", "weight": 5.46},
        {"ticker": "CTVA", "name": "Corteva", "weight": 4.72},
        {"ticker": "NUE", "name": "Nucor", "weight": 4.15},
        {"ticker": "VMC", "name": "Vulcan Materials", "weight": 3.89},
        {"ticker": "DOW", "name": "Dow Inc", "weight": 3.54},
    ],
    "XLC": [
        {"ticker": "META", "name": "Meta Platforms", "weight": 22.56},
        {"ticker": "GOOGL", "name": "Alphabet A", "weight": 12.18},
        {"ticker": "GOOG", "name": "Alphabet C", "weight": 10.94},
        {"ticker": "NFLX", "name": "Netflix", "weight": 5.42},
        {"ticker": "T", "name": "AT&T", "weight": 4.86},
        {"ticker": "CMCSA", "name": "Comcast", "weight": 4.55},
        {"ticker": "DIS", "name": "Walt Disney", "weight": 4.32},
        {"ticker": "VZ", "name": "Verizon", "weight": 4.18},
        {"ticker": "TMUS", "name": "T-Mobile US", "weight": 4.02},
        {"ticker": "EA", "name": "Electronic Arts", "weight": 2.98},
    ],
    "XLE": [
        {"ticker": "XOM", "name": "Exxon Mobil", "weight": 22.85},
        {"ticker": "CVX", "name": "Chevron", "weight": 16.42},
        {"ticker": "COP", "name": "ConocoPhillips", "weight": 8.15},
        {"ticker": "EOG", "name": "EOG Resources", "weight": 5.24},
        {"ticker": "SLB", "name": "Schlumberger", "weight": 4.98},
        {"ticker": "MPC", "name": "Marathon Petroleum", "weight": 4.72},
        {"ticker": "PSX", "name": "Phillips 66", "weight": 4.18},
        {"ticker": "VLO", "name": "Valero Energy", "weight": 3.85},
        {"ticker": "PXD", "name": "Pioneer Natural Res", "weight": 3.52},
        {"ticker": "OXY", "name": "Occidental Petroleum", "weight": 3.24},
    ],
    "XLF": [
        {"ticker": "BRK.B", "name": "Berkshire Hathaway B", "weight": 13.56},
        {"ticker": "JPM", "name": "JPMorgan Chase", "weight": 10.24},
        {"ticker": "V", "name": "Visa", "weight": 7.85},
        {"ticker": "MA", "name": "Mastercard", "weight": 6.92},
        {"ticker": "BAC", "name": "Bank of America", "weight": 4.86},
        {"ticker": "WFC", "name": "Wells Fargo", "weight": 3.95},
        {"ticker": "GS", "name": "Goldman Sachs", "weight": 3.42},
        {"ticker": "MS", "name": "Morgan Stanley", "weight": 3.18},
        {"ticker": "SPGI", "name": "S&P Global", "weight": 3.05},
        {"ticker": "BLK", "name": "BlackRock", "weight": 2.86},
    ],
    "XLI": [
        {"ticker": "GE", "name": "GE Aerospace", "weight": 8.95},
        {"ticker": "CAT", "name": "Caterpillar", "weight": 5.72},
        {"ticker": "UNP", "name": "Union Pacific", "weight": 4.86},
        {"ticker": "RTX", "name": "RTX Corp", "weight": 4.55},
        {"ticker": "HON", "name": "Honeywell", "weight": 4.32},
        {"ticker": "DE", "name": "Deere & Company", "weight": 4.12},
        {"ticker": "BA", "name": "Boeing", "weight": 3.85},
        {"ticker": "LMT", "name": "Lockheed Martin", "weight": 3.58},
        {"ticker": "ETN", "name": "Eaton Corp", "weight": 3.42},
        {"ticker": "UPS", "name": "United Parcel Service", "weight": 3.15},
    ],
    "XLK": [
        {"ticker": "MSFT", "name": "Microsoft", "weight": 20.85},
        {"ticker": "AAPL", "name": "Apple", "weight": 20.42},
        {"ticker": "NVDA", "name": "NVIDIA", "weight": 14.56},
        {"ticker": "AVGO", "name": "Broadcom", "weight": 5.18},
        {"ticker": "CRM", "name": "Salesforce", "weight": 3.24},
        {"ticker": "ADBE", "name": "Adobe", "weight": 2.98},
        {"ticker": "AMD", "name": "AMD", "weight": 2.72},
        {"ticker": "CSCO", "name": "Cisco Systems", "weight": 2.56},
        {"ticker": "ACN", "name": "Accenture", "weight": 2.42},
        {"ticker": "ORCL", "name": "Oracle", "weight": 2.35},
    ],
    "XLP": [
        {"ticker": "PG", "name": "Procter & Gamble", "weight": 14.85},
        {"ticker": "COST", "name": "Costco", "weight": 11.42},
        {"ticker": "KO", "name": "Coca-Cola", "weight": 9.56},
        {"ticker": "PEP", "name": "PepsiCo", "weight": 8.92},
        {"ticker": "WMT", "name": "Walmart", "weight": 7.85},
        {"ticker": "PM", "name": "Philip Morris", "weight": 5.24},
        {"ticker": "MDLZ", "name": "Mondelez", "weight": 3.98},
        {"ticker": "MO", "name": "Altria Group", "weight": 3.56},
        {"ticker": "CL", "name": "Colgate-Palmolive", "weight": 3.42},
        {"ticker": "STZ", "name": "Constellation Brands", "weight": 2.86},
    ],
    "XLU": [
        {"ticker": "NEE", "name": "NextEra Energy", "weight": 14.85},
        {"ticker": "SO", "name": "Southern Company", "weight": 8.56},
        {"ticker": "DUK", "name": "Duke Energy", "weight": 7.92},
        {"ticker": "CEG", "name": "Constellation Energy", "weight": 6.85},
        {"ticker": "SRE", "name": "Sempra", "weight": 4.72},
        {"ticker": "AEP", "name": "American Electric Power", "weight": 4.56},
        {"ticker": "D", "name": "Dominion Energy", "weight": 4.24},
        {"ticker": "PCG", "name": "PG&E Corp", "weight": 3.98},
        {"ticker": "EXC", "name": "Exelon", "weight": 3.56},
        {"ticker": "XEL", "name": "Xcel Energy", "weight": 3.12},
    ],
    "XLV": [
        {"ticker": "LLY", "name": "Eli Lilly", "weight": 11.85},
        {"ticker": "UNH", "name": "UnitedHealth Group", "weight": 9.56},
        {"ticker": "JNJ", "name": "Johnson & Johnson", "weight": 7.42},
        {"ticker": "MRK", "name": "Merck", "weight": 6.24},
        {"ticker": "ABBV", "name": "AbbVie", "weight": 6.12},
        {"ticker": "TMO", "name": "Thermo Fisher", "weight": 4.85},
        {"ticker": "ABT", "name": "Abbott Labs", "weight": 4.56},
        {"ticker": "DHR", "name": "Danaher", "weight": 3.92},
        {"ticker": "PFE", "name": "Pfizer", "weight": 3.56},
        {"ticker": "AMGN", "name": "Amgen", "weight": 3.24},
    ],
    "XLY": [
        {"ticker": "AMZN", "name": "Amazon", "weight": 22.56},
        {"ticker": "TSLA", "name": "Tesla", "weight": 15.85},
        {"ticker": "HD", "name": "Home Depot", "weight": 8.42},
        {"ticker": "MCD", "name": "McDonald's", "weight": 4.56},
        {"ticker": "LOW", "name": "Lowe's", "weight": 3.92},
        {"ticker": "BKNG", "name": "Booking Holdings", "weight": 3.85},
        {"ticker": "NKE", "name": "Nike", "weight": 3.24},
        {"ticker": "SBUX", "name": "Starbucks", "weight": 3.12},
        {"ticker": "TJX", "name": "TJX Companies", "weight": 2.98},
        {"ticker": "CMG", "name": "Chipotle", "weight": 2.56},
    ],
    "XHB": [
        {"ticker": "WSM", "name": "Williams-Sonoma", "weight": 5.24},
        {"ticker": "OC", "name": "Owens Corning", "weight": 4.98},
        {"ticker": "DHI", "name": "D.R. Horton", "weight": 4.72},
        {"ticker": "LEN", "name": "Lennar", "weight": 4.56},
        {"ticker": "PHM", "name": "PulteGroup", "weight": 4.42},
        {"ticker": "NVR", "name": "NVR Inc", "weight": 4.18},
        {"ticker": "FND", "name": "Floor & Decor", "weight": 3.95},
        {"ticker": "BLDR", "name": "Builders FirstSource", "weight": 3.82},
        {"ticker": "TOL", "name": "Toll Brothers", "weight": 3.68},
        {"ticker": "MHK", "name": "Mohawk Industries", "weight": 3.45},
    ],
    "XME": [
        {"ticker": "ATI", "name": "ATI Inc", "weight": 5.86},
        {"ticker": "CLF", "name": "Cleveland-Cliffs", "weight": 5.42},
        {"ticker": "STLD", "name": "Steel Dynamics", "weight": 5.18},
        {"ticker": "RS", "name": "Reliance Steel", "weight": 4.92},
        {"ticker": "NUE", "name": "Nucor", "weight": 4.85},
        {"ticker": "FCX", "name": "Freeport-McMoRan", "weight": 4.72},
        {"ticker": "AA", "name": "Alcoa", "weight": 4.56},
        {"ticker": "X", "name": "United States Steel", "weight": 4.24},
        {"ticker": "MP", "name": "MP Materials", "weight": 3.98},
        {"ticker": "RGLD", "name": "Royal Gold", "weight": 3.82},
    ],
    "XOP": [
        {"ticker": "COP", "name": "ConocoPhillips", "weight": 4.85},
        {"ticker": "DVN", "name": "Devon Energy", "weight": 4.56},
        {"ticker": "EOG", "name": "EOG Resources", "weight": 4.42},
        {"ticker": "PXD", "name": "Pioneer Natural Res", "weight": 4.28},
        {"ticker": "FANG", "name": "Diamondback Energy", "weight": 4.15},
        {"ticker": "MRO", "name": "Marathon Oil", "weight": 3.98},
        {"ticker": "OVV", "name": "Ovintiv", "weight": 3.82},
        {"ticker": "AR", "name": "Antero Resources", "weight": 3.68},
        {"ticker": "EQT", "name": "EQT Corp", "weight": 3.56},
        {"ticker": "CTRA", "name": "Coterra Energy", "weight": 3.42},
    ],
    "XRT": [
        {"ticker": "BURL", "name": "Burlington Stores", "weight": 2.85},
        {"ticker": "KMX", "name": "CarMax", "weight": 2.72},
        {"ticker": "ANF", "name": "Abercrombie & Fitch", "weight": 2.56},
        {"ticker": "BOOT", "name": "Boot Barn", "weight": 2.42},
        {"ticker": "VSCO", "name": "Victoria's Secret", "weight": 2.35},
        {"ticker": "GAP", "name": "Gap Inc", "weight": 2.28},
        {"ticker": "BBY", "name": "Best Buy", "weight": 2.18},
        {"ticker": "DKS", "name": "Dick's Sporting", "weight": 2.12},
        {"ticker": "CASY", "name": "Casey's General", "weight": 2.05},
        {"ticker": "AZO", "name": "AutoZone", "weight": 1.98},
    ],
    "KBE": [
        {"ticker": "JPM", "name": "JPMorgan Chase", "weight": 4.85},
        {"ticker": "BAC", "name": "Bank of America", "weight": 4.56},
        {"ticker": "WFC", "name": "Wells Fargo", "weight": 4.42},
        {"ticker": "GS", "name": "Goldman Sachs", "weight": 4.28},
        {"ticker": "MS", "name": "Morgan Stanley", "weight": 4.15},
        {"ticker": "C", "name": "Citigroup", "weight": 3.98},
        {"ticker": "USB", "name": "U.S. Bancorp", "weight": 3.82},
        {"ticker": "PNC", "name": "PNC Financial", "weight": 3.72},
        {"ticker": "TFC", "name": "Truist Financial", "weight": 3.56},
        {"ticker": "SCHW", "name": "Charles Schwab", "weight": 3.42},
    ],
    "KRE": [
        {"ticker": "CFG", "name": "Citizens Financial", "weight": 3.85},
        {"ticker": "RF", "name": "Regions Financial", "weight": 3.72},
        {"ticker": "HBAN", "name": "Huntington Bancshares", "weight": 3.56},
        {"ticker": "KEY", "name": "KeyCorp", "weight": 3.42},
        {"ticker": "MTB", "name": "M&T Bank", "weight": 3.28},
        {"ticker": "CMA", "name": "Comerica", "weight": 3.15},
        {"ticker": "ZION", "name": "Zions Bancorporation", "weight": 3.05},
        {"ticker": "FHN", "name": "First Horizon", "weight": 2.92},
        {"ticker": "FITB", "name": "Fifth Third Bancorp", "weight": 2.85},
        {"ticker": "WAL", "name": "Western Alliance", "weight": 2.78},
    ],
    "IBB": [
        {"ticker": "GILD", "name": "Gilead Sciences", "weight": 8.56},
        {"ticker": "AMGN", "name": "Amgen", "weight": 7.85},
        {"ticker": "VRTX", "name": "Vertex Pharma", "weight": 7.24},
        {"ticker": "REGN", "name": "Regeneron", "weight": 6.42},
        {"ticker": "MRNA", "name": "Moderna", "weight": 3.85},
        {"ticker": "BIIB", "name": "Biogen", "weight": 3.56},
        {"ticker": "ALNY", "name": "Alnylam Pharma", "weight": 3.24},
        {"ticker": "ILMN", "name": "Illumina", "weight": 2.98},
        {"ticker": "SGEN", "name": "Seagen", "weight": 2.72},
        {"ticker": "BMRN", "name": "BioMarin Pharma", "weight": 2.56},
    ],
    "IYR": [
        {"ticker": "PLD", "name": "Prologis", "weight": 9.24},
        {"ticker": "AMT", "name": "American Tower", "weight": 7.12},
        {"ticker": "EQIX", "name": "Equinix", "weight": 6.42},
        {"ticker": "CCI", "name": "Crown Castle", "weight": 4.56},
        {"ticker": "SPG", "name": "Simon Property Group", "weight": 4.12},
        {"ticker": "PSA", "name": "Public Storage", "weight": 3.85},
        {"ticker": "O", "name": "Realty Income", "weight": 3.72},
        {"ticker": "DLR", "name": "Digital Realty", "weight": 3.56},
        {"ticker": "WELL", "name": "Welltower", "weight": 3.42},
        {"ticker": "VICI", "name": "VICI Properties", "weight": 3.18},
    ],
    "IYT": [
        {"ticker": "UNP", "name": "Union Pacific", "weight": 14.56},
        {"ticker": "UPS", "name": "United Parcel Service", "weight": 10.42},
        {"ticker": "CSX", "name": "CSX Corp", "weight": 8.24},
        {"ticker": "NSC", "name": "Norfolk Southern", "weight": 7.12},
        {"ticker": "FDX", "name": "FedEx", "weight": 6.85},
        {"ticker": "DAL", "name": "Delta Air Lines", "weight": 4.56},
        {"ticker": "UAL", "name": "United Airlines", "weight": 3.85},
        {"ticker": "LUV", "name": "Southwest Airlines", "weight": 3.42},
        {"ticker": "JBHT", "name": "J.B. Hunt Transport", "weight": 3.24},
        {"ticker": "ODFL", "name": "Old Dominion Freight", "weight": 3.12},
    ],
    "ITA": [
        {"ticker": "RTX", "name": "RTX Corp", "weight": 17.85},
        {"ticker": "LMT", "name": "Lockheed Martin", "weight": 14.56},
        {"ticker": "BA", "name": "Boeing", "weight": 8.42},
        {"ticker": "GD", "name": "General Dynamics", "weight": 6.24},
        {"ticker": "NOC", "name": "Northrop Grumman", "weight": 5.85},
        {"ticker": "GE", "name": "GE Aerospace", "weight": 5.42},
        {"ticker": "TDG", "name": "TransDigm Group", "weight": 4.85},
        {"ticker": "LHX", "name": "L3Harris Tech", "weight": 4.56},
        {"ticker": "HWM", "name": "Howmet Aerospace", "weight": 3.92},
        {"ticker": "HII", "name": "Huntington Ingalls", "weight": 3.24},
    ],
    "IGV": [
        {"ticker": "MSFT", "name": "Microsoft", "weight": 9.56},
        {"ticker": "CRM", "name": "Salesforce", "weight": 7.85},
        {"ticker": "ORCL", "name": "Oracle", "weight": 7.24},
        {"ticker": "ADBE", "name": "Adobe", "weight": 5.42},
        {"ticker": "NOW", "name": "ServiceNow", "weight": 5.18},
        {"ticker": "INTU", "name": "Intuit", "weight": 4.85},
        {"ticker": "PANW", "name": "Palo Alto Networks", "weight": 4.56},
        {"ticker": "SNPS", "name": "Synopsys", "weight": 3.92},
        {"ticker": "CDNS", "name": "Cadence Design", "weight": 3.72},
        {"ticker": "WDAY", "name": "Workday", "weight": 3.42},
    ],
    "SMH": [
        {"ticker": "NVDA", "name": "NVIDIA", "weight": 20.12},
        {"ticker": "TSM", "name": "TSMC", "weight": 12.85},
        {"ticker": "AVGO", "name": "Broadcom", "weight": 8.42},
        {"ticker": "AMD", "name": "AMD", "weight": 5.56},
        {"ticker": "TXN", "name": "Texas Instruments", "weight": 5.24},
        {"ticker": "QCOM", "name": "Qualcomm", "weight": 4.85},
        {"ticker": "INTC", "name": "Intel", "weight": 4.42},
        {"ticker": "MU", "name": "Micron Technology", "weight": 4.18},
        {"ticker": "AMAT", "name": "Applied Materials", "weight": 3.92},
        {"ticker": "LRCX", "name": "Lam Research", "weight": 3.56},
    ],
    "GDX": [
        {"ticker": "NEM", "name": "Newmont Corp", "weight": 12.56},
        {"ticker": "GOLD", "name": "Barrick Gold", "weight": 8.42},
        {"ticker": "AEM", "name": "Agnico Eagle Mines", "weight": 8.24},
        {"ticker": "WPM", "name": "Wheaton Precious Metals", "weight": 6.56},
        {"ticker": "FNV", "name": "Franco-Nevada", "weight": 5.85},
        {"ticker": "GFI", "name": "Gold Fields", "weight": 4.72},
        {"ticker": "RGLD", "name": "Royal Gold", "weight": 3.98},
        {"ticker": "KGC", "name": "Kinross Gold", "weight": 3.72},
        {"ticker": "AU", "name": "AngloGold Ashanti", "weight": 3.42},
        {"ticker": "AGI", "name": "Alamos Gold", "weight": 3.18},
    ],
    "SLV": [
        {"ticker": "Silver", "name": "Physical Silver Bullion", "weight": 100.0},
        {"ticker": "-", "name": "Single-asset ETF", "weight": 0},
        {"ticker": "-", "name": "(Tracks spot silver price)", "weight": 0},
        {"ticker": "-", "name": "", "weight": 0},
        {"ticker": "-", "name": "", "weight": 0},
        {"ticker": "-", "name": "", "weight": 0},
        {"ticker": "-", "name": "", "weight": 0},
        {"ticker": "-", "name": "", "weight": 0},
        {"ticker": "-", "name": "", "weight": 0},
        {"ticker": "-", "name": "", "weight": 0},
    ],
    "GLD": [
        {"ticker": "Gold", "name": "Physical Gold Bullion", "weight": 100.0},
        {"ticker": "-", "name": "Single-asset ETF", "weight": 0},
        {"ticker": "-", "name": "(Tracks spot gold price)", "weight": 0},
        {"ticker": "-", "name": "", "weight": 0},
        {"ticker": "-", "name": "", "weight": 0},
        {"ticker": "-", "name": "", "weight": 0},
        {"ticker": "-", "name": "", "weight": 0},
        {"ticker": "-", "name": "", "weight": 0},
        {"ticker": "-", "name": "", "weight": 0},
        {"ticker": "-", "name": "", "weight": 0},
    ],
    "URA": [
        {"ticker": "CCJ", "name": "Cameco Corp", "weight": 22.56},
        {"ticker": "NXE", "name": "NexGen Energy", "weight": 7.85},
        {"ticker": "SRUUF", "name": "Sprott Physical Uranium", "weight": 6.42},
        {"ticker": "UEC", "name": "Uranium Energy Corp", "weight": 5.24},
        {"ticker": "DNN", "name": "Denison Mines", "weight": 4.85},
        {"ticker": "EU", "name": "enCore Energy", "weight": 4.12},
        {"ticker": "LEU", "name": "Centrus Energy", "weight": 3.72},
        {"ticker": "UUUU", "name": "Energy Fuels", "weight": 3.42},
        {"ticker": "BWXT", "name": "BWX Technologies", "weight": 3.18},
        {"ticker": "SMR", "name": "NuScale Power", "weight": 2.98},
    ],
    "TAN": [
        {"ticker": "ENPH", "name": "Enphase Energy", "weight": 10.56},
        {"ticker": "SEDG", "name": "SolarEdge Tech", "weight": 6.85},
        {"ticker": "FSLR", "name": "First Solar", "weight": 6.42},
        {"ticker": "RUN", "name": "Sunrun", "weight": 5.24},
        {"ticker": "NOVA", "name": "Sunnova Energy", "weight": 3.85},
        {"ticker": "ARRY", "name": "Array Technologies", "weight": 3.56},
        {"ticker": "CSIQ", "name": "Canadian Solar", "weight": 3.42},
        {"ticker": "JKS", "name": "JinkoSolar", "weight": 3.18},
        {"ticker": "MAXN", "name": "Maxeon Solar", "weight": 2.56},
        {"ticker": "SHLS", "name": "Shoals Technologies", "weight": 2.42},
    ],
    "ARKK": [
        {"ticker": "TSLA", "name": "Tesla", "weight": 12.56},
        {"ticker": "COIN", "name": "Coinbase", "weight": 8.42},
        {"ticker": "ROKU", "name": "Roku", "weight": 7.24},
        {"ticker": "SQ", "name": "Block (Square)", "weight": 5.85},
        {"ticker": "PATH", "name": "UiPath", "weight": 5.42},
        {"ticker": "RBLX", "name": "Roblox", "weight": 4.85},
        {"ticker": "DKNG", "name": "DraftKings", "weight": 4.56},
        {"ticker": "HOOD", "name": "Robinhood", "weight": 4.24},
        {"ticker": "ZM", "name": "Zoom Video", "weight": 3.98},
        {"ticker": "PLTR", "name": "Palantir", "weight": 3.72},
    ],
    "HACK": [
        {"ticker": "CRWD", "name": "CrowdStrike", "weight": 6.85},
        {"ticker": "PANW", "name": "Palo Alto Networks", "weight": 6.42},
        {"ticker": "FTNT", "name": "Fortinet", "weight": 5.85},
        {"ticker": "ZS", "name": "Zscaler", "weight": 5.24},
        {"ticker": "CSCO", "name": "Cisco Systems", "weight": 4.85},
        {"ticker": "AKAM", "name": "Akamai Technologies", "weight": 4.42},
        {"ticker": "GEN", "name": "Gen Digital", "weight": 3.98},
        {"ticker": "TENB", "name": "Tenable Holdings", "weight": 3.56},
        {"ticker": "SAIL", "name": "SailPoint Tech", "weight": 3.24},
        {"ticker": "CYBR", "name": "CyberArk Software", "weight": 3.12},
    ],
    "JETS": [
        {"ticker": "DAL", "name": "Delta Air Lines", "weight": 10.56},
        {"ticker": "UAL", "name": "United Airlines", "weight": 10.24},
        {"ticker": "LUV", "name": "Southwest Airlines", "weight": 10.12},
        {"ticker": "AAL", "name": "American Airlines", "weight": 9.85},
        {"ticker": "ALK", "name": "Alaska Air Group", "weight": 4.56},
        {"ticker": "JBLU", "name": "JetBlue Airways", "weight": 3.85},
        {"ticker": "SAVE", "name": "Spirit Airlines", "weight": 3.42},
        {"ticker": "HA", "name": "Hawaiian Airlines", "weight": 2.98},
        {"ticker": "RYAAY", "name": "Ryanair Holdings", "weight": 2.72},
        {"ticker": "SKYW", "name": "SkyWest Inc", "weight": 2.56},
    ],
    "PAVE": [
        {"ticker": "CARR", "name": "Carrier Global", "weight": 4.85},
        {"ticker": "ETN", "name": "Eaton Corp", "weight": 4.56},
        {"ticker": "URI", "name": "United Rentals", "weight": 4.32},
        {"ticker": "NUE", "name": "Nucor", "weight": 4.18},
        {"ticker": "PWR", "name": "Quanta Services", "weight": 4.05},
        {"ticker": "EMR", "name": "Emerson Electric", "weight": 3.92},
        {"ticker": "MLM", "name": "Martin Marietta", "weight": 3.78},
        {"ticker": "VMC", "name": "Vulcan Materials", "weight": 3.56},
        {"ticker": "AME", "name": "Ametek", "weight": 3.42},
        {"ticker": "FAST", "name": "Fastenal", "weight": 3.28},
    ],
    "COPX": [
        {"ticker": "FCX", "name": "Freeport-McMoRan", "weight": 14.56},
        {"ticker": "SCCO", "name": "Southern Copper", "weight": 9.85},
        {"ticker": "TECK", "name": "Teck Resources", "weight": 6.42},
        {"ticker": "HBM", "name": "Hudbay Minerals", "weight": 5.24},
        {"ticker": "ERO", "name": "Ero Copper", "weight": 4.85},
        {"ticker": "IVPAF", "name": "Ivanhoe Mines", "weight": 4.56},
        {"ticker": "CS", "name": "Capstone Copper", "weight": 4.18},
        {"ticker": "FM.TO", "name": "First Quantum Minerals", "weight": 3.92},
        {"ticker": "LUN.TO", "name": "Lundin Mining", "weight": 3.72},
        {"ticker": "TGB", "name": "Taseko Mines", "weight": 3.42},
    ],
    "LIT": [
        {"ticker": "ALB", "name": "Albemarle", "weight": 10.56},
        {"ticker": "SQM", "name": "Sociedad Quimica", "weight": 7.85},
        {"ticker": "BYDDY", "name": "BYD Company", "weight": 6.42},
        {"ticker": "TM", "name": "Toyota Motor", "weight": 5.24},
        {"ticker": "PANW", "name": "Panasonic Holdings", "weight": 4.85},
        {"ticker": "ENR", "name": "Energizer Holdings", "weight": 4.42},
        {"ticker": "LTHM", "name": "Livent", "weight": 4.18},
        {"ticker": "LAC", "name": "Lithium Americas", "weight": 3.92},
        {"ticker": "PLL", "name": "Piedmont Lithium", "weight": 3.56},
        {"ticker": "SGML", "name": "Sigma Lithium", "weight": 3.24},
    ],
    "BITO": [
        {"ticker": "BTC", "name": "Bitcoin Futures (CME)", "weight": 100.0},
        {"ticker": "-", "name": "Single-asset ETF", "weight": 0},
        {"ticker": "-", "name": "(Tracks Bitcoin via futures)", "weight": 0},
        {"ticker": "-", "name": "", "weight": 0},
        {"ticker": "-", "name": "", "weight": 0},
        {"ticker": "-", "name": "", "weight": 0},
        {"ticker": "-", "name": "", "weight": 0},
        {"ticker": "-", "name": "", "weight": 0},
        {"ticker": "-", "name": "", "weight": 0},
        {"ticker": "-", "name": "", "weight": 0},
    ],
}


# ── International ETF Holdings ──────────────────────────────────────────────
INTL_HOLDINGS = {
    "EWJ": [
        {"ticker": "TM", "name": "Toyota Motor", "weight": 5.42},
        {"ticker": "MUFG", "name": "Mitsubishi UFJ Financial", "weight": 4.18},
        {"ticker": "SONY", "name": "Sony Group", "weight": 3.85},
        {"ticker": "8035.T", "name": "Tokyo Electron", "weight": 3.56},
        {"ticker": "8306.T", "name": "Sumitomo Mitsui Financial", "weight": 3.24},
        {"ticker": "6758.T", "name": "Hitachi", "weight": 2.98},
        {"ticker": "6501.T", "name": "Keyence", "weight": 2.72},
        {"ticker": "9984.T", "name": "SoftBank Group", "weight": 2.56},
        {"ticker": "7203.T", "name": "Recruit Holdings", "weight": 2.42},
        {"ticker": "6902.T", "name": "Shin-Etsu Chemical", "weight": 2.28},
    ],
    "KWEB": [
        {"ticker": "PDD", "name": "PDD Holdings", "weight": 10.56},
        {"ticker": "BABA", "name": "Alibaba Group", "weight": 9.85},
        {"ticker": "TCOM", "name": "Trip.com Group", "weight": 7.24},
        {"ticker": "JD", "name": "JD.com", "weight": 6.42},
        {"ticker": "BIDU", "name": "Baidu", "weight": 5.85},
        {"ticker": "NTES", "name": "NetEase", "weight": 5.24},
        {"ticker": "BILI", "name": "Bilibili", "weight": 4.56},
        {"ticker": "KC", "name": "Kingsoft Cloud", "weight": 3.85},
        {"ticker": "MNSO", "name": "Miniso Group", "weight": 3.42},
        {"ticker": "ZTO", "name": "ZTO Express", "weight": 3.12},
    ],
    "MCHI": [
        {"ticker": "BABA", "name": "Alibaba Group", "weight": 10.24},
        {"ticker": "TCEHY", "name": "Tencent Holdings", "weight": 9.56},
        {"ticker": "PDD", "name": "PDD Holdings", "weight": 6.85},
        {"ticker": "3690.HK", "name": "Meituan", "weight": 5.42},
        {"ticker": "JD", "name": "JD.com", "weight": 4.85},
        {"ticker": "939.HK", "name": "China Construction Bank", "weight": 3.92},
        {"ticker": "NTES", "name": "NetEase", "weight": 3.56},
        {"ticker": "1398.HK", "name": "ICBC", "weight": 3.24},
        {"ticker": "BIDU", "name": "Baidu", "weight": 2.98},
        {"ticker": "2318.HK", "name": "Ping An Insurance", "weight": 2.72},
    ],
    "EWZ": [
        {"ticker": "VALE", "name": "Vale S.A.", "weight": 14.56},
        {"ticker": "PBR", "name": "Petrobras", "weight": 10.85},
        {"ticker": "ITUB", "name": "Itau Unibanco", "weight": 7.24},
        {"ticker": "BBD", "name": "Banco Bradesco", "weight": 5.42},
        {"ticker": "NU", "name": "Nu Holdings", "weight": 4.85},
        {"ticker": "WEG", "name": "WEG S.A.", "weight": 4.18},
        {"ticker": "B3SA3.SA", "name": "B3 - Brasil Bolsa", "weight": 3.72},
        {"ticker": "ABEV", "name": "Ambev", "weight": 3.42},
        {"ticker": "SUZB3.SA", "name": "Suzano", "weight": 3.18},
        {"ticker": "RENT3.SA", "name": "Localiza", "weight": 2.85},
    ],
    "INDA": [
        {"ticker": "RELIANCE.NS", "name": "Reliance Industries", "weight": 10.56},
        {"ticker": "INFY", "name": "Infosys", "weight": 6.85},
        {"ticker": "HDB", "name": "HDFC Bank", "weight": 6.42},
        {"ticker": "TCS.NS", "name": "Tata Consultancy", "weight": 4.85},
        {"ticker": "ICICIBANK.NS", "name": "ICICI Bank", "weight": 4.56},
        {"ticker": "BHARTIARTL.NS", "name": "Bharti Airtel", "weight": 3.92},
        {"ticker": "LT.NS", "name": "Larsen & Toubro", "weight": 3.42},
        {"ticker": "HINDUNILVR.NS", "name": "Hindustan Unilever", "weight": 3.18},
        {"ticker": "SBIN.NS", "name": "State Bank of India", "weight": 2.85},
        {"ticker": "ITC.NS", "name": "ITC Limited", "weight": 2.56},
    ],
    "EWT": [
        {"ticker": "TSM", "name": "TSMC", "weight": 23.56},
        {"ticker": "2317.TW", "name": "Hon Hai Precision", "weight": 5.42},
        {"ticker": "2454.TW", "name": "MediaTek", "weight": 5.18},
        {"ticker": "2330.TW", "name": "Delta Electronics", "weight": 3.85},
        {"ticker": "2881.TW", "name": "Fubon Financial", "weight": 3.42},
        {"ticker": "2882.TW", "name": "Cathay Financial", "weight": 3.18},
        {"ticker": "2891.TW", "name": "CTBC Financial", "weight": 2.85},
        {"ticker": "1303.TW", "name": "Nan Ya Plastics", "weight": 2.56},
        {"ticker": "2303.TW", "name": "United Micro", "weight": 2.42},
        {"ticker": "3711.TW", "name": "ASE Technology", "weight": 2.28},
    ],
    "EFA": [
        {"ticker": "NOVO-B.CO", "name": "Novo Nordisk", "weight": 2.85},
        {"ticker": "ASML", "name": "ASML Holding", "weight": 2.56},
        {"ticker": "NESN.SW", "name": "Nestle", "weight": 2.12},
        {"ticker": "AZN", "name": "AstraZeneca", "weight": 1.98},
        {"ticker": "SHEL", "name": "Shell", "weight": 1.85},
        {"ticker": "ROG.SW", "name": "Roche Holding", "weight": 1.72},
        {"ticker": "NOVN.SW", "name": "Novartis", "weight": 1.65},
        {"ticker": "SAP", "name": "SAP SE", "weight": 1.56},
        {"ticker": "TM", "name": "Toyota Motor", "weight": 1.42},
        {"ticker": "HSBA.L", "name": "HSBC Holdings", "weight": 1.38},
    ],
    "EEM": [
        {"ticker": "TSM", "name": "TSMC", "weight": 9.85},
        {"ticker": "TCEHY", "name": "Tencent Holdings", "weight": 4.56},
        {"ticker": "BABA", "name": "Alibaba Group", "weight": 3.42},
        {"ticker": "005930.KS", "name": "Samsung Electronics", "weight": 3.85},
        {"ticker": "RELIANCE.NS", "name": "Reliance Industries", "weight": 2.18},
        {"ticker": "PDD", "name": "PDD Holdings", "weight": 1.98},
        {"ticker": "3690.HK", "name": "Meituan", "weight": 1.72},
        {"ticker": "INFY", "name": "Infosys", "weight": 1.56},
        {"ticker": "VALE", "name": "Vale S.A.", "weight": 1.42},
        {"ticker": "2317.TW", "name": "Hon Hai Precision", "weight": 1.28},
    ],
    "EWG": [
        {"ticker": "SAP", "name": "SAP SE", "weight": 14.56},
        {"ticker": "SIE.DE", "name": "Siemens", "weight": 9.85},
        {"ticker": "ALV.DE", "name": "Allianz", "weight": 7.24},
        {"ticker": "DTE.DE", "name": "Deutsche Telekom", "weight": 6.42},
        {"ticker": "MUV2.DE", "name": "Munich Re", "weight": 4.85},
        {"ticker": "MBG.DE", "name": "Mercedes-Benz", "weight": 3.92},
        {"ticker": "IFX.DE", "name": "Infineon Technologies", "weight": 3.56},
        {"ticker": "AIR.PA", "name": "Airbus", "weight": 3.24},
        {"ticker": "BAS.DE", "name": "BASF", "weight": 2.98},
        {"ticker": "BMW.DE", "name": "BMW", "weight": 2.72},
    ],
    "EWY": [
        {"ticker": "005930.KS", "name": "Samsung Electronics", "weight": 22.56},
        {"ticker": "000660.KS", "name": "SK Hynix", "weight": 8.42},
        {"ticker": "373220.KS", "name": "LG Energy Solution", "weight": 4.85},
        {"ticker": "207940.KS", "name": "Samsung Biologics", "weight": 3.92},
        {"ticker": "005490.KS", "name": "POSCO Holdings", "weight": 3.56},
        {"ticker": "035420.KS", "name": "Naver Corp", "weight": 3.24},
        {"ticker": "006400.KS", "name": "Samsung SDI", "weight": 2.98},
        {"ticker": "051910.KS", "name": "LG Chem", "weight": 2.72},
        {"ticker": "035720.KS", "name": "Kakao Corp", "weight": 2.56},
        {"ticker": "068270.KS", "name": "Celltrion", "weight": 2.42},
    ],
}


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
    """Return all holdings for all ETFs."""
    result = {}
    for ticker, holdings in ETF_HOLDINGS.items():
        # Filter out empty placeholder rows
        filtered = [h for h in holdings if h["ticker"] != "-" and h["name"]]
        result[ticker] = filtered
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
    """Return all holdings for international ETFs."""
    result = {}
    for ticker, holdings in INTL_HOLDINGS.items():
        filtered = [h for h in holdings if h["ticker"] != "-" and h["name"]]
        result[ticker] = filtered
    return jsonify(result)


if __name__ == "__main__":
    print("Starting Sector ETF Dashboard on http://localhost:5051")
    app.run(debug=True, port=5051)
