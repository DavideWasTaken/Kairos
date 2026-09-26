import logging
import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests
import yfinance as yf

logger = logging.getLogger(__name__)

RECENT_INSIDER_WINDOW_DAYS = 90

DCF_ASSUMPTIONS = {
    "risk_free_rate": 0.04,
    "equity_risk_premium": 0.05,
    "pre_tax_debt_cost": 0.05,
    "default_beta": 1.0,
    "default_tax_rate": 0.21,
    "method": "Profile bounds constrain growth, discount rates and terminal growth; missing inputs may use fixed assumptions.",
}
DCF_LIMITATIONS = [
    "Illustrative valuation, sensitive to growth, discount rate and terminal value assumptions; not a price forecast.",
    "Free cash flow definitions vary by provider; this simplified model treats reported FCF as enterprise cash flow and adjusts for debt and cash.",
    "Growth and discount assumptions are heuristics and have not been calibrated or independently validated.",
]

POSITIVE_NEWS_WORDS = {
    "beat",
    "beats",
    "upgrade",
    "upgrades",
    "growth",
    "surge",
    "rally",
    "record",
    "strong",
    "bullish",
}

NEGATIVE_NEWS_WORDS = {
    "miss",
    "misses",
    "downgrade",
    "downgrades",
    "drop",
    "fall",
    "weak",
    "lawsuit",
    "bearish",
    "decline",
    "risk",
    "selloff",
}

POSITIVE_SOCIAL_WORDS = POSITIVE_NEWS_WORDS.union(
    {
        "buy",
        "long",
        "accumulate",
        "uptrend",
        "breakout",
        "undervalued",
        "rebound",
        "moon",
        "pump",
    }
)

NEGATIVE_SOCIAL_WORDS = NEGATIVE_NEWS_WORDS.union(
    {
        "sell",
        "short",
        "overvalued",
        "downtrend",
        "breakdown",
        "crash",
        "dump",
        "bagholder",
    }
)

DCF_PROFILE_CONFIG = {
    "conservative": {
        "growth_min": 0.02,
        "growth_max": 0.12,
        "default_growth": 0.06,
        "terminal_growth": 0.02,
        "projection_years": 8,
        "discount_rate_shift": 0.01,
    },
    "base": {
        "growth_min": 0.03,
        "growth_max": 0.18,
        "default_growth": 0.08,
        "terminal_growth": 0.025,
        "projection_years": 10,
        "discount_rate_shift": 0.0,
    },
    "aggressive": {
        "growth_min": 0.04,
        "growth_max": 0.24,
        "default_growth": 0.10,
        "terminal_growth": 0.03,
        "projection_years": 12,
        "discount_rate_shift": -0.01,
    },
}


def _normalize_dcf_profile(profile: str | None) -> str:
    p = (profile or "base").strip().lower()
    if p in DCF_PROFILE_CONFIG:
        return p
    return "base"


def _safe_float(v):
    try:
        if v is None:
            return None
        if isinstance(v, (float, int, np.floating, np.integer)):
            if np.isnan(v) or np.isinf(v):
                return None
            return float(v)
        out = float(v)
        if np.isnan(out) or np.isinf(out):
            return None
        return out
    except Exception:
        return None


def _safe_int(v):
    fv = _safe_float(v)
    if fv is None:
        return None
    try:
        return int(round(fv))
    except Exception:
        return None


def _series_value(series: pd.Series, keys: list[str]):
    if series is None or len(series) == 0:
        return None
    for key in keys:
        if key in series.index:
            return _safe_float(series.get(key))
    lower_map = {str(k).lower(): k for k in series.index}
    for key in keys:
        match = lower_map.get(str(key).lower())
        if match is not None:
            return _safe_float(series.get(match))
    return None


def _to_iso_date(value):
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        value = value[0]
    if isinstance(value, pd.Timestamp):
        return str(value.date())
    if isinstance(value, datetime):
        return str(value.date())
    try:
        dt = pd.to_datetime(value, errors="coerce")
        if pd.isna(dt):
            return str(value)
        return str(dt.date())
    except Exception:
        return str(value)


def _find_statement_row(df: pd.DataFrame, candidates: list[str]) -> pd.Series | None:
    if df is None or df.empty:
        return None
    for name in candidates:
        if name in df.index:
            return df.loc[name]

    lowered = {str(idx).strip().lower(): idx for idx in df.index}
    for name in candidates:
        key = name.strip().lower()
        if key in lowered:
            return df.loc[lowered[key]]
    return None


def _to_period(col) -> str:
    if isinstance(col, pd.Timestamp):
        return str(col.date())
    if isinstance(col, datetime):
        return str(col.date())
    try:
        return str(pd.to_datetime(col).date())
    except Exception:
        return str(col)


def _yoy_growth(new_val, old_val):
    nv = _safe_float(new_val)
    ov = _safe_float(old_val)
    if nv is None or ov is None or abs(ov) < 1e-12:
        return None
    return (nv - ov) / abs(ov)


def _clamp(value, low, high):
    if value is None:
        return None
    return max(low, min(high, value))


def _normalize_rate(value):
    v = _safe_float(value)
    if v is None:
        return None
    # Some sources may return percentages as whole numbers (e.g. 12 for 12%)
    if abs(v) > 1.5:
        v = v / 100.0
    return v


def _latest_value_from_row(row: pd.Series | None):
    if row is None:
        return None
    dated = []
    undated = []
    for k, v in row.items():
        fv = _safe_float(v)
        if fv is None:
            continue
        dt = pd.to_datetime(k, errors="coerce")
        if pd.isna(dt):
            undated.append(fv)
        else:
            dated.append((dt, fv))
    if dated:
        dated.sort(key=lambda x: x[0])
        return dated[-1][1]
    if undated:
        return undated[-1]
    return None


def _estimate_cagr(values: list[float]):
    vals = [_safe_float(v) for v in values if _safe_float(v) is not None]
    vals = [v for v in vals if v is not None and v > 0]
    if len(vals) < 2:
        return None
    start = vals[0]
    end = vals[-1]
    years = len(vals) - 1
    if years <= 0 or start <= 0 or end <= 0:
        return None
    return (end / start) ** (1.0 / years) - 1.0


def _robust_median(values: list[float]):
    cleaned = []
    for v in values:
        fv = _safe_float(v)
        if fv is not None:
            cleaned.append(fv)
    if not cleaned:
        return None
    return float(np.median(np.asarray(cleaned, dtype=float)))


def _derive_fcf_from_operating_and_capex(operating_cf, capex):
    op = _safe_float(operating_cf)
    cx = _safe_float(capex)
    if op is None or cx is None:
        return None
    # Yahoo can expose capex as negative or positive. Normalize both conventions:
    # FCF = OCF - CapEx(outflow) => if capex is already negative cash outflow, sum it.
    return op + cx if cx < 0 else op - cx


def _estimate_wacc(market_cap, total_debt, tax_rate, beta=None):
    risk_free = 0.04
    equity_risk_premium = 0.05
    beta_n = _safe_float(beta)
    cost_of_equity = risk_free + (beta_n if beta_n is not None else 1.0) * equity_risk_premium
    cost_of_equity = _clamp(cost_of_equity, 0.06, 0.20)

    debt = _safe_float(total_debt) or 0.0
    equity = _safe_float(market_cap) or 0.0
    t_rate = _clamp(_normalize_rate(tax_rate), 0.0, 0.45)
    if t_rate is None:
        t_rate = 0.21
    pre_tax_debt_cost = 0.05

    denom = debt + equity
    if denom <= 0:
        return cost_of_equity

    wacc = (equity / denom) * cost_of_equity + (debt / denom) * pre_tax_debt_cost * (1.0 - t_rate)
    return _clamp(wacc, 0.06, 0.20)


