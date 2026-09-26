from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Literal
import pandas as pd
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"), override=False)
DEMO_MODE = os.getenv("KAIROS_DEMO", "0").lower() in {"1", "true", "yes"}

from market_data import get_market_data, search_ticker
from analysis import find_best_match
from insights import build_asset_insights
from chat_engine import answer_financial_chat
from demo_data import demo_history, demo_insights, demo_search, demo_chat
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Kairos Research Dashboard")

# Allow CORS for frontend/dev hosts.
default_origins = "http://localhost:5173,http://localhost:8080"
raw_origins = os.getenv("ALLOWED_ORIGINS", default_origins).strip()
origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
allow_all = len(origins) == 1 and origins[0] == "*"
app.add_middleware(
    CORSMiddleware,
    allow_origins=(["*"] if allow_all else origins),
    allow_credentials=not allow_all,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
@app.get("/api/health")
def health_check():
    return {"status": "ok", "demo_mode": DEMO_MODE}

@app.get("/api/search")
def search_assets(q: str = Query(..., min_length=1, max_length=100)):
    """
    Proxy to Yahoo Finance Search API.
    Returns a list of matching tickers.
    """
    results = demo_search(q) if DEMO_MODE else search_ticker(q)
    return results


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=2000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    ticker: str | None = Field(default=None, max_length=30)
    history: list[ChatMessage] = Field(default_factory=list, max_length=8)


@app.post("/api/chat")
def financial_chat(req: ChatRequest):
    try:
        if DEMO_MODE:
            return demo_chat(req.message, (req.ticker or "DEMO").upper())
        history = [{"role": m.role, "content": m.content} for m in (req.history or [])]
        return answer_financial_chat(
            question=req.message,
            ticker=(req.ticker or "").strip().upper() or None,
            history=history,
        )
    except Exception as e:
        logger.error("Chat failed: %s", type(e).__name__)
        raise HTTPException(status_code=500, detail="Chat failed")

@app.get("/api/analyze/{ticker}")
def analyze_stock(
    ticker: str,
    period: str = "3mo",
    dcf_profile: str = Query("base"),
):
    """
    Analyzes the given ticker.
    1. Fetches full historical data.
    2. Builds strict business-day windows.
    3. Finds the best historical match.
    """
    ticker = ticker.upper()
    try:
        # Kept only for backward compatibility with existing frontend query params.
        _ = period

        def _direction(values):
            if values is None or len(values) < 2:
                return "flat"
            delta = float(values[-1]) - float(values[0])
            if abs(delta) < 1e-12:
                return "flat"
            return "up" if delta > 0 else "down"

        # 1. Get full history
        if DEMO_MODE and ticker not in {"DEMO", "DEMO2"}:
            raise HTTPException(status_code=400, detail="Demo mode supports DEMO and DEMO2 only.")
        history_data = demo_history(ticker) if DEMO_MODE else get_market_data(ticker)
        if history_data.empty:
            raise HTTPException(status_code=404, detail="No historical data found")

        history_series = history_data['Close'] if 'Close' in history_data.columns else history_data.iloc[:, 0]
        history_series = history_series.dropna().sort_index()
        if isinstance(history_series.index, pd.DatetimeIndex):
            # Enforce business-day windows consistently (Mon-Fri only).
            history_business = history_series[history_series.index.dayofweek < 5]
        else:
            history_business = history_series
        if history_business.empty:
            raise HTTPException(status_code=404, detail="No usable historical business-day data found")

        # 2. Build strict windows and find best match.
        # Analog mode: strictly 90 business days.
        # Seasonal strict mode: strictly 60 business days with calendar anchoring.
        analog_window = 90
        seasonal_window = 60
        current_trend_slice_analog = history_business.tail(analog_window)
        current_trend_slice_seasonal = history_business.tail(seasonal_window)
        seasonal_tolerance_days = 0
        seasonal_tolerance_days_fallback = 1
        logger.info(
            "Using strict business-day windows for %s: analog=%s bars, seasonal=%s bars",
            ticker,
            len(current_trend_slice_analog),
            len(current_trend_slice_seasonal),
        )
        if len(current_trend_slice_analog) < analog_window:
            raise HTTPException(status_code=404, detail=f"Not enough history for {analog_window} business-day analog window")
        if len(current_trend_slice_seasonal) < seasonal_window:
            raise HTTPException(status_code=404, detail=f"Not enough history for {seasonal_window} business-day seasonal window")
        current_start_day = int(current_trend_slice_seasonal.index[0].dayofyear)
        current_end_day = int(current_trend_slice_seasonal.index[-1].dayofyear)

        # We can adjust prediction window logic if needed (e.g. 30 days or proportional to input period)
        # For now, fixed 60 days lookahead
        best_match_analog = find_best_match(
            history_business,
            current_trend_slice_analog,
            prediction_window=60,
        )
        best_match_seasonal = find_best_match(
            history_business,
            current_trend_slice_seasonal,
            prediction_window=60,
            seasonal_anchor_start_day=None,
            seasonal_anchor_day=current_end_day,
            seasonal_tolerance_days=seasonal_tolerance_days,
        )
        if not best_match_seasonal:
            best_match_seasonal = find_best_match(
                history_business,
                current_trend_slice_seasonal,
                prediction_window=60,
                seasonal_anchor_start_day=None,
                seasonal_anchor_day=current_end_day,
                seasonal_tolerance_days=seasonal_tolerance_days_fallback,
            )
            if best_match_seasonal:
                seasonal_tolerance_days = seasonal_tolerance_days_fallback
        best_match = best_match_analog or best_match_seasonal
        dcf_profile = (dcf_profile or "base").strip().lower()
        if dcf_profile not in {"conservative", "base", "aggressive"}:
            dcf_profile = "base"

        insights = demo_insights(history_data, dcf_profile) if DEMO_MODE else build_asset_insights(ticker, history_data, dcf_profile=dcf_profile)

        if not best_match:
            raise HTTPException(status_code=404, detail="Could not find a valid seasonality correlation match")

        current_direction = _direction(current_trend_slice_analog.values.tolist())
        analog_direction = _direction(best_match_analog.get("match_data") if best_match_analog else None)
        seasonal_direction = _direction(best_match_seasonal.get("match_data") if best_match_seasonal else None)
        same_year = (
            bool(best_match_analog)
            and bool(best_match_seasonal)
            and int(best_match_analog.get("match_year")) == int(best_match_seasonal.get("match_year"))
        )
        same_direction = (
            bool(best_match_analog)
            and bool(best_match_seasonal)
            and analog_direction == seasonal_direction
        )
        same_as_current = (
            bool(best_match_analog)
            and bool(best_match_seasonal)
            and analog_direction == current_direction
            and seasonal_direction == current_direction
        )
        if best_match_analog and best_match_seasonal:
            if same_year and same_direction and same_as_current:
                confluence_level = "high"
            elif same_year or same_direction:
                confluence_level = "medium"
            else:
                confluence_level = "low"
        else:
            confluence_level = "n/a"
        return {
            "ticker": ticker,
            "demo_mode": DEMO_MODE,
            "data_source": "Synthetic demo fixture" if DEMO_MODE else "Yahoo Finance via yfinance",
            "asset": {"symbol": ticker, "name": "Synthetic Research Asset" if DEMO_MODE else ticker},
            "seasonality": {
                "current_trend": {
                    "dates": [str(d.date()) for d in current_trend_slice_analog.index],
                    "prices": current_trend_slice_analog.values.tolist()
                },
                "current_trend_analog": {
                    "dates": [str(d.date()) for d in current_trend_slice_analog.index],
                    "prices": current_trend_slice_analog.values.tolist()
                },
                "current_trend_seasonal": {
                    "dates": [str(d.date()) for d in current_trend_slice_seasonal.index],
                    "prices": current_trend_slice_seasonal.values.tolist()
                },
                "best_match": best_match,
                "best_match_analog": best_match_analog,
                "best_match_seasonal": best_match_seasonal,
                "confluence": {
                    "level": confluence_level,
                    "same_year": bool(same_year),
                    "same_direction": bool(same_direction),
                    "same_as_current_direction": bool(same_as_current),
                    "current_direction": current_direction,
                    "analog_direction": analog_direction,
                    "seasonal_direction": seasonal_direction,
                    "seasonal_anchor_start_day": None,
                    "seasonal_anchor_day": int(current_end_day),
                    "seasonal_tolerance_days": int(seasonal_tolerance_days),
                },
            },
            "insights": insights,
            # Backward compatibility for existing frontend clients.
            "current_trend": {
                "dates": [str(d.date()) for d in current_trend_slice_analog.index],
                "prices": current_trend_slice_analog.values.tolist()
            },
            "best_match": best_match,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Analysis failed: %s", type(e).__name__)
        raise HTTPException(status_code=500, detail="Analysis failed; check provider availability and input.")
