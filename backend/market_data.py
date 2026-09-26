import yfinance as yf
import pandas as pd
import requests
import logging
from functools import lru_cache
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_FALLBACK_ASSETS = [
    {"symbol": "AAPL", "name": "Apple Inc.", "type": "Equity", "exchange": "NASDAQ"},
    {"symbol": "APP", "name": "AppLovin Corporation", "type": "Equity", "exchange": "NASDAQ"},
    {"symbol": "MSFT", "name": "Microsoft Corporation", "type": "Equity", "exchange": "NASDAQ"},
    {"symbol": "NVDA", "name": "NVIDIA Corporation", "type": "Equity", "exchange": "NASDAQ"},
    {"symbol": "AMZN", "name": "Amazon.com, Inc.", "type": "Equity", "exchange": "NASDAQ"},
    {"symbol": "GOOGL", "name": "Alphabet Inc. (Class A)", "type": "Equity", "exchange": "NASDAQ"},
    {"symbol": "GOOG", "name": "Alphabet Inc. (Class C)", "type": "Equity", "exchange": "NASDAQ"},
    {"symbol": "META", "name": "Meta Platforms, Inc.", "type": "Equity", "exchange": "NASDAQ"},
    {"symbol": "TSLA", "name": "Tesla, Inc.", "type": "Equity", "exchange": "NASDAQ"},
    {"symbol": "NFLX", "name": "Netflix, Inc.", "type": "Equity", "exchange": "NASDAQ"},
    {"symbol": "AMD", "name": "Advanced Micro Devices, Inc.", "type": "Equity", "exchange": "NASDAQ"},
    {"symbol": "INTC", "name": "Intel Corporation", "type": "Equity", "exchange": "NASDAQ"},
    {"symbol": "QCOM", "name": "QUALCOMM Incorporated", "type": "Equity", "exchange": "NASDAQ"},
    {"symbol": "AVGO", "name": "Broadcom Inc.", "type": "Equity", "exchange": "NASDAQ"},
    {"symbol": "ORCL", "name": "Oracle Corporation", "type": "Equity", "exchange": "NYSE"},
    {"symbol": "ADBE", "name": "Adobe Inc.", "type": "Equity", "exchange": "NASDAQ"},
    {"symbol": "CRM", "name": "Salesforce, Inc.", "type": "Equity", "exchange": "NYSE"},
    {"symbol": "PYPL", "name": "PayPal Holdings, Inc.", "type": "Equity", "exchange": "NASDAQ"},
    {"symbol": "SHOP", "name": "Shopify Inc.", "type": "Equity", "exchange": "NYSE"},
    {"symbol": "UBER", "name": "Uber Technologies, Inc.", "type": "Equity", "exchange": "NYSE"},
    {"symbol": "ABNB", "name": "Airbnb, Inc.", "type": "Equity", "exchange": "NASDAQ"},
    {"symbol": "PLTR", "name": "Palantir Technologies Inc.", "type": "Equity", "exchange": "NASDAQ"},
    {"symbol": "SNOW", "name": "Snowflake Inc.", "type": "Equity", "exchange": "NYSE"},
    {"symbol": "ARM", "name": "Arm Holdings plc", "type": "Equity", "exchange": "NASDAQ"},
    {"symbol": "JPM", "name": "JPMorgan Chase & Co.", "type": "Equity", "exchange": "NYSE"},
    {"symbol": "BAC", "name": "Bank of America Corporation", "type": "Equity", "exchange": "NYSE"},
    {"symbol": "GS", "name": "The Goldman Sachs Group, Inc.", "type": "Equity", "exchange": "NYSE"},
    {"symbol": "MS", "name": "Morgan Stanley", "type": "Equity", "exchange": "NYSE"},
    {"symbol": "V", "name": "Visa Inc.", "type": "Equity", "exchange": "NYSE"},
    {"symbol": "MA", "name": "Mastercard Incorporated", "type": "Equity", "exchange": "NYSE"},
    {"symbol": "BRK-B", "name": "Berkshire Hathaway Inc. Class B", "type": "Equity", "exchange": "NYSE"},
    {"symbol": "WMT", "name": "Walmart Inc.", "type": "Equity", "exchange": "NYSE"},
    {"symbol": "COST", "name": "Costco Wholesale Corporation", "type": "Equity", "exchange": "NASDAQ"},
    {"symbol": "DIS", "name": "The Walt Disney Company", "type": "Equity", "exchange": "NYSE"},
    {"symbol": "NKE", "name": "NIKE, Inc.", "type": "Equity", "exchange": "NYSE"},
    {"symbol": "MCD", "name": "McDonald's Corporation", "type": "Equity", "exchange": "NYSE"},
    {"symbol": "SBUX", "name": "Starbucks Corporation", "type": "Equity", "exchange": "NASDAQ"},
    {"symbol": "PEP", "name": "PepsiCo, Inc.", "type": "Equity", "exchange": "NASDAQ"},
    {"symbol": "KO", "name": "The Coca-Cola Company", "type": "Equity", "exchange": "NYSE"},
    {"symbol": "UNH", "name": "UnitedHealth Group Incorporated", "type": "Equity", "exchange": "NYSE"},
    {"symbol": "JNJ", "name": "Johnson & Johnson", "type": "Equity", "exchange": "NYSE"},
    {"symbol": "LLY", "name": "Eli Lilly and Company", "type": "Equity", "exchange": "NYSE"},
    {"symbol": "PFE", "name": "Pfizer Inc.", "type": "Equity", "exchange": "NYSE"},
    {"symbol": "MRK", "name": "Merck & Co., Inc.", "type": "Equity", "exchange": "NYSE"},
    {"symbol": "XOM", "name": "Exxon Mobil Corporation", "type": "Equity", "exchange": "NYSE"},
    {"symbol": "CVX", "name": "Chevron Corporation", "type": "Equity", "exchange": "NYSE"},
    {"symbol": "CAT", "name": "Caterpillar Inc.", "type": "Equity", "exchange": "NYSE"},
    {"symbol": "BA", "name": "The Boeing Company", "type": "Equity", "exchange": "NYSE"},
    {"symbol": "GE", "name": "GE Aerospace", "type": "Equity", "exchange": "NYSE"},
    {"symbol": "SPY", "name": "SPDR S&P 500 ETF Trust", "type": "ETF", "exchange": "NYSEARCA"},
    {"symbol": "QQQ", "name": "Invesco QQQ Trust", "type": "ETF", "exchange": "NASDAQ"},
    {"symbol": "IWM", "name": "iShares Russell 2000 ETF", "type": "ETF", "exchange": "NYSEARCA"},
    {"symbol": "DIA", "name": "SPDR Dow Jones Industrial Average ETF", "type": "ETF", "exchange": "NYSEARCA"},
    {"symbol": "VTI", "name": "Vanguard Total Stock Market ETF", "type": "ETF", "exchange": "NYSEARCA"},
    {"symbol": "VOO", "name": "Vanguard S&P 500 ETF", "type": "ETF", "exchange": "NYSEARCA"},
    {"symbol": "TLT", "name": "iShares 20+ Year Treasury Bond ETF", "type": "ETF", "exchange": "NASDAQ"},
    {"symbol": "GLD", "name": "SPDR Gold Shares", "type": "ETF", "exchange": "NYSEARCA"},
    {"symbol": "SLV", "name": "iShares Silver Trust", "type": "ETF", "exchange": "NYSEARCA"},
    {"symbol": "BTC-USD", "name": "Bitcoin USD", "type": "Crypto", "exchange": "CCC"},
    {"symbol": "ETH-USD", "name": "Ethereum USD", "type": "Crypto", "exchange": "CCC"},
    {"symbol": "SOL-USD", "name": "Solana USD", "type": "Crypto", "exchange": "CCC"},
    {"symbol": "XRP-USD", "name": "XRP USD", "type": "Crypto", "exchange": "CCC"},
    {"symbol": "DOGE-USD", "name": "Dogecoin USD", "type": "Crypto", "exchange": "CCC"},
    {"symbol": "^GSPC", "name": "S&P 500 Index", "type": "Index", "exchange": "SNP"},
    {"symbol": "^IXIC", "name": "NASDAQ Composite", "type": "Index", "exchange": "NASDAQ"},
    {"symbol": "^DJI", "name": "Dow Jones Industrial Average", "type": "Index", "exchange": "DJI"},
]