def compute_fundamental_analysis(ticker: str, dcf_profile: str = "base") -> dict:
    dcf_profile = _normalize_dcf_profile(dcf_profile)
    dcf_cfg = DCF_PROFILE_CONFIG[dcf_profile]
    out = {
        "has_data": False,
        "dcf_profile": dcf_profile,
        "currency": None,
        "current_price": None,
        "market_cap": None,
        "trailing_pe": None,
        "forward_pe": None,
        "price_to_book": None,
        "dividend_yield": None,
        "latest_annual": {
            "period": None,
            "revenue": None,
            "net_income": None,
            "net_margin": None,
        },
        "latest_quarterly": {
            "period": None,
            "revenue": None,
            "net_income": None,
            "net_margin": None,
        },
        "revenue_growth_yoy": None,
        "net_income_growth_yoy": None,
        "annual_trend": [],
        "quarterly_trend": [],
        "data_quality": {
            "score": None,
            "status": "unknown",
            "flags": [],
        },
        "estimate_revisions": {
            "has_data": False,
            "sentiment": "neutral",
            "rows": [],
            "summary": {
                "up_7d": None,
                "down_7d": None,
                "up_30d": None,
                "down_30d": None,
                "net_30d": None,
            },
        },
        "earnings_events": {
            "has_data": False,
            "next_event_date": None,
            "events": [],
        },
        "peter_lynch": {
            "score": None,
            "fair_pe": None,
            "fair_value": None,
            "upside": None,
            "signal": "neutral",
            "inputs": {
                "price": None,
                "trailing_pe": None,
                "eps_growth": None,
                "dividend_yield": None,
                "forward_eps": None,
                "trailing_eps": None,
            },
        },
        "discounted_cash_flow": {
            "assumptions": {**DCF_ASSUMPTIONS, "profile_parameters": dict(dcf_cfg)},
            "limitations": list(DCF_LIMITATIONS),
            "intrinsic_value_per_share": None,
            "equity_value": None,
            "enterprise_value": None,
            "upside": None,
            "valuation_view": "neutral",
            "signal": "neutral",
            "profile": dcf_profile,
            "inputs": {
                "base_fcf": None,
                "growth_rate": None,
                "discount_rate": None,
                "terminal_growth": None,
                "projection_years": dcf_cfg["projection_years"],
                "shares_outstanding": None,
            },
        },
        "economic_value_added": {
            "eva": None,
            "nopat": None,
            "invested_capital": None,
            "wacc": None,
            "fair_equity_value": None,
            "fair_value_per_share": None,
            "signal": "neutral",
        },
        "ev_to_sales": {
            "ratio": None,
            "target_multiple": None,
            "enterprise_value": None,
            "revenue": None,
            "fair_equity_value": None,
            "fair_value_per_share": None,
            "signal": "neutral",
        },
        "valuation_summary": {
            "average_fair_value": None,
            "current_price": None,
            "delta_pct": None,
            "relation": "neutral",
            "available_methods": [],
        },
    }

    try:
        tk = yf.Ticker(ticker)

        info = {}
        fast = {}
        try:
            info = tk.info or {}
        except Exception:
            info = {}
        try:
            fast = tk.fast_info or {}
        except Exception:
            fast = {}

        out["currency"] = info.get("financialCurrency") or info.get("currency")
        out["market_cap"] = _safe_float(fast.get("market_cap")) or _safe_float(info.get("marketCap"))
        out["trailing_pe"] = _safe_float(info.get("trailingPE"))
        out["forward_pe"] = _safe_float(info.get("forwardPE"))
        out["price_to_book"] = _safe_float(info.get("priceToBook"))
        out["dividend_yield"] = _normalize_rate(info.get("dividendYield"))
        price = (
            _safe_float(fast.get("last_price"))
            or _safe_float(fast.get("lastPrice"))
            or _safe_float(info.get("currentPrice"))
            or _safe_float(info.get("regularMarketPrice"))
        )
        out["current_price"] = price
        free_cash_flow_info = _safe_float(info.get("freeCashflow"))
        shares_outstanding = (
            _safe_float(fast.get("shares"))
            or _safe_float(fast.get("shares_outstanding"))
            or _safe_float(info.get("sharesOutstanding"))
        )
        enterprise_value = _safe_float(info.get("enterpriseValue"))
        total_debt_info = _safe_float(info.get("totalDebt"))
        total_cash_info = _safe_float(info.get("totalCash"))

        income = tk.income_stmt
        if income is None or income.empty:
            income = tk.financials
        if income is None or income.empty:
            return out

        revenue_row = _find_statement_row(
            income,
            ["Total Revenue", "Operating Revenue", "Revenue"],
        )
        net_income_row = _find_statement_row(
            income,
            ["Net Income", "NetIncome", "Net Income Common Stockholders"],
        )
        ebit_row = _find_statement_row(
            income,
            ["EBIT", "Operating Income", "OperatingIncome"],
        )
        pretax_income_row = _find_statement_row(
            income,
            ["Pretax Income", "PretaxIncome", "Income Before Tax"],
        )
        tax_provision_row = _find_statement_row(
            income,
            ["Tax Provision", "Income Tax Expense", "TaxProvision"],
        )

        if revenue_row is None and net_income_row is None:
            return out

        cols = list(income.columns)
        cols = sorted(cols)
        trend = []
        for c in cols[-6:]:
            revenue = _safe_float(revenue_row.get(c)) if revenue_row is not None else None
            net_income = _safe_float(net_income_row.get(c)) if net_income_row is not None else None
            net_margin = (net_income / revenue) if (revenue and net_income is not None) else None
            trend.append(
                {
                    "period": _to_period(c),
                    "revenue": revenue,
                    "net_income": net_income,
                    "net_margin": net_margin,
                }
            )

        trend = [t for t in trend if t["revenue"] is not None or t["net_income"] is not None]
        out["annual_trend"] = trend
        out["has_data"] = len(trend) > 0

        if trend:
            latest = trend[-1]
            out["latest_annual"] = latest

        quarterly_income = None
        try:
            quarterly_income = tk.quarterly_income_stmt
        except Exception:
            quarterly_income = None
        if quarterly_income is None or quarterly_income.empty:
            try:
                quarterly_income = tk.quarterly_financials
            except Exception:
                quarterly_income = None

        if quarterly_income is not None and not quarterly_income.empty:
            q_revenue_row = _find_statement_row(
                quarterly_income,
                ["Total Revenue", "Operating Revenue", "Revenue"],
            )
            q_net_income_row = _find_statement_row(
                quarterly_income,
                ["Net Income", "NetIncome", "Net Income Common Stockholders"],
            )
            q_cols = sorted(list(quarterly_income.columns))
            q_trend = []
            for c in q_cols[-12:]:
                q_revenue = _safe_float(q_revenue_row.get(c)) if q_revenue_row is not None else None
                q_net_income = _safe_float(q_net_income_row.get(c)) if q_net_income_row is not None else None
                q_net_margin = (q_net_income / q_revenue) if (q_revenue and q_net_income is not None) else None
                q_trend.append(
                    {
                        "period": _to_period(c),
                        "revenue": q_revenue,
                        "net_income": q_net_income,
                        "net_margin": q_net_margin,
                    }
                )
            q_trend = [q for q in q_trend if q["revenue"] is not None or q["net_income"] is not None]
            out["quarterly_trend"] = q_trend
            if q_trend:
                out["latest_quarterly"] = q_trend[-1]

        if len(trend) >= 2:
            out["revenue_growth_yoy"] = _yoy_growth(trend[-1]["revenue"], trend[-2]["revenue"])
            out["net_income_growth_yoy"] = _yoy_growth(trend[-1]["net_income"], trend[-2]["net_income"])

        revenue_cagr = _estimate_cagr([t["revenue"] for t in trend if t["revenue"] is not None])
        net_income_cagr = _estimate_cagr([t["net_income"] for t in trend if t["net_income"] is not None])
        growth_candidates = [
            _normalize_rate(info.get("earningsGrowth")),
            _normalize_rate(info.get("revenueGrowth")),
            out["net_income_growth_yoy"],
            out["revenue_growth_yoy"],
            net_income_cagr,
            revenue_cagr,
        ]
        earnings_growth = _robust_median(growth_candidates)
        earnings_growth = _clamp(earnings_growth, -0.20, 0.30)
        if earnings_growth is None:
            earnings_growth = 0.05
        quality_margin = _clamp(
            out["latest_annual"].get("net_margin") if isinstance(out.get("latest_annual"), dict) else None,
            -0.20,
            0.40,
        )
        quality_margin = quality_margin or 0.0

        trailing_eps = _safe_float(info.get("trailingEps"))
        forward_eps = _safe_float(info.get("forwardEps"))
        trailing_pe = out["trailing_pe"]

        # Peter Lynch (conservative blend):
        # fair P/E ~= long-term growth% + dividend yield%.
        # We blend fast growth signals with historical growth to avoid inflated one-year spikes.
        pl_growth_fast = _normalize_rate(info.get("earningsGrowth")) or _normalize_rate(info.get("revenueGrowth"))
        pl_growth_slow = _robust_median(
            [
                revenue_cagr,
                net_income_cagr,
                out["revenue_growth_yoy"],
                out["net_income_growth_yoy"],
            ]
        )
        if pl_growth_fast is not None and pl_growth_slow is not None:
            pl_growth = (0.35 * pl_growth_fast) + (0.65 * pl_growth_slow)
        else:
            pl_growth = pl_growth_slow if pl_growth_slow is not None else pl_growth_fast
        pl_growth = _clamp(pl_growth, 0.02, 0.18)

        pl_div = _normalize_rate(out["dividend_yield"]) or 0.0
        fair_pe = None
        if pl_growth is not None:
            fair_pe = (max(pl_growth, 0.0) + max(pl_div, 0.0)) * 100.0
        fair_pe = _clamp(fair_pe, 6.0, 28.0)

        pl_score = None
        if fair_pe is not None and trailing_pe is not None and trailing_pe > 0:
            pl_score = fair_pe / trailing_pe
        pl_fair_value = None
        pl_upside = None
        # Most screeners use trailing EPS for Peter Lynch fair value.
        fair_eps = trailing_eps or forward_eps
        if fair_pe is not None and fair_eps is not None and price is not None and price > 0:
            pl_fair_value = fair_eps * fair_pe
            pl_upside = (pl_fair_value - price) / price

        pl_signal = "neutral"
        if pl_score is not None:
            if pl_score >= 1.1:
                pl_signal = "bullish"
            elif pl_score <= 0.9:
                pl_signal = "bearish"
        out["peter_lynch"] = {
            "score": pl_score,
            "fair_pe": fair_pe,
            "fair_value": pl_fair_value,
            "upside": pl_upside,
            "signal": pl_signal,
            "inputs": {
                "price": price,
                "trailing_pe": trailing_pe,
                "eps_growth": pl_growth,
                "dividend_yield": pl_div,
                "forward_eps": forward_eps,
                "trailing_eps": trailing_eps,
            },
        }

        cashflow = tk.cash_flow
        if cashflow is None or cashflow.empty:
            cashflow = tk.cashflow
        free_cash_flow_row = _find_statement_row(
            cashflow,
            ["Free Cash Flow", "FreeCashFlow"],
        )
        operating_cf_row = _find_statement_row(
            cashflow,
            ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities", "Total Cash From Operating Activities"],
        )
        capex_row = _find_statement_row(
            cashflow,
            ["Capital Expenditure", "Capital Expenditures"],
        )
        base_fcf = _latest_value_from_row(free_cash_flow_row)
        fcf_source = "statement_free_cash_flow"
        if free_cash_flow_info is not None and free_cash_flow_info > 0:
            base_fcf = free_cash_flow_info
            fcf_source = "info_free_cashflow"
        if base_fcf is None:
            op_cf = _latest_value_from_row(operating_cf_row)
            capex = _latest_value_from_row(capex_row)
            base_fcf = _derive_fcf_from_operating_and_capex(op_cf, capex)
            fcf_source = "derived_ocf_capex" if base_fcf is not None else "missing"

        balance = tk.balance_sheet
        if balance is None or balance.empty:
            balance = tk.balancesheet
        total_debt = total_debt_info or _latest_value_from_row(
            _find_statement_row(balance, ["Total Debt", "Current Debt And Capital Lease Obligation"])
        )
        total_equity = _latest_value_from_row(
            _find_statement_row(
                balance,
                ["Stockholders Equity", "Total Equity Gross Minority Interest", "Total Equity"],
            )
        )
        cash_equivalents = total_cash_info or _latest_value_from_row(
            _find_statement_row(
                balance,
                ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments", "Cash"],
            )
        )
        total_assets = _latest_value_from_row(_find_statement_row(balance, ["Total Assets"]))
        current_liabilities = _latest_value_from_row(
            _find_statement_row(balance, ["Current Liabilities", "Total Current Liabilities"])
        )

        tax_rate = _normalize_rate(info.get("effectiveTaxRate"))
        if tax_rate is None:
            tax = _latest_value_from_row(tax_provision_row)
            pretax = _latest_value_from_row(pretax_income_row)
            if tax is not None and pretax is not None and abs(pretax) > 1e-9:
                tax_rate = abs(tax / pretax)
        tax_rate = _clamp(tax_rate, 0.05, 0.45)
        if tax_rate is None:
            tax_rate = 0.21

        wacc = _estimate_wacc(out["market_cap"], total_debt, tax_rate, beta=info.get("beta"))

        # DCF with profile-driven horizon and multi-scenario engine (bear/base/bull).
        dcf_intrinsic_per_share = None
        dcf_equity_value = None
        dcf_enterprise_value = None
        dcf_upside = None
        dcf_view = "neutral"
        dcf_signal = "neutral"
        dcf_growth = _normalize_rate(info.get("earningsGrowth")) or _normalize_rate(info.get("revenueGrowth")) or earnings_growth
        dcf_growth = _clamp(dcf_growth, dcf_cfg["growth_min"], dcf_cfg["growth_max"])
        if dcf_growth is None:
            dcf_growth = dcf_cfg["default_growth"]
        terminal_growth = _clamp(dcf_cfg["terminal_growth"], 0.01, min(0.04, (wacc or 0.10) - 0.01))
        if terminal_growth is None:
            terminal_growth = 0.02
        dcf_discount_rate = wacc
        if dcf_discount_rate is not None:
            quality_discount = 0.0
            if (out["market_cap"] or 0) >= 500_000_000_000:
                quality_discount += 0.005
            if quality_margin >= 0.20:
                quality_discount += 0.005
            dcf_discount_rate = _clamp(dcf_discount_rate - quality_discount, 0.065, 0.18)
            dcf_discount_rate = _clamp(dcf_discount_rate + dcf_cfg["discount_rate_shift"], 0.06, 0.20)

        def _run_dcf_case(case_growth, case_discount, case_terminal):
            if (
                base_fcf is None
                or case_discount is None
                or case_terminal is None
                or base_fcf <= 0
                or case_discount <= (case_terminal + 0.002)
            ):
                return {
                    "enterprise_value": None,
                    "equity_value": None,
                    "per_share": None,
                }
            projection_years = int(dcf_cfg["projection_years"])
            pv_fcfs = 0.0
            fcf_t = float(base_fcf)
            for year in range(1, projection_years + 1):
                fade = ((year - 1) / (projection_years - 1)) if projection_years > 1 else 1.0
                year_growth = case_growth + (case_terminal - case_growth) * fade
                fcf_t = fcf_t * (1.0 + year_growth)
                pv_fcfs += fcf_t / ((1.0 + case_discount) ** year)
            terminal_value = (fcf_t * (1.0 + case_terminal)) / (case_discount - case_terminal)
            pv_terminal = terminal_value / ((1.0 + case_discount) ** projection_years)
            case_ev = pv_fcfs + pv_terminal
            case_equity = case_ev - (total_debt or 0.0) + (cash_equivalents or 0.0)
            case_per_share = None
            if shares_outstanding and shares_outstanding > 0:
                case_per_share = case_equity / shares_outstanding
            return {
                "enterprise_value": case_ev,
                "equity_value": case_equity,
                "per_share": case_per_share,
            }

        dcf_scenario_cfg = {
            "bear": {"growth_shift": -0.03, "discount_shift": 0.01, "terminal_shift": -0.003, "weight": 0.25},
            "base": {"growth_shift": 0.0, "discount_shift": 0.0, "terminal_shift": 0.0, "weight": 0.50},
            "bull": {"growth_shift": 0.03, "discount_shift": -0.01, "terminal_shift": 0.003, "weight": 0.25},
        }
        dcf_scenarios = {}
        for name, cfg in dcf_scenario_cfg.items():
            case_growth = _clamp(
                (dcf_growth or dcf_cfg["default_growth"]) + cfg["growth_shift"],
                -0.03,
                max(0.24, dcf_cfg["growth_max"]),
            )
            case_discount = _clamp((dcf_discount_rate or 0.10) + cfg["discount_shift"], 0.055, 0.22)
            max_terminal = min(0.04, case_discount - 0.005)
            case_terminal = _clamp((terminal_growth or 0.02) + cfg["terminal_shift"], 0.005, max_terminal)
            case_result = _run_dcf_case(case_growth, case_discount, case_terminal)
            dcf_scenarios[name] = {
                "weight": cfg["weight"],
                "growth_rate": case_growth,
                "discount_rate": case_discount,
                "terminal_growth": case_terminal,
                "enterprise_value": case_result["enterprise_value"],
                "equity_value": case_result["equity_value"],
                "intrinsic_value_per_share": case_result["per_share"],
            }

        usable_cases = [v for v in dcf_scenarios.values() if _safe_float(v.get("intrinsic_value_per_share")) is not None]
        if usable_cases:
            total_weight = sum(float(v["weight"]) for v in usable_cases) or 1.0
            dcf_intrinsic_per_share = sum(
                float(v["intrinsic_value_per_share"]) * (float(v["weight"]) / total_weight)
                for v in usable_cases
            )
            dcf_equity_value = sum(
                float(v["equity_value"]) * (float(v["weight"]) / total_weight)
                for v in usable_cases
                if _safe_float(v.get("equity_value")) is not None
            )
            dcf_enterprise_value = sum(
                float(v["enterprise_value"]) * (float(v["weight"]) / total_weight)
                for v in usable_cases
                if _safe_float(v.get("enterprise_value")) is not None
            )
            per_share_values = [float(v["intrinsic_value_per_share"]) for v in usable_cases]
            dcf_range_low = min(per_share_values)
            dcf_range_high = max(per_share_values)
            if dcf_intrinsic_per_share is not None and price is not None and price > 0:
                dcf_upside = (dcf_intrinsic_per_share - price) / price
                if dcf_upside >= 0.15:
                    dcf_signal = "bullish"
                    dcf_view = "undervalued"
                elif dcf_upside <= -0.15:
                    dcf_signal = "bearish"
                    dcf_view = "overvalued"
                else:
                    dcf_view = "fairly_valued"
        else:
            dcf_range_low = None
            dcf_range_high = None

        out["discounted_cash_flow"] = {
            "assumptions": {**DCF_ASSUMPTIONS, "profile_parameters": dict(dcf_cfg), "fcf_source": fcf_source},
            "limitations": list(DCF_LIMITATIONS),
            "intrinsic_value_per_share": dcf_intrinsic_per_share,
            "equity_value": dcf_equity_value,
            "enterprise_value": dcf_enterprise_value,
            "upside": dcf_upside,
            "valuation_view": dcf_view,
            "signal": dcf_signal,
            "profile": dcf_profile,
            "range_per_share": {
                "low": dcf_range_low,
                "high": dcf_range_high,
            },
            "scenarios": dcf_scenarios,
            "inputs": {
                "base_fcf": base_fcf,
                "growth_rate": dcf_growth,
                "discount_rate": dcf_discount_rate,
                "terminal_growth": terminal_growth,
                "projection_years": int(dcf_cfg["projection_years"]),
                "shares_outstanding": shares_outstanding,
            },
        }

        # EVA = NOPAT - (Invested Capital * WACC)
        ebit = _latest_value_from_row(ebit_row)
        nopat = ebit * (1.0 - tax_rate) if ebit is not None else None
        invested_capital = None
        if total_debt is not None and total_equity is not None:
            invested_capital = total_debt + total_equity - (cash_equivalents or 0.0)
        elif total_assets is not None and current_liabilities is not None:
            invested_capital = total_assets - current_liabilities

        eva = None
        eva_signal = "neutral"
        eva_fair_equity_value = None
        eva_fair_price = None
        if nopat is not None and invested_capital is not None and wacc is not None and invested_capital > 0:
            eva = nopat - (invested_capital * wacc)
            # Keep EVA valuation coherent with the same economic logic for every asset:
            # Firm value ~= Invested Capital + EVA / WACC, then derive equity value.
            if wacc > 0:
                eva_firm_value = invested_capital + (eva / wacc)
                eva_fair_equity_value = eva_firm_value - (total_debt or 0.0) + (cash_equivalents or 0.0)
            if shares_outstanding and shares_outstanding > 0:
                eva_fair_price = eva_fair_equity_value / shares_outstanding
            if eva_fair_price is not None and price is not None and price > 0:
                eva_upside = (eva_fair_price - price) / price
                if eva_upside >= 0.15:
                    eva_signal = "bullish"
                elif eva_upside <= -0.15:
                    eva_signal = "bearish"
            else:
                if eva > 0:
                    eva_signal = "bullish"
                elif eva < 0:
                    eva_signal = "bearish"

        out["economic_value_added"] = {
            "eva": eva,
            "nopat": nopat,
            "invested_capital": invested_capital,
            "wacc": wacc,
            "fair_equity_value": eva_fair_equity_value,
            "fair_value_per_share": eva_fair_price,
            "signal": eva_signal,
        }

        # EV/Sales
        latest_revenue = out["latest_annual"].get("revenue") if isinstance(out["latest_annual"], dict) else None
        sales_reference = _safe_float(info.get("totalRevenue")) or latest_revenue
        ev_for_ratio = enterprise_value
        if ev_for_ratio is None and out["market_cap"] is not None:
            ev_for_ratio = out["market_cap"] + (total_debt or 0.0) - (cash_equivalents or 0.0)

        ev_sales = None
        ev_sales_signal = "neutral"
        target_ev_sales = None
        evs_fair_ev = None
        evs_fair_equity_value = None
        evs_fair_price = None
        revenue_growth_for_multiple = None
        margin_for_multiple = None
        if ev_for_ratio is not None and sales_reference is not None and sales_reference > 0:
            ev_sales = ev_for_ratio / sales_reference
            revenue_growth_for_multiple = _robust_median(
                [
                    _normalize_rate(info.get("revenueGrowth")),
                    out["revenue_growth_yoy"],
                    revenue_cagr,
                ]
            )
            growth_for_multiple = _clamp(revenue_growth_for_multiple, -0.10, 0.25) or 0.04
            margin_for_multiple = _clamp(
                out["latest_annual"].get("net_margin") if isinstance(out.get("latest_annual"), dict) else None,
                -0.20,
                0.40,
            )
            margin_for_multiple = margin_for_multiple or 0.0
            heuristic_ev_sales = _clamp(
                2.0 + (growth_for_multiple * 12.0) + (max(margin_for_multiple, 0.0) * 4.0),
                1.0,
                12.0,
            )
            target_ev_sales = (0.75 * ev_sales) + (0.25 * heuristic_ev_sales)
            target_ev_sales = _clamp(target_ev_sales, ev_sales * 0.70, ev_sales * 1.20)
            evs_fair_ev = sales_reference * target_ev_sales
            evs_fair_equity_value = evs_fair_ev - (total_debt or 0.0) + (cash_equivalents or 0.0)
            if shares_outstanding and shares_outstanding > 0:
                evs_fair_price = evs_fair_equity_value / shares_outstanding
            if evs_fair_price is not None and price is not None and price > 0:
                evs_upside = (evs_fair_price - price) / price
                if evs_upside >= 0.15:
                    ev_sales_signal = "bullish"
                elif evs_upside <= -0.15:
                    ev_sales_signal = "bearish"
            else:
                if ev_sales <= 2:
                    ev_sales_signal = "bullish"
                elif ev_sales >= 8:
                    ev_sales_signal = "bearish"

        out["ev_to_sales"] = {
            "ratio": ev_sales,
            "target_multiple": target_ev_sales,
            "enterprise_value": ev_for_ratio,
            "revenue": sales_reference,
            "fair_equity_value": evs_fair_equity_value,
            "fair_value_per_share": evs_fair_price,
            "inputs": {
                "revenue_growth": revenue_growth_for_multiple,
                "net_margin": margin_for_multiple,
            },
            "signal": ev_sales_signal,
        }

        fair_value_map = {
            "dcf": _safe_float(dcf_intrinsic_per_share),
            "ev_to_sales": _safe_float(evs_fair_price),
        }
        available = [name for name, value in fair_value_map.items() if value is not None]
        latest_net_income = _safe_float(out.get("latest_annual", {}).get("net_income"))
        trailing_eps_for_regime = _safe_float(info.get("trailingEps"))
        forward_eps_for_regime = _safe_float(info.get("forwardEps"))
        eps_for_regime = trailing_eps_for_regime if trailing_eps_for_regime is not None else forward_eps_for_regime
        is_loss_making = False
        if latest_net_income is not None and latest_net_income <= 0:
            is_loss_making = True
        elif eps_for_regime is not None and eps_for_regime <= 0:
            is_loss_making = True
        elif trailing_pe is not None and trailing_pe <= 0:
            is_loss_making = True

        primary_model = None
        valuation_mode = "unavailable"
        primary_reason = "No valid fair value available from DCF or EV/Sales."
        if is_loss_making and fair_value_map["ev_to_sales"] is not None:
            primary_model = "ev_to_sales"
            valuation_mode = "ev_sales_primary"
            primary_reason = "Loss-making profile detected: EV/Sales is the primary model."
        elif fair_value_map["dcf"] is not None:
            primary_model = "dcf"
            valuation_mode = "dcf_primary"
            primary_reason = "Positive earnings profile: DCF is the primary model."
        elif fair_value_map["ev_to_sales"] is not None:
            primary_model = "ev_to_sales"
            valuation_mode = "ev_sales_fallback"
            primary_reason = "DCF unavailable, EV/Sales selected as fallback."

        raw_weights = {}
        if primary_model == "dcf":
            raw_weights["dcf"] = 0.85
            raw_weights["ev_to_sales"] = 0.15
        elif primary_model == "ev_to_sales":
            raw_weights["ev_to_sales"] = 0.85
            raw_weights["dcf"] = 0.15

        usable_weights = {}
        for model_name, weight in raw_weights.items():
            if fair_value_map.get(model_name) is not None and weight > 0:
                usable_weights[model_name] = float(weight)

        if not usable_weights and primary_model and fair_value_map.get(primary_model) is not None:
            usable_weights[primary_model] = 1.0
        if not usable_weights and available:
            usable_weights[available[0]] = 1.0

        total_weight = sum(usable_weights.values()) or 1.0
        normalized_weights = {k: (v / total_weight) for k, v in usable_weights.items()}

        average_fair_value = None
        if normalized_weights:
            average_fair_value = float(
                sum((fair_value_map[k] or 0.0) * w for k, w in normalized_weights.items())
            )

        delta_pct = None
        relation = "neutral"
        if average_fair_value is not None and price is not None and average_fair_value > 0:
            delta_pct = (price - average_fair_value) / average_fair_value
            if price < average_fair_value:
                relation = "below"
            elif price > average_fair_value:
                relation = "above"
            else:
                relation = "at"

        out["valuation_summary"] = {
            "average_fair_value": average_fair_value,
            "current_price": price,
            "delta_pct": delta_pct,
            "relation": relation,
            "available_methods": available,
            "primary_model": primary_model,
            "valuation_mode": valuation_mode,
            "is_loss_making": is_loss_making,
            "method_weights": [
                {"model": model_name, "weight": weight}
                for model_name, weight in normalized_weights.items()
            ],
            "note": primary_reason,
        }

        # Estimate revisions (analyst updates).
        try:
            revisions_df = tk.eps_revisions
            if isinstance(revisions_df, pd.DataFrame) and not revisions_df.empty:
                rows = []
                agg_up_7 = agg_down_7 = agg_up_30 = agg_down_30 = 0
                for period, row in revisions_df.head(6).iterrows():
                    up_7 = _safe_int(_series_value(row, ["upLast7days", "up_last_7days"]))
                    down_7 = _safe_int(_series_value(row, ["downLast7days", "down_last_7days"]))
                    up_30 = _safe_int(_series_value(row, ["upLast30days", "up_last_30days"]))
                    down_30 = _safe_int(_series_value(row, ["downLast30days", "down_last_30days"]))
                    net_30 = None
                    if up_30 is not None or down_30 is not None:
                        net_30 = int((up_30 or 0) - (down_30 or 0))
                    if up_7 is not None:
                        agg_up_7 += up_7
                    if down_7 is not None:
                        agg_down_7 += down_7
                    if up_30 is not None:
                        agg_up_30 += up_30
                    if down_30 is not None:
                        agg_down_30 += down_30
                    rows.append(
                        {
                            "period": str(period),
                            "up_7d": up_7,
                            "down_7d": down_7,
                            "up_30d": up_30,
                            "down_30d": down_30,
                            "net_30d": net_30,
                        }
                    )
                net_30_total = agg_up_30 - agg_down_30
                sentiment = "neutral"
                if net_30_total > 0:
                    sentiment = "positive"
                elif net_30_total < 0:
                    sentiment = "negative"
                out["estimate_revisions"] = {
                    "has_data": True,
                    "sentiment": sentiment,
                    "rows": rows,
                    "summary": {
                        "up_7d": agg_up_7,
                        "down_7d": agg_down_7,
                        "up_30d": agg_up_30,
                        "down_30d": agg_down_30,
                        "net_30d": net_30_total,
                    },
                }
        except Exception:
            pass

        # Earnings & events (upcoming dates and key calendar points).
        events = []
        seen_events = set()
        try:
            cal = tk.calendar or {}
            raw_earnings_date = cal.get("Earnings Date")
            raw_ex_div = cal.get("Ex-Dividend Date")
            raw_div = cal.get("Dividend Date")
            for label, event_type, raw in [
                ("Earnings Date", "earnings", raw_earnings_date),
                ("Ex-Dividend Date", "ex_dividend", raw_ex_div),
                ("Dividend Date", "dividend", raw_div),
            ]:
                if raw is None:
                    continue
                values = raw if isinstance(raw, (list, tuple)) else [raw]
                for value in values:
                    d = _to_iso_date(value)
                    if not d:
                        continue
                    key = (event_type, d)
                    if key in seen_events:
                        continue
                    seen_events.add(key)
                    events.append(
                        {
                            "type": event_type,
                            "label": label,
                            "date": d,
                            "source": "calendar",
                        }
                    )
        except Exception:
            pass

        try:
            earnings_dates_df = tk.get_earnings_dates(limit=4)
            if isinstance(earnings_dates_df, pd.DataFrame) and not earnings_dates_df.empty:
                for idx, row in earnings_dates_df.head(4).iterrows():
                    d = _to_iso_date(idx)
                    if not d:
                        continue
                    key = ("earnings", d)
                    if key in seen_events:
                        continue
                    seen_events.add(key)
                    events.append(
                        {
                            "type": "earnings",
                            "label": "Earnings Date",
                            "date": d,
                            "source": "earnings_dates",
                            "eps_estimate": _safe_float(_series_value(row, ["EPS Estimate"])),
                            "reported_eps": _safe_float(_series_value(row, ["Reported EPS"])),
                            "surprise_pct": _safe_float(_series_value(row, ["Surprise(%)"])),
                        }
                    )
        except Exception:
            pass

        if events:
            events = sorted(events, key=lambda x: x.get("date") or "")
            today = datetime.now(timezone.utc).date()
            future = [e for e in events if e.get("date") and pd.to_datetime(e["date"], errors="coerce").date() >= today]
            next_event_date = future[0]["date"] if future else events[0]["date"]
            out["earnings_events"] = {
                "has_data": True,
                "next_event_date": next_event_date,
                "events": events[:8],
            }

        # Data quality flags and score.
        flags = []
        if price is None:
            flags.append({"level": "high", "code": "missing_price", "message": "Current price is missing."})
        if shares_outstanding is None:
            flags.append({"level": "high", "code": "missing_shares", "message": "Shares outstanding not available."})
        if base_fcf is None:
            flags.append({"level": "high", "code": "missing_fcf", "message": "Free cash flow not available."})
        elif fcf_source == "derived_ocf_capex":
            flags.append({"level": "medium", "code": "fcf_derived", "message": "FCF derived from operating cash flow and capex."})
        if out["latest_annual"].get("revenue") is None:
            flags.append({"level": "medium", "code": "missing_revenue", "message": "Latest annual revenue missing."})
        if out["latest_annual"].get("net_income") is None:
            flags.append({"level": "medium", "code": "missing_net_income", "message": "Latest annual net income missing."})
        if len(out["valuation_summary"].get("available_methods", [])) < 2:
            flags.append({"level": "high", "code": "low_method_coverage", "message": "Less than two valuation methods produced a fair value."})
        if out["estimate_revisions"].get("has_data") is False:
            flags.append({"level": "low", "code": "no_revisions", "message": "Estimate revisions data unavailable."})
        if out["earnings_events"].get("has_data") is False:
            flags.append({"level": "low", "code": "no_events", "message": "Earnings/events calendar unavailable."})

        penalty = 0
        for f in flags:
            if f["level"] == "high":
                penalty += 18
            elif f["level"] == "medium":
                penalty += 10
            else:
                penalty += 4
        dq_score = int(max(0, min(100, 100 - penalty)))
        dq_status = "high" if dq_score >= 80 else ("medium" if dq_score >= 55 else "low")
        out["data_quality"] = {
            "score": dq_score,
            "status": dq_status,
            "flags": flags,
        }

    except Exception as e:
        logger.warning("Fundamental analysis failed for %s: %s", ticker, type(e).__name__)

    return out


