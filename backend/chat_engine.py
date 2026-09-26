import logging
import math
import os
import re
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
import yfinance as yf
import ai_assistant
import snapshot_store
from snapshot_store import get_analysis_snapshot
from insights import RECENT_INSIDER_WINDOW_DAYS, get_insider_activity

logger = logging.getLogger(__name__)

_INDEX_ALIASES = {
    "nasdaq": "^IXIC",
    "nasdaq composite": "^IXIC",
    "nasdaq100": "^NDX",
    "nasdaq 100": "^NDX",
    "ndx": "^NDX",
    "sp500": "^GSPC",
    "s&p500": "^GSPC",
    "s&p 500": "^GSPC",
    "dow jones": "^DJI",
    "dow": "^DJI",
    "dji": "^DJI",
    "russell 2000": "^RUT",
    "bitcoin": "BTC-USD",
    "btc": "BTC-USD",
    "ethereum": "ETH-USD",
    "eth": "ETH-USD",
}

_YAHOO_SCREENER_URL = "https://query1.finance.yahoo.com/v1/finance/screener"
_MICRO_CAP_MIN = 50_000_000
_MICRO_CAP_MAX = 300_000_000
_SMALL_CAP_MIN = 300_000_000
_SMALL_CAP_MAX = 2_000_000_000
_MID_CAP_MIN = 2_000_000_000
_MID_CAP_MAX = 10_000_000_000

_CURATED_CAP_UNIVERSE = [
    {"symbol": "AAOI", "name": "Applied Optoelectronics", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "AEHR", "name": "Aehr Test Systems", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "ARQT", "name": "Arcutis Biotherapeutics", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "AVDL", "name": "Avadel Pharmaceuticals", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "BBAI", "name": "BigBear.ai", "exchange": "nyse", "segment": "small_cap"},
    {"symbol": "BLNK", "name": "Blink Charging", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "CDNA", "name": "CareDx", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "CHRS", "name": "Coherus BioSciences", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "CLOV", "name": "Clover Health", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "CRNC", "name": "Cerence", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "EOSE", "name": "Eos Energy Enterprises", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "EYPT", "name": "EyePoint Pharmaceuticals", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "FATE", "name": "Fate Therapeutics", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "GRWG", "name": "GrowGeneration", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "HNST", "name": "The Honest Company", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "LUNR", "name": "Intuitive Machines", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "MRVI", "name": "Maravai LifeSciences", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "MTTR", "name": "Matterport", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "MYGN", "name": "Myriad Genetics", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "NNDM", "name": "Nano Dimension", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "OUST", "name": "Ouster", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "RNA", "name": "Avidity Biosciences", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "RXRX", "name": "Recursion Pharmaceuticals", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "RYTM", "name": "Rhythm Pharmaceuticals", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "SDGR", "name": "Schrodinger", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "SHLS", "name": "Shoals Technologies Group", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "SLNO", "name": "Soleno Therapeutics", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "VCEL", "name": "Vericel", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "YMAB", "name": "Y-mAbs Therapeutics", "exchange": "nasdaq", "segment": "small_cap"},
    {"symbol": "CDE", "name": "Coeur Mining", "exchange": "nyse", "segment": "small_cap"},
    {"symbol": "GEO", "name": "The GEO Group", "exchange": "nyse", "segment": "small_cap"},
    {"symbol": "HAYW", "name": "Hayward Holdings", "exchange": "nyse", "segment": "small_cap"},
    {"symbol": "PUMP", "name": "ProPetro Holding", "exchange": "nyse", "segment": "small_cap"},
    {"symbol": "TALO", "name": "Talos Energy", "exchange": "nyse", "segment": "small_cap"},
    {"symbol": "ACLS", "name": "Axcelis Technologies", "exchange": "nasdaq", "segment": "mid_cap"},
    {"symbol": "ADMA", "name": "ADMA Biologics", "exchange": "nasdaq", "segment": "mid_cap"},
    {"symbol": "ASTS", "name": "AST SpaceMobile", "exchange": "nasdaq", "segment": "mid_cap"},
    {"symbol": "BPMC", "name": "Blueprint Medicines", "exchange": "nasdaq", "segment": "mid_cap"},
    {"symbol": "EXPI", "name": "eXp World Holdings", "exchange": "nasdaq", "segment": "mid_cap"},
    {"symbol": "INMD", "name": "InMode", "exchange": "nasdaq", "segment": "mid_cap"},
    {"symbol": "IOVA", "name": "Iovance Biotherapeutics", "exchange": "nasdaq", "segment": "mid_cap"},
    {"symbol": "NVCR", "name": "NovoCure", "exchange": "nasdaq", "segment": "mid_cap"},
    {"symbol": "PRCT", "name": "PROCEPT BioRobotics", "exchange": "nasdaq", "segment": "mid_cap"},
    {"symbol": "TMDX", "name": "TransMedics Group", "exchange": "nasdaq", "segment": "mid_cap"},
    {"symbol": "UPST", "name": "Upstart Holdings", "exchange": "nasdaq", "segment": "mid_cap"},
    {"symbol": "VST", "name": "Vistra", "exchange": "nyse", "segment": "mid_cap"},
    {"symbol": "RGTI", "name": "Rigetti Computing", "exchange": "nasdaq", "segment": "micro_cap"},
    {"symbol": "ONDS", "name": "Ondas Holdings", "exchange": "nasdaq", "segment": "micro_cap"},
    {"symbol": "OPTX", "name": "Syntec Optics", "exchange": "nasdaq", "segment": "micro_cap"},
    {"symbol": "AEMD", "name": "Aethlon Medical", "exchange": "nasdaq", "segment": "micro_cap"},
    {"symbol": "HWH", "name": "HWH International", "exchange": "nasdaq", "segment": "micro_cap"},
]