def _score_fallback_asset(query: str, asset: dict):
    q = query.lower()
    symbol = asset["symbol"].lower()
    name = asset["name"].lower()
    if q == symbol:
        return 0
    if symbol.startswith(q):
        return 1
    if q in symbol:
        return 2
    if q == name:
        return 3
    if name.startswith(q):
        return 4
    if q in name:
        return 5
    return None


def _local_suggestions(query: str, limit: int = 10):
    ranked = []
    for asset in _FALLBACK_ASSETS:
        score = _score_fallback_asset(query, asset)
        if score is None:
            continue
        ranked.append((score, len(asset["symbol"]), asset["symbol"], asset))
    ranked.sort(key=lambda row: (row[0], row[1], row[2]))
    return [row[3] for row in ranked[:limit]]


def _merge_suggestions(primary, secondary, limit: int = 10):
    merged = []
    seen = set()
    for candidate in list(primary) + list(secondary):
        symbol = (candidate.get("symbol") or "").upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        merged.append(candidate)
        if len(merged) >= limit:
            break
    return merged


def _extract_domain(website: str | None):
    if not website:
        return None
    try:
        parsed = urlparse(website if "://" in website else f"https://{website}")
        host = (parsed.netloc or "").strip().lower()
        if host.startswith("www."):
            host = host[4:]
        return host or None
    except Exception:
        return None