def _slope(values: np.ndarray) -> float:
    y = np.asarray(values, dtype=float)
    y = y[np.isfinite(y)]
    if len(y) < 5:
        return 0.0
    x = np.arange(len(y), dtype=float)
    return float(np.polyfit(x, y, 1)[0])


def _zscore(s: pd.Series, window: int = 60) -> pd.Series:
    mu = s.rolling(window).mean()
    sd = s.rolling(window).std()
    z = (s - mu) / sd.replace(0, np.nan)
    return z.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def compute_wyckoff_causes_effects(history_data: pd.DataFrame) -> dict:
    out = {
        "signal": "neutral",
        "interpretation": "Not enough data",
        "price_slope": 0.0,
        "wyckoff_slope": 0.0,
        "divergence": "none",
        "series": {"dates": [], "price": [], "price_norm": [], "wyckoff_line": []},
    }

    if history_data is None or history_data.empty:
        return out

    close = history_data["Close"] if "Close" in history_data.columns else history_data.iloc[:, 0]
    volume = (
        history_data["Volume"]
        if "Volume" in history_data.columns
        else pd.Series(np.zeros(len(close)), index=close.index, dtype=float)
    )

    close = pd.Series(close).dropna().astype(float)
    volume = pd.Series(volume).reindex(close.index).fillna(0.0).astype(float)
    if len(close) < 50:
        return out

    momentum = close.pct_change(10).fillna(0.0)
    volume_pressure = (volume / volume.rolling(20).mean().replace(0, np.nan) - 1.0).fillna(0.0)
    wyckoff_raw = momentum * (1.0 + volume_pressure)
    wyckoff_line = _zscore(wyckoff_raw, window=60).ewm(span=8, adjust=False).mean() * 100.0
    price_norm = ((close / close.iloc[0]) - 1.0) * 100.0

    lookback = min(30, len(close))
    price_slope = _slope(close.tail(lookback).values)
    wy_slope = _slope(wyckoff_line.tail(lookback).values)

    signal = "neutral"
    divergence = "none"
    interpretation = "Trend is mixed."
    if price_slope > 0 and wy_slope > 0:
        signal = "trend_confirmed_up"
        interpretation = "Price and Wyckoff line are both rising. Trend appears supported."
    elif price_slope < 0 and wy_slope < 0:
        signal = "trend_confirmed_down"
        interpretation = "Price and Wyckoff line are both falling. Downtrend appears supported."
    elif price_slope > 0 and wy_slope < 0:
        signal = "bearish_divergence"
        divergence = "bearish"
        interpretation = "Price is rising while the Wyckoff line is weakening: a descriptive bearish divergence."
    elif price_slope < 0 and wy_slope > 0:
        signal = "bullish_divergence"
        divergence = "bullish"
        interpretation = "Price is falling while the Wyckoff line improves: a descriptive bullish divergence."

    window = min(180, len(close))
    out.update(
        {
            "signal": signal,
            "interpretation": interpretation,
            "price_slope": float(price_slope),
            "wyckoff_slope": float(wy_slope),
            "divergence": divergence,
            "series": {
                "dates": [str(d.date()) for d in close.index[-window:]],
                "price": [float(v) for v in close.iloc[-window:].values.tolist()],
                "price_norm": [float(v) for v in price_norm.iloc[-window:].values.tolist()],
                "wyckoff_line": [float(v) for v in wyckoff_line.iloc[-window:].values.tolist()],
            },
        }
    )
    return out


