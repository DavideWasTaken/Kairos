import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def calculate_pearson_correlation(x, y) -> float:
    """
    Pearson correlation on two equally-sized windows.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    if len(x) != len(y) or len(x) < 2:
        return 0.0
    if np.std(x) < 1e-12 or np.std(y) < 1e-12:
        return 0.0

    corr = np.corrcoef(x, y)[0, 1]
    if not np.isfinite(corr):
        return 0.0
    return float(np.clip(corr, -1.0, 1.0))


def _cyclical_day_distance(day_a: int, day_b: int) -> int:
    """
    Distance between two day-of-year values on a circular 366-day calendar.
    """
    diff = abs(int(day_a) - int(day_b))
    return min(diff, 366 - diff)


def find_best_match(
    full_history: pd.DataFrame,
    current_trend: pd.Series,
    prediction_window: int = 30,
    seasonal_anchor_day: int | None = None,
    seasonal_anchor_start_day: int | None = None,
    seasonal_tolerance_days: int | None = None,
):
    """
    Forecaster-like analog search:
    - Pearson correlation
    - Rolling windows on historical data
    - Window size = len(current_trend) (typically 60 business days)
    - Optional calendar filter for strict seasonality matching
    """
    if isinstance(full_history, pd.DataFrame):
        ts = full_history["Close"] if "Close" in full_history.columns else full_history.iloc[:, 0]
    else:
        ts = full_history

    if isinstance(current_trend, pd.DataFrame):
        current_trend = current_trend["Close"] if "Close" in current_trend.columns else current_trend.iloc[:, 0]

    ts = pd.Series(ts).dropna().sort_index()
    current_trend = pd.Series(current_trend).dropna().sort_index()

    window_size = len(current_trend)
    if window_size < 20 or len(ts) < (2 * window_size + prediction_window):
        return None

    # Current trend is the last N bars (N=60 in main.py). We search only before it.
    current_start_idx = len(ts) - window_size
    search_start_end_idx = window_size - 1
    search_end_end_idx = current_start_idx - prediction_window - 1

    if search_end_end_idx < search_start_end_idx:
        return None

    current_values = current_trend.values
    best_corr = -2.0
    best_match = None
    logger.info(
        "Scanning rolling %s-bar historical windows with Pearson correlation (end_idx=%s..%s, seasonal_start_day=%s, seasonal_end_day=%s, tolerance=%s)",
        window_size,
        search_start_end_idx,
        search_end_end_idx,
        seasonal_anchor_start_day,
        seasonal_anchor_day,
        seasonal_tolerance_days,
    )

    for end_idx in range(search_start_end_idx, search_end_end_idx + 1):
        start_idx = end_idx - window_size + 1
        if seasonal_tolerance_days is not None:
            tolerance = int(seasonal_tolerance_days)
            if seasonal_anchor_day is not None:
                candidate_end_day = int(ts.index[end_idx].dayofyear)
                if _cyclical_day_distance(candidate_end_day, seasonal_anchor_day) > tolerance:
                    continue
            if seasonal_anchor_start_day is not None:
                candidate_start_day = int(ts.index[start_idx].dayofyear)
                if _cyclical_day_distance(candidate_start_day, seasonal_anchor_start_day) > tolerance:
                    continue

        window = ts.iloc[start_idx: end_idx + 1]
        if len(window) != window_size:
            continue

        corr = calculate_pearson_correlation(current_values, window.values)
        if corr > best_corr:
            best_corr = corr

            visual_year = int(window.index[-1].year)
            full_year_series = ts[ts.index.year == visual_year]
            if full_year_series.empty:
                full_year_series = window

            match_end_date = window.index[-1]
            match_end_indices = np.where(full_year_series.index == match_end_date)[0]
            if len(match_end_indices) > 0:
                match_start_idx = int(match_end_indices[0]) - window_size + 1
            else:
                match_start_idx = 0

            prediction = ts.iloc[end_idx + 1: end_idx + 1 + prediction_window]
            if len(prediction) < prediction_window:
                continue

            best_match = {
                "correlation": float(best_corr),
                "match_year": visual_year,
                "start_date": str(window.index[0].date()),
                "end_date": str(window.index[-1].date()),
                "match_data": window.values.tolist(),
                "full_year_data": full_year_series.values.tolist(),
                "full_year_dates": [str(d.date()) for d in full_year_series.index],
                "match_start_index": int(match_start_idx),
                "prediction_data": prediction.values.tolist(),
                "match_dates": [str(d.date()) for d in window.index],
                "prediction_dates": [str(d.date()) for d in prediction.index],
                "score_components": {
                    "method": "pearson_rolling_window",
                    "window_size": int(window_size),
                    "seasonal_anchor_start_day": int(seasonal_anchor_start_day) if seasonal_anchor_start_day is not None else None,
                    "seasonal_anchor_day": int(seasonal_anchor_day) if seasonal_anchor_day is not None else None,
                    "seasonal_tolerance_days": int(seasonal_tolerance_days) if seasonal_tolerance_days is not None else None,
                },
            }

    return best_match
