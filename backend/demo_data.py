"""Deterministic synthetic market series. No provider calls or real company data."""
import numpy as np
import pandas as pd

from insights import compute_overbought_oversold, compute_wyckoff_causes_effects

SOURCE = "Synthetic demo fixture (deterministic seed; not market data)"
SYMBOLS = ("DEMO", "DEMO2")


def demo_search(query):
    return [{"symbol": symbol, "name": f"Synthetic Research Asset {i + 1}",
             "exchange": "DEMO", "type": "Synthetic", "currency": "USD"}
            for i, symbol in enumerate(SYMBOLS)
            if query.lower() in symbol.lower() or query.lower() in "synthetic research asset"]


def demo_history(symbol):
    if symbol not in SYMBOLS:
        raise ValueError("Demo mode supports DEMO and DEMO2 only.")
    rng = np.random.default_rng(42 if symbol == "DEMO" else 84)
    dates = pd.bdate_range("2018-01-02", periods=1800)
    t = np.arange(len(dates))
    changes = 0.00035 + 0.0015 * np.sin(t / 35) + rng.normal(0, 0.007, len(t))
    close = 100 * np.exp(np.cumsum(changes))
    opening = close * (1 + rng.normal(0, 0.002, len(t)))
    return pd.DataFrame({"Open": opening, "High": np.maximum(opening, close) * 1.004,
                         "Low": np.minimum(opening, close) * 0.996, "Close": close,
                         "Volume": rng.integers(500_000, 3_000_000, len(t))}, index=dates)


def demo_insights(history, profile="base"):
    return {
        "fundamental": {"has_data": False, "dcf_profile": profile,
                        "annual_trend": [], "quarterly_trend": [],
                        "discounted_cash_flow": {}, "valuation_summary": {},
                        "data_quality": {"score": None, "flags": ["Synthetic prices only; fundamentals unavailable."]}},
        "wyckoff": compute_wyckoff_causes_effects(history),
        "overbought_oversold": compute_overbought_oversold(history),
        "insider_activity": {"has_data": False, "transactions": [],
                             "note": "Insider records are unavailable in synthetic demo mode."},
        "news": [], "social_sentiment": {"has_data": False},
        "price_history": {"dates": [str(d.date()) for d in history.index],
                          "prices": history.Close.tolist()},
        "model_confidence": {"score": None, "label": "unavailable", "breakdown": {},
                             "methodology": {"name": "Heuristic composite", "calibrated_probability": False,
                                             "missing_data_policy": "Not computed for synthetic demo data."}},
        "quick_verdict": {"label": "unavailable", "score": None,
                          "summary": "Explore the synthetic dataset",
                          "reasons": ["Prices and volumes are generated locally with a fixed seed.",
                                      "Technical indicators and historical matches use the normal calculation engine.",
                                      "Fundamentals, news and insider records are unavailable in this demo."]},
    }


def demo_chat(question, symbol="DEMO"):
    result = {"answer": "", "explanation": None, "verified_facts": [],
              "used_llm": False, "model": None, "demo_mode": True, "evidence_ids": [],
              "ai": {"status": "demo", "code": None, "planning_status": "skipped", "commentary_status": "skipped"}}
    if any(word in question.lower() for word in ("insider", "news", "dcf", "fundamental")):
        result["answer"] = "These data are unavailable in the synthetic demo. Try return statistics or correlation."
        return result
    symbol = symbol if symbol in SYMBOLS else "DEMO"
    prices = demo_history(symbol).Close
    years = (prices.index[-1] - prices.index[0]).days / 365.25
    period = {"start_date": str(prices.index[0].date()), "end_date": str(prices.index[-1].date()),
              "years_observed": round(years, 3), "trading_days": len(prices)}
    if "correl" in question.lower():
        other = "DEMO2" if symbol == "DEMO" else "DEMO"
        corr = float(prices.pct_change().corr(demo_history(other).Close.pct_change()))
        fact = {"metric": "historical_correlation_stats", "symbol_a": symbol, "symbol_b": other,
                "period_actual": period, "data_source": SOURCE,
                "method": "Pearson correlation of daily synthetic returns",
                "results": {"correlation": corr, "correlation_pct": corr * 100}}
        answer = f"Synthetic {symbol}/{other} daily-return correlation: {corr:.3f}."
    else:
        total = float(prices.iloc[-1] / prices.iloc[0] - 1)
        cagr = float((1 + total) ** (1 / years) - 1)
        fact = {"metric": "historical_return_stats", "symbol": symbol,
                "period_actual": period, "data_source": SOURCE,
                "results": {"start_price": float(prices.iloc[0]), "end_price": float(prices.iloc[-1]),
                            "total_return_pct": total * 100, "cagr_pct": cagr * 100}}
        answer = f"Synthetic {symbol}: total return {total:.2%}; CAGR {cagr:.2%}."
    result["answer"] = answer + f" Demo always uses the full fixture ({period['start_date']} to {period['end_date']}), regardless of the requested timeframe. No live data or AI call."
    result["verified_facts"] = [dict(fact, id="fact-1")]
    return result