def _compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    return rsi.replace([np.inf, -np.inf], np.nan).fillna(50.0)


def compute_overbought_oversold(history_data: pd.DataFrame) -> dict:
    out = {
        "status": "neutral",
        "interpretation": "Not enough data",
        "rsi": None,
        "stochastic_k": None,
        "stochastic_d": None,
        "history": {"dates": [], "rsi": []},
    }
    if history_data is None or history_data.empty:
        return out

    close = history_data["Close"] if "Close" in history_data.columns else history_data.iloc[:, 0]

    close = pd.Series(close).dropna().astype(float)
    if len(close) < 30:
        return out

    rsi = _compute_rsi(close, 14)

    rsi_last = float(rsi.iloc[-1])

    status = "neutral"
    interpretation = "No strong RSI overbought/oversold signal."
    if rsi_last >= 70:
        status = "overbought"
        interpretation = "RSI is in overbought territory (>= 70). The trend may persist."
    elif rsi_last <= 30:
        status = "oversold"
        interpretation = "RSI is in oversold territory (<= 30). This threshold does not establish a rebound probability."

    window = min(180, len(close))
    out.update(
        {
            "status": status,
            "interpretation": interpretation,
            "rsi": rsi_last,
            "stochastic_k": None,
            "stochastic_d": None,
            "history": {
                "dates": [str(d.date()) for d in close.index[-window:]],
                "rsi": [float(v) for v in rsi.iloc[-window:].values.tolist()],
            },
        }
    )
    return out