def _is_plausible_symbol(token: str | None) -> bool:
    t = (token or "").strip().upper()
    if not t:
        return False
    if t in _INDEX_ALIASES.values():
        return True
    if re.fullmatch(r"\^[A-Z0-9.\-]{1,10}", t):
        return True
    if re.fullmatch(r"[A-Z]{1,5}", t):
        return True
    if re.fullmatch(r"[A-Z0-9]{1,5}-[A-Z0-9]{1,5}", t):
        return True
    return False


def _extract_years_maybe(question: str) -> int | None:
    txt = (question or "").lower()
    patterns = [
        r"(\d{1,3})\s*(anni|anno|years?|yrs?|yr|y)\b",
        r"(\d{1,3})\s*-\s*year\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, txt)
        if m:
            try:
                years = int(m.group(1))
                return int(max(1, min(100, years)))
            except Exception:
                return None
    return None


def _extract_years(question: str, default_years: int = 30) -> int:
    years = _extract_years_maybe(question)
    return years if years is not None else default_years


def _extract_days_maybe(question: str) -> int | None:
    txt = (question or "").lower()
    patterns = [
        (r"\b(\d{1,4})\s*-?\s*(giorni|giorno|days?)\b", 1),
        (r"\b(\d{1,4})\s*-?\s*(settimane?|weeks?|wks?)\b", 7),
        (r"\b(\d{1,4})\s*-?\s*(mesi|mese|months?|mos?)\b", 30),
        (r"\b(\d{1,4})\s*-?\s*(anni|anno|years?|yrs?|y)\b", 365),
    ]
    for pattern, multiplier in patterns:
        m = re.search(pattern, txt)
        if m:
            try:
                days = int(m.group(1)) * multiplier
                return int(max(1, min(3650, days)))
            except Exception:
                return None
    return None


def _extract_symbol_from_question(question: str, fallback_ticker: str | None) -> str | None:
    txt = (question or "").strip().lower()
    alias_items = sorted(_INDEX_ALIASES.items(), key=lambda x: len(x[0]), reverse=True)
    for alias, symbol in alias_items:
        pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
        if re.search(pattern, txt):
            return symbol

    # explicit $TICKER form
    m = re.search(r"\$([a-zA-Z][a-zA-Z0-9\-.^=]{0,14})", question or "")
    if m:
        candidate = m.group(1).upper()
        if _is_plausible_symbol(candidate):
            return candidate

    # explicit "ticker XYZ" form (case-insensitive)
    m2 = re.search(r"\bticker\s*[:=]?\s*([A-Za-z][A-Za-z0-9\-.]{0,14})\b", question or "", flags=re.IGNORECASE)
    if m2:
        candidate = m2.group(1).upper()
        if _is_plausible_symbol(candidate):
            return candidate

    # loose ticker-like token: accept only already-uppercase tokens from original text
    for m3 in re.finditer(r"\b([A-Z]{1,5}(?:-USD)?)\b", question or ""):
        token = m3.group(1)
        if token not in {"CAGR", "ETF", "USD", "YOY"} and _is_plausible_symbol(token):
            return token

    if fallback_ticker:
        candidate = fallback_ticker.strip().upper()
        if _is_plausible_symbol(candidate):
            return candidate
    return None


def _normalize_symbol_candidate(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip()
    if not s:
        return None
    lowered = s.lower()
    if lowered in _INDEX_ALIASES:
        return _INDEX_ALIASES[lowered]
    if lowered.startswith("$"):
        s = lowered[1:]
    s_up = s.upper()
    return s_up if _is_plausible_symbol(s_up) else None


def _extract_symbols_from_question(question: str, fallback_ticker: str | None = None) -> list[str]:
    text = question or ""
    txt = text.lower()
    candidates: list[tuple[int, str]] = []
    used_spans: list[tuple[int, int]] = []

    alias_items = sorted(_INDEX_ALIASES.items(), key=lambda x: len(x[0]), reverse=True)
    for alias, symbol in alias_items:
        pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
        for match in re.finditer(pattern, txt):
            span = (match.start(), match.end())
            overlaps = any(not (span[1] <= s[0] or span[0] >= s[1]) for s in used_spans)
            if overlaps:
                continue
            used_spans.append(span)
            candidates.append((match.start(), symbol))

    for m in re.finditer(r"\$([a-zA-Z][a-zA-Z0-9\-.^=]{0,14})", text):
        candidate = m.group(1).upper()
        if _is_plausible_symbol(candidate):
            candidates.append((m.start(), candidate))

    for m in re.finditer(r"\bticker\s*[:=]?\s*([A-Za-z][A-Za-z0-9\-.]{0,14})\b", text, flags=re.IGNORECASE):
        candidate = m.group(1).upper()
        if _is_plausible_symbol(candidate):
            candidates.append((m.start(1), candidate))

    for m in re.finditer(r"\b([A-Z]{2,5}(?:-USD)?)\b", text):
        token = m.group(1)
        if token not in {"CAGR", "ETF", "USD", "YOY"} and _is_plausible_symbol(token):
            candidates.append((m.start(1), token))

    candidates.sort(key=lambda x: x[0])
    out: list[str] = []
    for _, symbol in candidates:
        if symbol not in out:
            out.append(symbol)

    if fallback_ticker:
        fb = fallback_ticker.strip().upper()
        if _is_plausible_symbol(fb) and fb not in out:
            out.append(fb)
    return out


def _is_return_question(question: str) -> bool:
    txt = (question or "").lower()
    keys = [
        "rendimento",
        "return",
        "performance",
        "cagr",
        "compound annual",
        "annualized",
        "annuo",
        "annuale",
        "average return",
        "mean return",
        "in media",
        "di media",
        "all'anno",
        "per year",
        "yearly",
        "ultimo",
        "ultimi",
    ]
    return any(k in txt for k in keys)


def _is_correlation_question(question: str) -> bool:
    txt = (question or "").lower()
    keys = [
        "correlation",
        "correlazione",
        "correlate",
        "correlato",
        "correlata",
        "corr ",
    ]
    return any(k in txt for k in keys)


def _is_insider_question(question: str) -> bool:
    txt = (question or "").lower()
    keys = [
        "insider",
        "inside buying",
        "inside buy",
        "inside purchases",
        "acquisti insider",
        "acquisti degli insider",
        "acquisti da parte di insider",
        "comprato dagli insider",
        "management buying",
    ]
    return any(k in txt for k in keys)


def _is_small_cap_question(question: str) -> bool:
    txt = (question or "").lower()
    keys = [
        "small cap",
        "small-cap",
        "smallcap",
        "micro cap",
        "micro-cap",
        "mid small cap",
        "bassa capitalizzazione",
        "piccola capitalizzazione",
        "piccole capitalizzazioni",
    ]
    return any(k in txt for k in keys)


def _extract_cap_segment(question: str) -> tuple[str, int, int] | None:
    txt = (question or "").lower()
    if any(k in txt for k in ["micro cap", "micro-cap", "microcap", "micro caps"]):
        return ("micro_cap", _MICRO_CAP_MIN, _MICRO_CAP_MAX)
    if any(k in txt for k in ["mid cap", "mid-cap", "midcap", "medium cap", "media capitalizzazione"]):
        return ("mid_cap", _MID_CAP_MIN, _MID_CAP_MAX)
    if _is_small_cap_question(question):
        return ("small_cap", _SMALL_CAP_MIN, _SMALL_CAP_MAX)
    return None


def _extract_exchange_filter(question: str) -> str | None:
    txt = (question or "").lower()
    if "nasdaq" in txt:
        return "nasdaq"
    if "nyse" in txt:
        return "nyse"
    if "amex" in txt or "nyse american" in txt:
        return "amex"
    return None


def _is_top_ranked_question(question: str) -> bool:
    txt = (question or "").lower()
    keys = [
        "top",
        "largest",
        "biggest",
        "most important",
        "most significant",
        "piu importanti",
        "più importanti",
        "migliori",
        "principali",
    ]
    return any(k in txt for k in keys)


def _is_follow_up_question(question: str) -> bool:
    txt = (question or "").strip().lower()
    if not txt:
        return False
    follow_up_keys = [
        "quindi",
        "in pratica",
        "quasi",
        "so ",
        "that means",
        "meaning",
        "is that",
        "correct",
        "giusto",
    ]
    has_short_question_shape = len(txt) <= 80 and ("?" in txt)
    return has_short_question_shape or any(k in txt for k in follow_up_keys)


def _infer_symbol_from_history(history: list[dict] | None) -> str | None:
    for msg in reversed(history or []):
        content = (msg.get("content") or "").strip()
        if not content:
            continue

        # assistant fallback/summary format: "Verified Yahoo data for ^IXIC (...)"
        m = re.search(r"\bfor\s+([A-Z^][A-Z0-9\-.^=]{0,14})\b", content)
        if m:
            return m.group(1).upper()

        candidate = _extract_symbol_from_question(content, None)
        if candidate:
            return candidate
    return None


def _infer_years_from_history(history: list[dict] | None) -> int | None:
    for msg in reversed(history or []):
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        years = _extract_years_maybe(content)
        if years is not None:
            return years
    return None


def _history_has_return_topic(history: list[dict] | None) -> bool:
    for msg in reversed(history or []):
        content = (msg.get("content") or "").strip()
        if _is_return_question(content):
            return True
    return False


def _extract_price_series(hist: pd.DataFrame) -> pd.Series:
    if hist is None or hist.empty:
        return pd.Series(dtype=float)

    if "Adj Close" in hist.columns:
        px = hist["Adj Close"]
    elif "Close" in hist.columns:
        px = hist["Close"]
    else:
        px = hist.iloc[:, 0]

    if isinstance(px, pd.DataFrame):
        px = px.iloc[:, 0]

    if not isinstance(px, pd.Series):
        px = pd.Series(px)

    px = px.dropna().astype(float)
    if isinstance(px.index, pd.DatetimeIndex):
        px.index = px.index.tz_localize(None)
    return px


def _download_yahoo_history(symbol: str, start_dt: datetime, end_dt: datetime) -> pd.Series:
    def extract_window(frame):
        prices = _extract_price_series(frame)
        if not isinstance(prices.index, pd.DatetimeIndex):
            return pd.Series(dtype=float)
        start = pd.Timestamp(start_dt).tz_localize(None).normalize()
        end = pd.Timestamp(end_dt).tz_localize(None).normalize()
        return prices[(prices.index >= start) & (prices.index < end)].sort_index()

    # Try direct download on explicit date window first.
    try:
        hist = yf.download(
            symbol,
            start=start_dt.strftime("%Y-%m-%d"),
            end=end_dt.strftime("%Y-%m-%d"),
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        px = extract_window(hist)
        if len(px) >= 3:
            return px
    except Exception as e:
        logger.warning("yf.download failed for %s: %s", symbol, type(e).__name__)

    # Fallback 1: ticker.history with period.
    try:
        years = max(1, int(((end_dt - start_dt).days / 365.25) + 2))
        t = yf.Ticker(symbol)
        hist2 = t.history(period=f"{years}y", interval="1d", auto_adjust=False)
        px2 = extract_window(hist2)
        if len(px2) >= 3:
            return px2
    except Exception as e:
        logger.warning("yf.Ticker.history period failed for %s: %s", symbol, type(e).__name__)

    # Fallback 2: full available history then trim.
    try:
        t = yf.Ticker(symbol)
        hist3 = t.history(period="max", interval="1d", auto_adjust=False)
        px3 = extract_window(hist3)
        if len(px3) >= 3:
            return px3
    except Exception as e:
        logger.warning("yf.Ticker.history max failed for %s: %s", symbol, type(e).__name__)

    return pd.Series(dtype=float)


def _compute_verified_return_stats(symbol: str, years: int) -> dict | None:
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=int(years * 365.25 + 7))
    try:
        px = _download_yahoo_history(symbol, start_dt, end_dt)

        if len(px) < 3:
            return None

        start_price = float(px.iloc[0])
        end_price = float(px.iloc[-1])
        if start_price <= 0 or end_price <= 0:
            return None

        elapsed_years = max(1e-6, (px.index[-1] - px.index[0]).days / 365.25)
        total_return = (end_price / start_price) - 1.0
        cagr = (end_price / start_price) ** (1.0 / elapsed_years) - 1.0

        yearly = px.resample("YE").last().pct_change().dropna()
        # A year-end-labelled sample after the last observation is only a partial year.
        yearly = yearly[yearly.index <= px.index[-1].normalize()]
        yearly_mean = float(yearly.mean()) if len(yearly) > 0 else None
        yearly_median = float(yearly.median()) if len(yearly) > 0 else None
        yearly_std = float(yearly.std()) if len(yearly) > 1 else None

        return {
            "metric": "historical_return_stats",
            "symbol": symbol,
            "period_requested_years": years,
            "period_actual": {
                "start_date": str(px.index[0].date()),
                "end_date": str(px.index[-1].date()),
                "years_observed": round(elapsed_years, 3),
                "trading_days": int(len(px)),
            },
            "data_source": "Yahoo Finance via yfinance (Adj Close if available, else Close)",
            "results": {
                "start_price": start_price,
                "end_price": end_price,
                "total_return_pct": total_return * 100.0,
                "cagr_pct": cagr * 100.0,
                "mean_calendar_year_return_pct": (yearly_mean * 100.0) if yearly_mean is not None else None,
                "median_calendar_year_return_pct": (yearly_median * 100.0) if yearly_median is not None else None,
                "annual_volatility_pct": (yearly_std * 100.0) if yearly_std is not None else None,
                "calendar_year_samples": int(len(yearly)),
            },
        }
    except Exception as e:
        logger.warning("Return stats computation failed for %s: %s", symbol, type(e).__name__)
        return None


def _compute_verified_correlation_stats(symbol_a: str, symbol_b: str, years: int) -> dict | None:
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=int(years * 365.25 + 7))
    try:
        px_a = _download_yahoo_history(symbol_a, start_dt, end_dt)
        px_b = _download_yahoo_history(symbol_b, start_dt, end_dt)
        if len(px_a) < 3 or len(px_b) < 3:
            return None

        ret_a = px_a.pct_change().dropna()
        ret_b = px_b.pct_change().dropna()
        if len(ret_a) < 3 or len(ret_b) < 3:
            return None

        aligned = pd.concat([ret_a.rename("a"), ret_b.rename("b")], axis=1, join="inner").dropna()
        if len(aligned) < 10:
            return None

        if not all(math.isfinite(float(value)) for value in aligned.to_numpy().flat):
            return None
        if (aligned.std() == 0).any():
            return None

        corr = float(aligned["a"].corr(aligned["b"]))
        if not math.isfinite(corr):
            return None
        overlap_start = aligned.index[0]
        overlap_end = aligned.index[-1]
        overlap_years = max(1e-6, (overlap_end - overlap_start).days / 365.25)

        return {
            "metric": "historical_correlation_stats",
            "symbol_a": symbol_a,
            "symbol_b": symbol_b,
            "period_requested_years": years,
            "period_actual": {
                "start_date": str(overlap_start.date()),
                "end_date": str(overlap_end.date()),
                "years_observed": round(overlap_years, 3),
                "overlap_trading_days": int(len(aligned)),
            },
            "data_source": "Yahoo Finance via yfinance (daily Adj Close if available, else Close)",
            "method": "Pearson correlation on overlapping daily returns",
            "results": {
                "correlation": corr,
                "correlation_pct": corr * 100.0,
            },
        }
    except Exception as e:
        logger.warning("Correlation stats computation failed for %s/%s: %s", symbol_a, symbol_b, type(e).__name__)
        return None


def _exchange_matches(exchange_value: str | None, target: str | None) -> bool:
    if not target:
        return True
    exchange = (exchange_value or "").strip().lower()
    if target == "nasdaq":
        return any(token in exchange for token in ["nasdaq", "nms", "ngm", "ncm"])
    if target == "nyse":
        return "nyse" in exchange and "american" not in exchange
    if target == "amex":
        return any(token in exchange for token in ["amex", "american"])
    return True


def _fallback_curated_universe(segment_name: str, exchange_filter: str | None = None, limit: int = 60) -> list[dict]:
    out = []
    for item in _CURATED_CAP_UNIVERSE:
        if item.get("segment") != segment_name:
            continue
        if not _exchange_matches(item.get("exchange"), exchange_filter):
            continue
        out.append(
            {
                "symbol": item["symbol"],
                "name": item["name"],
                "market_cap": None,
                "exchange": item.get("exchange"),
            }
        )
        if len(out) >= limit:
            break
    return out


def _fetch_us_equity_symbols(
    market_cap_min: int,
    market_cap_max: int,
    limit: int = 60,
    exchange_filter: str | None = None,
    segment_name: str | None = None,
) -> tuple[list[dict], str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Content-Type": "application/json",
    }
    payload = {
        "offset": 0,
        "size": int(max(10, min(250, limit))),
        "sortField": "intradaymarketcap",
        "sortType": "ASC",
        "quoteType": "EQUITY",
        "query": {
            "operator": "and",
            "operands": [
                {"operator": "eq", "operands": ["region", "us"]},
                {"operator": "gt", "operands": ["intradaymarketcap", int(market_cap_min)]},
                {"operator": "lt", "operands": ["intradaymarketcap", int(market_cap_max)]},
            ],
        },
    }

    try:
        resp = requests.post(_YAHOO_SCREENER_URL, headers=headers, json=payload, timeout=12)
        resp.raise_for_status()
        body = resp.json() or {}
        finance = body.get("finance") or {}
        result = (finance.get("result") or [{}])[0] or {}
        quotes = result.get("quotes") or []
        symbols = []
        for item in quotes:
            symbol = _normalize_symbol_candidate(item.get("symbol"))
            if not symbol:
                continue
            exchange = (
                item.get("exchange")
                or item.get("fullExchangeName")
                or item.get("exchangeDisplay")
                or ""
            )
            if not _exchange_matches(exchange, exchange_filter):
                continue
            market_cap = None
            mc = item.get("intradaymarketcap")
            if isinstance(mc, dict):
                market_cap = mc.get("raw")
            elif isinstance(mc, (int, float)):
                market_cap = mc
            symbols.append(
                {
                    "symbol": symbol,
                    "name": item.get("shortName") or item.get("longName") or symbol,
                    "market_cap": float(market_cap) if market_cap is not None else None,
                    "exchange": exchange or None,
                }
            )
        if symbols:
            return symbols, "yahoo_screener"
    except Exception as e:
        logger.warning("Yahoo cap-segment screener failed: %s", type(e).__name__)

    if segment_name:
        fallback = _fallback_curated_universe(segment_name, exchange_filter=exchange_filter, limit=limit)
        if fallback:
            logger.warning("Using curated fallback universe for %s (%s)", segment_name, exchange_filter or "all")
            return fallback, "curated_fallback"
    return [], "unavailable"


def _compute_cap_segment_insider_activity(question: str) -> dict | None:
    segment = _extract_cap_segment(question)
    if not _is_insider_question(question) or not segment:
        return None

    segment_name, market_cap_min, market_cap_max = segment
    exchange_filter = _extract_exchange_filter(question)
    window_days = _extract_days_maybe(question) or RECENT_INSIDER_WINDOW_DAYS
    window_conversion = "Lookbacks use days; a week is 7 days, a month 30 days and a year 365 days."
    limit = 5 if _is_top_ranked_question(question) else 8
    universe, universe_source = _fetch_us_equity_symbols(
        market_cap_min=market_cap_min,
        market_cap_max=market_cap_max,
        limit=80,
        exchange_filter=exchange_filter,
        segment_name=segment_name,
    )
    if not universe:
        return {
            "metric": "cap_segment_insider_activity_unavailable",
            "scope": f"us_{segment_name}s",
            "window_days": window_days,
            "window_conversion": window_conversion,
            "reason": "Neither Yahoo screener nor the fallback monitored universe returned a usable symbol list for this filter.",
        }

    ranked = []
    for item in universe:
        symbol = item.get("symbol")
        if not symbol:
            continue
        try:
            activity = get_insider_activity(symbol, max_items=8, window_days=window_days)
        except Exception as e:
            logger.warning("Insider activity scan failed for %s: %s", symbol, type(e).__name__)
            continue
        rows = activity.get("transactions") or []
        summary = activity.get("summary") or {}
        if not summary.get("purchase_count"):
            continue
        ranked.append(
            {
                "symbol": symbol,
                "name": item.get("name") or symbol,
                "market_cap": item.get("market_cap"),
                "exchange": item.get("exchange"),
                "purchase_count": summary.get("purchase_count"),
                "purchase_shares": summary.get("purchase_shares"),
                "purchase_value": summary.get("purchase_value"),
                "valued_purchase_count": summary.get("valued_purchase_count"),
                "latest_purchase_date": summary.get("latest_purchase_date"),
                "coverage_note": activity.get("note"),
                "transactions": rows[:3],
            }
        )

    if not ranked:
        return {
            "metric": "cap_segment_insider_activity",
            "scope": f"us_{segment_name}s",
            "window_days": window_days,
            "window_conversion": window_conversion,
            "definition": {
                "segment": segment_name,
                "market_cap_min": market_cap_min,
                "market_cap_max": market_cap_max,
                "region": "US",
                "exchange": exchange_filter,
            },
            "scan": {
                "universe_size": len(universe),
                "matches_with_recent_buys": 0,
            },
            "universe_source": universe_source,
            "results": [],
            "ranking_method": "Recent insider purchase value first, then purchase count, then shares bought.",
            "data_source": "Yahoo Finance insider transactions via yfinance, with Yahoo screener or curated monitored universe for symbol discovery",
        }

    ranked.sort(
        key=lambda row: (
            float(row.get("purchase_value") or -1.0),
            float(row.get("purchase_count") or 0.0),
            float(row.get("purchase_shares") or 0.0),
        ),
        reverse=True,
    )

    return {
        "metric": "cap_segment_insider_activity",
        "scope": f"us_{segment_name}s",
        "window_days": window_days,
        "window_conversion": window_conversion,
        "definition": {
            "segment": segment_name,
            "market_cap_min": market_cap_min,
            "market_cap_max": market_cap_max,
            "region": "US",
            "exchange": exchange_filter,
        },
        "scan": {
            "universe_size": len(universe),
            "matches_with_recent_buys": len(ranked),
        },
        "universe_source": universe_source,
        "results": ranked[:limit],
        "ranking_method": "Recent insider purchase value first, then purchase count, then shares bought.",
        "data_source": "Yahoo Finance insider transactions via yfinance, with Yahoo screener or curated monitored universe for symbol discovery",
    }


def _has_unsupported_historical_period(question: str) -> bool:
    # These are lookback units, not return sampling frequency (e.g. daily returns).
    amount = r'(?:\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|un|uno|una|due|tre|quattro|cinque|sei|sette|otto|nove|dieci|undici|dodici|last|past|previous|ultim[oaie]|scors[oaie])'
    unit = r'(?:days?|giorni|giorno|weeks?|wks?|settimane?|months?|mos?|mesi|mese)'
    return bool(re.search(r'\b' + amount + r'\s*-?\s*(?:calendar\s+)?' + unit + r'\b', question or '', re.IGNORECASE))


def _build_verified_facts(question: str, fallback_ticker: str | None, history: list[dict] | None = None) -> list[dict]:
    facts = []
    insider_scan = _compute_cap_segment_insider_activity(question)
    if insider_scan:
        facts.append(insider_scan)
        return facts

    is_follow_up = _is_follow_up_question(question)
    # Route facts deterministically. Optional model selection never changes numbers.
    is_return_query = _is_return_question(question) or (is_follow_up and _history_has_return_topic(history))
    is_correlation_query = _is_correlation_question(question)
    if (is_return_query or is_correlation_query) and _has_unsupported_historical_period(question):
        return [{"metric": "historical_period_unsupported",
                 "reason": "Return and correlation queries currently support whole years only. Please specify a period in whole years."}]
    symbol = _extract_symbol_from_question(question, None)
    if not symbol and is_follow_up:
        symbol = _infer_symbol_from_history(history)
    if not symbol and fallback_ticker:
        symbol = fallback_ticker.strip().upper()

    years = _extract_years_maybe(question)
    if years is None and is_follow_up:
        years = _infer_years_from_history(history)
    years = years if years is not None else 30

    if is_correlation_query:
        symbols = _extract_symbols_from_question(question, fallback_ticker)
        if len(symbols) >= 2:
            stats = _compute_verified_correlation_stats(symbols[0], symbols[1], years)
            if stats:
                facts.append(stats)
            else:
                facts.append(
                    {
                        "metric": "historical_correlation_stats_unavailable",
                        "symbol_a": symbols[0],
                        "symbol_b": symbols[1],
                        "period_requested_years": years,
                        "data_source": "Yahoo Finance via yfinance",
                        "reason": "No sufficient overlapping history returned by provider for this request.",
                    }
                )
        else:
            facts.append(
                {
                    "metric": "historical_correlation_symbols_missing",
                    "reason": "Need two assets or indices to compute correlation.",
                }
            )
    # Return metrics are secondary when the user explicitly asks for correlation.
    if is_return_query and not is_correlation_query:
        if symbol:
            stats = _compute_verified_return_stats(symbol, years)
            if stats:
                facts.append(stats)
            else:
                facts.append(
                    {
                        "metric": "historical_return_stats_unavailable",
                        "symbol": symbol,
                        "period_requested_years": years,
                        "data_source": "Yahoo Finance via yfinance",
                        "reason": "No sufficient price history returned by provider for this request.",
                    }
                )
    return facts


def _format_metric(value, precision: int = 2, suffix: str = "") -> str:
    if isinstance(value, (int, float)) and math.isfinite(value):
        return f"{value:.{precision}f}{suffix}"
    return "n/a"


def _fallback_verified_answer(question: str, facts: list[dict]) -> str:
    if not facts:
        return (
            "I cannot verify this yet from Yahoo data for the current request. "
            "Try asking with an explicit asset and timeframe, e.g. "
            "'Average S&P 500 return over the last 30 years'."
        )

    f = facts[0]
    if f.get("metric") == "asset_overview_unavailable":
        return f"Please analyze {f.get('symbol')} with the {f.get('dcf_profile')} DCF profile first, then ask again. The server snapshot is missing or expired."
    if f.get("metric") == "asset_overview":
        values = f.get('results', {})
        period = f.get('period_actual', {})
        return (
            f"Dashboard snapshot for {f.get('symbol')} ({f.get('dcf_profile')} DCF profile), captured {f.get('captured_at')}. "
            f"Price observation window: {period.get('start_date')} -> {period.get('end_date')}. "
            f"Current price {_format_metric(values.get('current_price'))}; "
            f"DCF value per share {_format_metric(values.get('dcf_intrinsic_value_per_share'))}; "
            f"RSI {_format_metric(values.get('rsi'), 1)}. "
            f"Source: {f.get('data_source')}. Missing fields: {', '.join(f.get('missing_data') or []) or 'none'}. "
            "DCF values are assumption-dependent estimates; missing values are not estimates."
        )
    if f.get("metric") == "historical_period_unsupported":
        return f["reason"]
    if f.get("metric") == "cap_segment_insider_activity_unavailable":
        return (
            "I recognized the request for recent insider buying in the requested U.S. cap segment, "
            "but Yahoo did not return a usable screening universe right now. Please retry in a moment."
        )
    if f.get("metric") == "cap_segment_insider_activity":
        results = f.get("results") or []
        window_days = f.get("window_days") or RECENT_INSIDER_WINDOW_DAYS
        scan = f.get("scan") or {}
        definition = f.get("definition") or {}
        universe_source = f.get("universe_source") or "unknown"
        segment_name = str(definition.get("segment") or "small_cap").replace("_", " ")
        exchange_filter = definition.get("exchange")
        exchange_txt = f" on {str(exchange_filter).upper()}" if exchange_filter else ""
        source_note = (
            " using Yahoo screener"
            if universe_source == "yahoo_screener"
            else " using a curated monitored universe because Yahoo screener was rate-limited"
            if universe_source == "curated_fallback"
            else ""
        )
        window_note = f" {f['window_conversion']}" if f.get("window_conversion") else ""
        if not results:
            return (
                f"I scanned {scan.get('universe_size') or 0} U.S. {segment_name}{exchange_txt} "
                f"(market cap roughly ${float(definition.get('market_cap_min') or 0)/1_000_000:.0f}M "
                f"to ${float(definition.get('market_cap_max') or 0)/1_000_000_000:.1f}B) "
                f"for the last {window_days} days{source_note} and found no recent insider buys in the current result set.{window_note}"
            )
        lines = []
        for idx, row in enumerate(results[:5], start=1):
            value = row.get("purchase_value")
            value_txt = f"${value:,.0f}" if isinstance(value, (int, float)) else "n/a"
            latest_date = row.get("latest_purchase_date") or "-"
            lines.append(
                f"{idx}. {row.get('symbol')} ({row.get('name')}) - "
                f"reported buys {value_txt}, {row.get('purchase_count') or 0} purchase records, latest {latest_date}."
            )
        joined = "\n".join(lines)
        return (
            f"Verified scan of U.S. {segment_name}{exchange_txt} for recent insider buying (last {window_days} days){source_note}. "
            f"Universe scanned: {scan.get('universe_size') or 0}, matches: {scan.get('matches_with_recent_buys') or 0}.\n"
            f"{joined}\nCounts include all matching provider rows; displayed transactions and purchase values may be incomplete.{window_note}"
        )

    if f.get("metric") == "historical_return_stats_unavailable":
        symbol = f.get("symbol") or "the requested asset"
        years = f.get("period_requested_years")
        return (
            f"I recognized the request for {symbol} over {years} years, "
            "but Yahoo did not return enough history right now. "
            "Please retry in a moment."
        )
    if f.get("metric") == "historical_correlation_symbols_missing":
        return (
            "I need two assets to compute a verified correlation. "
            "Example: 'What is the correlation between Nasdaq 100 and S&P 500 over 5 years?'"
        )
    if f.get("metric") == "historical_correlation_stats_unavailable":
        a = f.get("symbol_a") or "asset A"
        b = f.get("symbol_b") or "asset B"
        years = f.get("period_requested_years")
        return (
            f"I recognized the correlation request for {a} vs {b} over {years} years, "
            "but Yahoo did not return enough overlapping history right now. "
            "Please retry in a moment."
        )

    if f.get("metric") == "historical_correlation_stats":
        r = f.get("results", {})
        p = f.get("period_actual", {})
        a = f.get("symbol_a") or "-"
        b = f.get("symbol_b") or "-"
        return (
            f"Verified Yahoo data for {a} vs {b} ({p.get('start_date')} -> {p.get('end_date')}): "
            f"daily-return Pearson correlation {_format_metric(r.get('correlation'), 3)} "
            f"({_format_metric(r.get('correlation_pct'), 1, '%')})."
        )

    if f.get("metric") != "historical_return_stats":
        return "Verified data is available, but no formatter is defined for this metric yet."

    r = f.get("results", {})
    p = f.get("period_actual", {})
    symbol = f.get("symbol") or "-"
    return (
        f"Verified Yahoo data for {symbol} ({p.get('start_date')} -> {p.get('end_date')}): "
        f"CAGR {_format_metric(r.get('cagr_pct'), 2, '%')}, mean calendar-year return {_format_metric(r.get('mean_calendar_year_return_pct'), 2, '%')}, "
        f"total return {_format_metric(r.get('total_return_pct'), 2, '%')}."
    )


CLARIFICATIONS = {
    'missing_asset': 'Please specify an asset ticker to analyze.',
    'missing_period': 'Please specify the period in whole years.',
    'missing_pair': 'Please specify two assets for the correlation calculation.',
    'unsupported_period': 'Return and correlation queries currently support whole years only. Please specify a period in whole years.',
    'unsupported_request': 'Please ask for one operation: historical returns, correlation, an insider scan, a dashboard overview, or a general financial concept.',
}


def _validate_request_alignment(plan, question):
    """Protect explicit periods and recognizable symbols from an inconsistent plan."""
    operation = plan['operation']
    if operation in {'returns', 'correlation'}:
        if _has_unsupported_historical_period(question):
            raise ai_assistant.AIUnavailable('invalid_plan')
        years = _extract_years_maybe(question)
        if years is not None and years != plan['years']:
            raise ai_assistant.AIUnavailable('invalid_plan')
    if operation in {'returns', 'correlation', 'asset_overview'}:
        # Mask compound symbols before the legacy loose-token extractor can split them.
        compound_pattern = r'(?<![A-Za-z0-9])(?:\^[A-Z0-9.-]+|[A-Z0-9]+[.=-][A-Z0-9.-]+)(?![A-Za-z0-9])'
        compounds = [match.group() for match in re.finditer(compound_pattern, question)
                     if ai_assistant.valid_ticker(match.group())]
        simple_question = re.sub(compound_pattern, ' ', question)
        explicit = compounds + [symbol for symbol in _extract_symbols_from_question(simple_question)
                                if symbol not in {'DCF', 'RSI', 'EPS', 'FCF', 'WACC', 'GDP', 'PE', 'AI'}]
        planned = [plan['ticker_a'], plan['ticker_b']] if operation == 'correlation' else [plan['ticker']]
        if explicit and any(symbol not in planned for symbol in explicit):
            raise ai_assistant.AIUnavailable('invalid_plan')
    if operation == 'insider_scan':
        days = _extract_days_maybe(question)
        segment = _extract_cap_segment(question)
        exchange = _extract_exchange_filter(question)
        if ((days is not None and days != plan['days']) or
                (segment and segment[0] != plan['segment']) or
                (exchange and exchange != plan['exchange'])):
            raise ai_assistant.AIUnavailable('invalid_plan')


def _execute_plan(plan, profile):
    operation = plan['operation']
    if operation == 'returns':
        fact = _compute_verified_return_stats(plan['ticker'], plan['years'])
        return [fact or {'metric': 'historical_return_stats_unavailable', 'symbol': plan['ticker'],
                         'period_requested_years': plan['years'], 'data_source': 'Yahoo Finance via yfinance'}]
    if operation == 'correlation':
        fact = _compute_verified_correlation_stats(plan['ticker_a'], plan['ticker_b'], plan['years'])
        return [fact or {'metric': 'historical_correlation_stats_unavailable', 'symbol_a': plan['ticker_a'],
                         'symbol_b': plan['ticker_b'], 'period_requested_years': plan['years'], 'data_source': 'Yahoo Finance via yfinance'}]
    if operation == 'insider_scan':
        # Format only validated enums and a bounded integer for the existing deterministic scan.
        query = f"top {plan['segment'].replace('_', ' ')} insider purchases {plan['exchange'] or ''} last {plan['days']} days"
        return [_compute_cap_segment_insider_activity(query)]
    if operation == 'asset_overview':
        fact = get_analysis_snapshot(plan['ticker'], profile)
        return [fact or {'metric': 'asset_overview_unavailable', 'symbol': plan['ticker'], 'dcf_profile': profile}]
    return []


def _commentary_evidence(facts):
    """Remove provider prose and detailed rows from scan evidence before sending it."""
    projected = []
    for fact in facts:
        if fact.get('metric') == 'cap_segment_insider_activity':
            item = {key: fact[key] for key in ('id', 'metric', 'scope', 'window_days', 'window_conversion', 'definition', 'scan', 'universe_source', 'ranking_method', 'data_source') if key in fact}
            item['results'] = [{key: row.get(key) for key in ('symbol', 'market_cap', 'purchase_count', 'purchase_shares', 'purchase_value', 'valued_purchase_count', 'latest_purchase_date')} for row in (fact.get('results') or [])[:5]]
            projected.append(item)
        else:
            projected.append(fact)
    return projected


def answer_financial_chat(question: str, ticker: str | None = None, history: list[dict] | None = None,
                          dcf_profile: str = 'base') -> dict:
    user_q = (question or '').strip()[:4000]
    history = ai_assistant.bounded_history(history)
    demo = os.getenv('KAIROS_DEMO', '0').lower() in {'1', 'true', 'yes'}
    capability = ai_assistant.ai_capability(demo=demo)
    ai = {'status': capability['status'] if capability['status'] != 'configured' else 'unavailable',
          'code': None, 'planning_status': 'skipped', 'commentary_status': 'skipped'}
    result = {'answer': 'Please write a question.', 'explanation': None, 'explanation_kind': None,
              'verified_facts': [], 'model': None, 'used_llm': False, 'ai': ai, 'evidence_ids': []}
    if not user_q:
        return result
    if demo:
        from demo_data import demo_chat
        return demo_chat(user_q, ticker or 'DEMO')
    plan = None
    if capability['status'] == 'configured':
        try:
            plan = ai_assistant.validate_plan(ai_assistant.request_json(ai_assistant.PLAN_PROMPT,
                {'question': user_q, 'selected_ticker': ticker, 'dcf_profile': dcf_profile, 'history': history}))
            _validate_request_alignment(plan, user_q)
            ai.update(status='used', planning_status='used')
            result.update(used_llm=True, model=ai_assistant.configured_model())
        except ai_assistant.AIUnavailable as error:
            ai.update(status='unavailable', code=error.code, planning_status='unavailable')
            logger.warning('Optional AI planning unavailable (%s); deterministic answer retained.', error.code)
            plan = None
    facts = _execute_plan(plan, dcf_profile) if plan else _build_verified_facts(user_q, ticker, history=history)
    facts = [dict(fact, id=f'fact-{index}') for index, fact in enumerate(facts, 1) if fact]
    result['verified_facts'] = facts
    operation = plan['operation'] if plan else None
    if operation == 'clarify':
        result['answer'] = CLARIFICATIONS[plan['reason']]
    elif operation == 'concept':
        result['answer'] = 'General concept explanation; no asset-specific numerical facts were requested or verified.'
    else:
        result['answer'] = _fallback_verified_answer(user_q, facts)
    # No second attempt after a failed plan, clarification, or missing data.
    has_evidence = bool(facts) and facts[0].get('metric') in {
        'historical_return_stats', 'historical_correlation_stats', 'cap_segment_insider_activity', 'asset_overview'}
    if plan and (has_evidence or operation == 'concept'):
        try:
            commentary = ai_assistant.request_json(ai_assistant.COMMENTARY_PROMPT,
                {'question': user_q, 'history': history, 'operation': operation, 'facts': _commentary_evidence(facts)})
            explanation, refs = ai_assistant.validate_commentary(commentary, facts)
            result.update(explanation=explanation, evidence_ids=refs,
                          explanation_kind='Unverified AI-generated interpretation')
            ai['commentary_status'] = 'used'
        except ai_assistant.AIUnavailable as error:
            ai.update(status='partial', code=error.code, commentary_status='unavailable')
            logger.warning('Optional AI commentary unavailable (%s); computed answer retained.', error.code)
    return result