@lru_cache(maxsize=300)
def get_asset_profile(ticker: str):
    symbol = (ticker or "").strip().upper()
    if not symbol:
        return {
            "symbol": "",
            "name": "",
            "logo_url": None,
            "exchange": None,
            "type": None,
            "currency": None,
            "website": None,
        }
    out = {
        "symbol": symbol,
        "name": symbol,
        "logo_url": None,
        "exchange": None,
        "type": None,
        "currency": None,
        "website": None,
    }
    try:
        tk = yf.Ticker(symbol)
        info = tk.info or {}
        out["name"] = info.get("longName") or info.get("shortName") or symbol
        out["exchange"] = info.get("exchange") or info.get("fullExchangeName")
        out["type"] = info.get("quoteType")
        out["currency"] = info.get("currency") or info.get("financialCurrency")
        out["website"] = info.get("website")

        logo = info.get("logo_url") or info.get("logoUrl")
        if not logo:
            domain = _extract_domain(out["website"])
            if domain:
                logo = f"https://logo.clearbit.com/{domain}"
        out["logo_url"] = logo
        return out
    except Exception as e:
        logger.warning("Asset profile fetch failed for %s: %s", symbol, type(e).__name__)
        return out

def _single_ticker_ohlcv(data: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Select the requested ticker, preserving price fields in either Yahoo layout."""
    if isinstance(data.columns, pd.MultiIndex):
        symbol = ticker.strip().upper()
        for level in range(data.columns.nlevels):
            matches = [value for value in data.columns.get_level_values(level).unique()
                       if str(value).upper() == symbol]
            if matches:
                data = data.xs(matches[0], axis=1, level=level).copy()
                data.columns.name = None
                break
        else:
            return pd.DataFrame()
    if "Close" not in data.columns:
        return pd.DataFrame()
    return data.dropna(subset=["Close"])


def get_market_data(ticker: str) -> pd.DataFrame:
    """
    Fetches the full historical daily data for the given ticker.
    Returns a DataFrame with the 'Close' prices.
    """
    try:
        logger.info(f"Fetching data for {ticker}...")
        # Fetch data with max history
        data = yf.download(ticker, period="max", interval="1d", progress=False)

        if data.empty:
            logger.warning(f"No data found for {ticker}")
            return pd.DataFrame()

        data = _single_ticker_ohlcv(data, ticker)

        logger.info(f"Fetched {len(data)} data points for {ticker}")
        return data

    except Exception as e:
        logger.error(f"Error fetching data for {ticker}: {type(e).__name__}")
        return pd.DataFrame()

def get_current_trend(ticker: str, period: str = "3mo") -> pd.DataFrame:
    """
    Fetches the recent data to represent the 'current trend'.
    Default is 3 months.
    """
    try:
        logger.info(f"Fetching current trend for {ticker} (period={period})...")
        data = yf.download(ticker, period=period, interval="1d", progress=False)
        return _single_ticker_ohlcv(data, ticker)
    except Exception as e:
        logger.error(f"Error fetching current trend: {type(e).__name__}")
        return pd.DataFrame()

@lru_cache(maxsize=100)
def search_ticker(query: str):
    """
    Searches for tickers using Yahoo Finance API.
    Cached to prevent rate limiting on repeated keystrokes.
    """
    normalized_query = (query or "").strip()
    if not normalized_query:
        return []

    # ... (url and headers same as before) ...
    url = "https://query2.finance.yahoo.com/v1/finance/search"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    params = {
        'q': normalized_query,
        'quotesCount': 20,
        'newsCount': 0
    }
    fallback = _local_suggestions(normalized_query, limit=10)
    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()

        quotes = data.get('quotes', [])
        results = []
        for q in quotes:
            if 'symbol' in q:
                results.append({
                    "symbol": q['symbol'],
                    "name": q.get('longname') or q.get('shortname') or q['symbol'],
                    "type": q.get('quoteType', 'Unknown'),
                    "exchange": q.get('exchange', '')
                })
        return _merge_suggestions(results, fallback, limit=10)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
             logger.warning(f"Rate limit hit for query '{normalized_query}': {type(e).__name__}")
             return fallback
        logger.error(f"HTTP Error searching for {normalized_query}: {type(e).__name__}")
        return fallback
    except Exception as e:
        logger.error(f"Error searching for {normalized_query}: {type(e).__name__}")
        return fallback