def _headline_sentiment(title: str) -> str:
    txt = (title or "").lower()
    pos = sum(1 for w in POSITIVE_NEWS_WORDS if w in txt)
    neg = sum(1 for w in NEGATIVE_NEWS_WORDS if w in txt)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def _text_sentiment(text: str, positive_words: set[str], negative_words: set[str]) -> str:
    txt = (text or "").lower()
    if not txt:
        return "neutral"
    pos = sum(1 for w in positive_words if w in txt)
    neg = sum(1 for w in negative_words if w in txt)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def _social_symbol_from_ticker(ticker: str) -> str:
    t = (ticker or "").strip().upper()
    if t.startswith("^"):
        t = t[1:]
    if "-USD" in t:
        t = t.split("-USD", 1)[0]
    if "/" in t:
        t = t.split("/", 1)[0]
    return t


def _build_social_queries(ticker: str) -> list[str]:
    symbol = _social_symbol_from_ticker(ticker)
    base = (ticker or "").strip().upper()
    queries = []
    if symbol:
        queries.append(f"${symbol}")
        queries.append(f"{symbol} stock")
        queries.append(symbol)
    if base and base != symbol:
        queries.append(base)
    dedup = []
    seen = set()
    for q in queries:
        qq = q.strip()
        if not qq or qq in seen:
            continue
        seen.add(qq)
        dedup.append(qq)
    return dedup[:3]


def _looks_related_to_symbol(text: str, symbol: str) -> bool:
    if not text or not symbol:
        return False
    upper = text.upper()
    sym = symbol.upper()
    if f"${sym}" in upper:
        return True
    if re.search(rf"\b{re.escape(sym)}\b", upper):
        return True
    return False


def _normalize_news_items(items: list[dict], max_items: int = 12) -> list[dict]:
    cleaned = []
    for n in items:
        title = n.get("title")
        url = n.get("url")
        if not title or not url:
            continue
        cleaned.append(
            {
                "title": title,
                "publisher": n.get("publisher") or "Unknown",
                "published_at": n.get("published_at"),
                "url": url,
                "sentiment": _headline_sentiment(title),
            }
        )

    seen = set()
    deduped = []
    for n in cleaned:
        key = (n["title"], n["url"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(n)

    return deduped[:max_items]


def _coerce_frame(value) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if value is None:
        return pd.DataFrame()
    if isinstance(value, list):
        try:
            return pd.DataFrame(value)
        except Exception:
            return pd.DataFrame()
    if isinstance(value, dict):
        try:
            return pd.DataFrame([value])
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def _pick_record_value(record: dict, keys: list[str]):
    if not isinstance(record, dict):
        return None
    for key in keys:
        if key in record and record.get(key) not in (None, "", [], {}):
            return record.get(key)
    lowered = {str(k).strip().lower(): v for k, v in record.items()}
    for key in keys:
        match = lowered.get(str(key).strip().lower())
        if match not in (None, "", [], {}):
            return match
    return None


def _is_buy_side_transaction(text: str) -> bool:
    txt = (text or "").strip().lower()
    if not txt:
        return False
    if re.search(r"\b(awards?|grants?|gifts?|exercises?|options?|sales?|sell|dispositions?)\b", txt):
        return False
    return bool(re.search(r"\b(buy|buys|bought|purchase|purchases|purchased)\b", txt))


def _is_sell_side_transaction(text: str) -> bool:
    txt = (text or "").strip().lower()
    if not txt:
        return False
    return any(token in txt for token in ["sell", "sale", "dispose", "disposition"])


def _normalize_insider_transactions(df: pd.DataFrame, max_items: int | None = 20) -> list[dict]:
    if df is None or df.empty:
        return []

    records = []
    for raw in df.to_dict(orient="records"):
        tx_date = _to_iso_date(
            _pick_record_value(
                raw,
                ["startDate", "transactionDate", "date", "Date", "Start Date", "Transaction Date"],
            )
        )
        insider_name = _pick_record_value(raw, ["insider", "name", "Insider", "Name"])
        relation = _pick_record_value(
            raw,
            ["relation", "position", "jobTitle", "title", "Relation", "Position", "Title"],
        )
        text = _pick_record_value(
            raw,
            ["text", "transactionText", "type", "Transaction", "Text", "transactionType"],
        )
        shares = _safe_float(
            _pick_record_value(
                raw,
                [
                    "shares",
                    "sharesTraded",
                    "transactionShares",
                    "Shares",
                    "Number of Shares",
                    "shares_transacted",
                ],
            )
        )
        value = _safe_float(
            _pick_record_value(
                raw,
                ["value", "transactionValue", "Value", "transaction_value", "sharesValue"],
            )
        )
        ownership = _pick_record_value(
            raw,
            ["ownership", "ownershipType", "Ownership", "ownershipNature"],
        )

        is_purchase = _is_buy_side_transaction(str(text or ""))
        if not is_purchase:
            continue

        shares_abs = abs(shares) if shares is not None else None
        price = None
        if value is not None and shares_abs not in (None, 0):
            price = value / shares_abs

        records.append(
            {
                "date": tx_date,
                "insider": str(insider_name).strip() if insider_name not in (None, "") else "Unknown insider",
                "relation": str(relation).strip() if relation not in (None, "") else None,
                "transaction_type": str(text).strip() if text not in (None, "") else "Purchase",
                "shares": shares_abs,
                "value": abs(value) if value is not None else None,
                "price": price,
                "ownership": str(ownership).strip() if ownership not in (None, "") else None,
            }
        )

    records = sorted(records, key=lambda row: row.get("date") or "", reverse=True)
    return records[:max_items]


def _filter_recent_insider_transactions(records: list[dict], window_days: int = RECENT_INSIDER_WINDOW_DAYS) -> list[dict]:
    if not records:
        return []
    cutoff = datetime.now(timezone.utc).date() - pd.Timedelta(days=window_days)
    filtered = []
    for row in records:
        raw_date = row.get("date")
        parsed = pd.to_datetime(raw_date, errors="coerce")
        if pd.isna(parsed):
            continue
        if parsed.date() >= cutoff:
            filtered.append(row)
    return filtered


def get_insider_activity(ticker: str, max_items: int = 20, window_days: int = RECENT_INSIDER_WINDOW_DAYS) -> dict:
    out = {
        "source": "yfinance_insider_transactions",
        "has_data": False,
        "has_purchases": False,
        "window_days": window_days,
        "summary": {
            "purchase_count": 0,
            "purchase_shares": None,
            "purchase_value": None,
            "latest_purchase_date": None,
        },
        "transactions": [],
        "transactions_truncated": False,
        "note": (
            f"Explicitly identified corporate insider purchases from the last {window_days} days. "
            "Summary counts all matching rows returned by the provider; displayed rows may be limited. "
            "Provider coverage may be incomplete. Awards, grants, gifts and unknown transaction types are excluded."
        ),
    }

    try:
        tk = yf.Ticker(ticker)
        transactions_df = _coerce_frame(tk.insider_transactions)
        purchases = _normalize_insider_transactions(transactions_df, max_items=None)
        purchases = _filter_recent_insider_transactions(purchases, window_days=window_days)
        if purchases:
            total_shares = sum((row.get("shares") or 0.0) for row in purchases)
            valued_rows = [row for row in purchases if row.get("value") is not None]
            total_value = sum((row.get("value") or 0.0) for row in valued_rows) if valued_rows else None
            out.update(
                {
                    "has_data": True,
                    "has_purchases": True,
                    "transactions": purchases[:max_items],
                    "transactions_truncated": len(purchases) > max_items,
                    "summary": {
                        "purchase_count": len(purchases),
                        "purchase_shares": total_shares if total_shares > 0 else None,
                        "purchase_value": total_value,
                        "valued_purchase_count": len(valued_rows),
                        "latest_purchase_date": purchases[0].get("date"),
                    },
                }
            )
            return out
    except Exception as e:
        logger.warning("Insider transactions fetch failed for %s: %s", ticker, type(e).__name__)

    try:
        tk = yf.Ticker(ticker)
        purchases_df = _coerce_frame(tk.insider_purchases)
        if purchases_df is not None and not purchases_df.empty:
            out["has_data"] = True
            out["note"] = (
                "Yahoo returned aggregate insider summary data with an unverified reporting window. "
                "No individual purchases could be verified for the requested window."
            )
    except Exception as e:
        logger.warning("Insider purchases summary fetch failed for %s: %s", ticker, type(e).__name__)

    return out


def get_asset_news(ticker: str, max_items: int = 12) -> list[dict]:
    news_items = []

    # Source 1: yfinance ticker news (free Yahoo feed)
    try:
        raw = yf.Ticker(ticker).news or []
        for item in raw:
            content = item.get("content", {}) if isinstance(item, dict) else {}
            title = content.get("title") or item.get("title")
            provider = (
                content.get("provider", {}).get("displayName")
                or item.get("publisher")
                or "Yahoo Finance"
            )
            link = (
                content.get("canonicalUrl", {}).get("url")
                or content.get("clickThroughUrl", {}).get("url")
                or item.get("link")
            )
            published = (
                content.get("pubDate")
                or item.get("providerPublishTime")
                or item.get("published")
            )

            if isinstance(published, (int, float)):
                published = datetime.fromtimestamp(published, tz=timezone.utc).isoformat()
            elif published is not None:
                published = str(published)

            if title and link:
                news_items.append(
                    {
                        "title": title,
                        "publisher": provider,
                        "url": link,
                        "published_at": published,
                    }
                )
    except Exception as e:
        logger.warning("Ticker news failed for %s: %s", ticker, type(e).__name__)

    # Source 2 fallback: Yahoo search news API (free)
    if len(news_items) < max_items:
        try:
            url = "https://query2.finance.yahoo.com/v1/finance/search"
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                )
            }
            params = {"q": ticker, "quotesCount": 0, "newsCount": max_items}
            resp = requests.get(url, headers=headers, params=params, timeout=6)
            resp.raise_for_status()
            payload = resp.json()
            for n in payload.get("news", []):
                title = n.get("title")
                link = n.get("link")
                publisher = n.get("publisher") or "Yahoo Finance"
                published = n.get("providerPublishTime")
                if isinstance(published, (int, float)):
                    published = datetime.fromtimestamp(published, tz=timezone.utc).isoformat()
                if title and link:
                    news_items.append(
                        {
                            "title": title,
                            "publisher": publisher,
                            "url": link,
                            "published_at": published,
                        }
                    )
        except Exception as e:
            logger.warning("Yahoo search news failed for %s: %s", ticker, type(e).__name__)

    return _normalize_news_items(news_items, max_items=max_items)


def get_reddit_social_sentiment(ticker: str, max_items: int = 20) -> dict:
    out = {
        "source": "reddit",
        "has_data": False,
        "query_symbol": _social_symbol_from_ticker(ticker),
        "sentiment": "neutral",
        "score": 50,
        "confidence": 0,
        "mentions_24h": 0,
        "mentions_7d": 0,
        "bullish_ratio": 0.0,
        "bearish_ratio": 0.0,
        "posts": [],
        "note": "Social sentiment is experimental and should be used as a secondary signal.",
    }
    queries = _build_social_queries(ticker)
    if not queries:
        return out

    raw_posts = []
    seen = set()
    headers = {
        "User-Agent": (
            "Kairos/1.0 (by /u/kairos_app; contact: support@kairos.local)"
        )
    }
    now_ts = datetime.now(timezone.utc).timestamp()
    since_24h = now_ts - (24 * 3600)
    since_7d = now_ts - (7 * 24 * 3600)
    symbol = out["query_symbol"]

    for q in queries:
        try:
            url = "https://www.reddit.com/search.json"
            params = {
                "q": q,
                "sort": "new",
                "t": "week",
                "limit": 50,
                "type": "link",
            }
            resp = requests.get(url, headers=headers, params=params, timeout=6)
            resp.raise_for_status()
            payload = resp.json() or {}
            children = (((payload.get("data") or {}).get("children")) or [])
            for child in children:
                data = child.get("data") or {}
                title = (data.get("title") or "").strip()
                selftext = (data.get("selftext") or "").strip()
                permalink = data.get("permalink")
                if not title or not permalink:
                    continue
                full_text = f"{title} {selftext}".strip()
                if symbol and not _looks_related_to_symbol(full_text, symbol):
                    continue
                post_url = f"https://www.reddit.com{permalink}"
                key = (title, post_url)
                if key in seen:
                    continue
                seen.add(key)
                created_utc = _safe_float(data.get("created_utc"))
                published = None
                if created_utc is not None:
                    published = datetime.fromtimestamp(created_utc, tz=timezone.utc).isoformat()
                social_sentiment = _text_sentiment(full_text, POSITIVE_SOCIAL_WORDS, NEGATIVE_SOCIAL_WORDS)
                raw_posts.append(
                    {
                        "title": title,
                        "subreddit": data.get("subreddit"),
                        "url": post_url,
                        "published_at": published,
                        "sentiment": social_sentiment,
                        "score": _safe_int(data.get("score")) or 0,
                        "num_comments": _safe_int(data.get("num_comments")) or 0,
                        "created_utc": created_utc,
                    }
                )
        except Exception as e:
            logger.warning("Reddit sentiment fetch failed for %s (query=%s): %s", ticker, q, type(e).__name__)

    if not raw_posts:
        return out

    raw_posts = sorted(
        raw_posts,
        key=lambda p: (
            _safe_float(p.get("created_utc")) or 0.0,
            _safe_float(p.get("score")) or 0.0,
            _safe_float(p.get("num_comments")) or 0.0,
        ),
        reverse=True,
    )

    pos_count = sum(1 for p in raw_posts if p.get("sentiment") == "positive")
    neg_count = sum(1 for p in raw_posts if p.get("sentiment") == "negative")
    mentions = len(raw_posts)
    directional_total = max(1, pos_count + neg_count)
    polarity = (pos_count - neg_count) / directional_total
    score = int(max(0, min(100, round(50 + (polarity * 45)))))
    sentiment = "neutral"
    if polarity >= 0.20:
        sentiment = "positive"
    elif polarity <= -0.20:
        sentiment = "negative"

    mentions_24h = sum(1 for p in raw_posts if (_safe_float(p.get("created_utc")) or 0.0) >= since_24h)
    mentions_7d = sum(1 for p in raw_posts if (_safe_float(p.get("created_utc")) or 0.0) >= since_7d)
    confidence = int(
        max(
            0,
            min(
                100,
                round(
                    min(1.0, mentions / 25.0) * 70
                    + abs(polarity) * 30
                ),
            ),
        )
    )

    out.update(
        {
            "has_data": True,
            "sentiment": sentiment,
            "score": score,
            "confidence": confidence,
            "mentions_24h": mentions_24h,
            "mentions_7d": mentions_7d,
            "bullish_ratio": round(pos_count / mentions, 4) if mentions > 0 else 0.0,
            "bearish_ratio": round(neg_count / mentions, 4) if mentions > 0 else 0.0,
            "posts": [
                {
                    "title": p.get("title"),
                    "subreddit": p.get("subreddit"),
                    "url": p.get("url"),
                    "published_at": p.get("published_at"),
                    "sentiment": p.get("sentiment"),
                    "score": p.get("score"),
                    "num_comments": p.get("num_comments"),
                }
                for p in raw_posts[:max_items]
            ],
        }
    )
    return out


def build_asset_insights(ticker: str, history_data: pd.DataFrame, dcf_profile: str = "base") -> dict:
    fundamental = compute_fundamental_analysis(ticker, dcf_profile=dcf_profile)
    wyckoff = compute_wyckoff_causes_effects(history_data)
    os = compute_overbought_oversold(history_data)
    news = get_asset_news(ticker, max_items=12)
    social = get_reddit_social_sentiment(ticker, max_items=20)
    insider_activity = get_insider_activity(ticker, max_items=20)

    # Heuristic composite: this is not a calibrated probability.
    valuation = fundamental.get("valuation_summary", {})
    data_quality = fundamental.get("data_quality", {})
    revisions = fundamental.get("estimate_revisions", {})

    valuation_score = 50
    delta = _safe_float(valuation.get("delta_pct"))
    methods = len(valuation.get("available_methods", []))
    if delta is not None:
        valuation_score = 50 + int(max(-35, min(35, (-delta) * 140)))
    valuation_score += min(10, methods * 2)
    valuation_score = int(max(0, min(100, valuation_score)))

    technical_score = 50
    signal = (wyckoff.get("signal") or "").lower()
    if "confirmed_up" in signal:
        technical_score += 20
    elif "confirmed_down" in signal:
        technical_score -= 20
    elif "bullish_divergence" in signal:
        technical_score += 10
    elif "bearish_divergence" in signal:
        technical_score -= 10
    os_status = (os.get("status") or "").lower()
    if os_status == "oversold":
        technical_score += 8
    elif os_status == "overbought":
        technical_score -= 8
    technical_score = int(max(0, min(100, technical_score)))

    revisions_score = 50
    net_30 = _safe_int(revisions.get("summary", {}).get("net_30d"))
    if net_30 is not None:
        revisions_score = 50 + int(max(-20, min(20, net_30 * 3)))
    revisions_score = int(max(0, min(100, revisions_score)))

    news_score = 50
    if news:
        pos = sum(1 for n in news if (n.get("sentiment") or "").lower() == "positive")
        neg = sum(1 for n in news if (n.get("sentiment") or "").lower() == "negative")
        total = max(1, pos + neg)
        news_score = 50 + int(((pos - neg) / total) * 20)
    if social.get("has_data"):
        social_score = _safe_float(social.get("score"))
        if social_score is not None:
            news_score = int(round((news_score * 0.75) + (social_score * 0.25)))
    news_score = int(max(0, min(100, news_score)))

    quality_score = _safe_float(data_quality.get("score"))
    weights = {"valuation": 0.34, "technical": 0.24, "data_quality": 0.22,
               "estimate_revisions": 0.12, "news_sentiment": 0.08}
    breakdown = {
        "valuation": valuation_score if delta is not None else None,
        "technical": technical_score if os.get("rsi") is not None or wyckoff.get("series", {}).get("dates") else None,
        "data_quality": int(max(0, min(100, quality_score))) if quality_score is not None else None,
        "estimate_revisions": revisions_score if net_30 is not None else None,
        "news_sentiment": news_score if news or social.get("has_data") else None,
    }
    missing = [name for name, value in breakdown.items() if value is None]
    model_confidence_score = (
        int(round(sum((value if value is not None else 50) * weights[name]
                      for name, value in breakdown.items())))
        if len(missing) < len(weights) else None
    )
    model_confidence_label = (
        "unavailable" if model_confidence_score is None else
        "high" if model_confidence_score >= 70 else ("medium" if model_confidence_score >= 45 else "low")
    )

    model_confidence = {
        "score": model_confidence_score,
        "label": model_confidence_label,
        "breakdown": breakdown,
        "methodology": {
            "name": "Heuristic composite",
            "calibrated_probability": False,
            "weights": weights,
            "missing_components": missing,
            "missing_data_policy": "Unavailable components are shown as null and imputed at neutral 50 in the weighted sum. No score is produced when every component is unavailable.",
            "observed_weight": round(sum(weights[name] for name in weights if name not in missing), 2),
            "assumptions": ["Fixed weights and thresholds are heuristic, not statistically calibrated.",
                            "The score combines valuation, technical direction, data quality, revisions and lexical sentiment; it is not a probability or expected return."],
        },
    }

    # Quick Verdict: compact directional label with top reasons.
    quick_label = "unavailable" if model_confidence_score is None else "neutral"
    if model_confidence_score is not None and model_confidence_score >= 68:
        quick_label = "bullish"
    elif model_confidence_score is not None and model_confidence_score <= 38:
        quick_label = "bearish"

    reasons = []
    primary_model = (valuation.get("primary_model") or "").lower()
    if primary_model == "dcf":
        reasons.append("Primary valuation model is DCF (cash-flow based).")
    elif primary_model == "ev_to_sales":
        reasons.append("Primary valuation model is EV/Sales (suitable for loss-making profiles).")
    elif primary_model == "economic_value_added":
        reasons.append("Primary valuation model is EVA.")
    elif primary_model == "peter_lynch":
        reasons.append("Primary valuation model is Peter Lynch fair value.")
    if delta is not None:
        if delta <= -0.08:
            reasons.append(f"Price is {abs(delta) * 100:.1f}% below estimated fair value.")
        elif delta >= 0.08:
            reasons.append(f"Price is {abs(delta) * 100:.1f}% above estimated fair value.")
        else:
            reasons.append("Price is close to estimated fair value.")

    if "confirmed_up" in signal:
        reasons.append("Technical trend is confirmed up (Wyckoff).")
    elif "confirmed_down" in signal:
        reasons.append("Technical trend is confirmed down (Wyckoff).")
    elif "bullish_divergence" in signal:
        reasons.append("Bullish divergence detected in Wyckoff signal.")
    elif "bearish_divergence" in signal:
        reasons.append("Bearish divergence detected in Wyckoff signal.")

    if net_30 is not None:
        if net_30 > 0:
            reasons.append(f"Analyst estimate revisions are positive (net +{net_30} in 30d).")
        elif net_30 < 0:
            reasons.append(f"Analyst estimate revisions are negative (net {net_30} in 30d).")
        else:
            reasons.append("Analyst estimate revisions are neutral over the last 30 days.")

    if social.get("has_data"):
        social_sentiment = (social.get("sentiment") or "neutral").lower()
        social_conf = _safe_int(social.get("confidence")) or 0
        social_mentions = _safe_int(social.get("mentions_7d")) or 0
        if social_conf >= 45 and social_mentions >= 5:
            if social_sentiment == "positive":
                reasons.append(f"Reddit sentiment is positive ({social_mentions} mentions in 7d).")
            elif social_sentiment == "negative":
                reasons.append(f"Reddit sentiment is negative ({social_mentions} mentions in 7d).")

    if os_status == "oversold":
        reasons.append("RSI is in oversold territory; this does not establish a rebound probability.")
    elif os_status == "overbought":
        reasons.append("RSI is in overbought territory; the trend may persist.")

    if quality_score is None or quality_score < 55:
        reasons.append("Data quality is limited; treat valuation with caution.")

    if not reasons:
        reasons = ["Signal is mixed across valuation and technical factors."]

    quick_summary = (
        "Insufficient measured data for a heuristic composite."
        if quick_label == "unavailable"
        else "Bullish setup with supportive cross-signals."
        if quick_label == "bullish"
        else "Bearish setup with elevated downside risk."
        if quick_label == "bearish"
        else "Neutral setup with mixed signals."
    )
    quick_verdict = {
        "label": quick_label,
        "score": model_confidence_score,
        "summary": quick_summary,
        "reasons": reasons[:3],
    }

    # Prepare Price History for Overview Chart
    # We return the full history (or a reasonable subset, e.g. last 5-10 years)
    price_history = {
        "dates": [],
        "prices": [],
    }
    if history_data is not None and not history_data.empty:
        # Ensure extraction of Close prices
        # history_data is likely a DF with 'Close'.
        hist_close = history_data['Close'] if 'Close' in history_data.columns else history_data.iloc[:, 0]
        # Drop NaNs
        hist_close = hist_close.dropna()
        # Convert to list
        price_history["dates"] = [str(d.date()) for d in hist_close.index]
        price_history["prices"] = hist_close.values.tolist()

    return {
        "fundamental": fundamental,
        "wyckoff": wyckoff,
        "overbought_oversold": os,
        "insider_activity": insider_activity,
        "news": news,
        "social_sentiment": social,
        "price_history": price_history,
        "model_confidence": model_confidence,
        "quick_verdict": quick_verdict,
    }
