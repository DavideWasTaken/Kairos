"""Small process-local cache of server-produced numerical dashboard summaries."""
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
import math
from threading import Lock
import time

# Only explicit numeric paths are eligible. News, provider prose and price arrays never enter.
FIELDS = {
    'current_price': ('fundamental', 'current_price'),
    'market_cap': ('fundamental', 'market_cap'),
    'trailing_pe': ('fundamental', 'trailing_pe'),
    'forward_pe': ('fundamental', 'forward_pe'),
    'revenue_growth_yoy': ('fundamental', 'revenue_growth_yoy'),
    'net_income_growth_yoy': ('fundamental', 'net_income_growth_yoy'),
    'dcf_intrinsic_value_per_share': ('fundamental', 'discounted_cash_flow', 'intrinsic_value_per_share'),
    'dcf_upside': ('fundamental', 'discounted_cash_flow', 'upside'),
    'dcf_base_fcf': ('fundamental', 'discounted_cash_flow', 'inputs', 'base_fcf'),
    'dcf_growth_rate': ('fundamental', 'discounted_cash_flow', 'inputs', 'growth_rate'),
    'dcf_discount_rate': ('fundamental', 'discounted_cash_flow', 'inputs', 'discount_rate'),
    'dcf_terminal_growth': ('fundamental', 'discounted_cash_flow', 'inputs', 'terminal_growth'),
    'dcf_projection_years': ('fundamental', 'discounted_cash_flow', 'inputs', 'projection_years'),
    'average_fair_value': ('fundamental', 'valuation_summary', 'average_fair_value'),
    'valuation_delta_pct': ('fundamental', 'valuation_summary', 'delta_pct'),
    'data_quality_score': ('fundamental', 'data_quality', 'score'),
    'rsi': ('overbought_oversold', 'rsi'),
    'heuristic_confidence_score': ('model_confidence', 'score'),
    'heuristic_observed_weight': ('model_confidence', 'methodology', 'observed_weight'),
}


def _number(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def _date(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value[:10]).date().isoformat()
    except ValueError:
        return None


def _summary(ticker, profile, payload):
    insights = payload.get('insights') or {}
    results = {}
    for name, path in FIELDS.items():
        value = insights
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        results[name] = _number(value)
        if name == 'valuation_delta_pct' and results[name] is not None:
            results[name] *= 100
    dates = (payload.get('current_trend') or {}).get('dates') or []
    fundamental = insights.get('fundamental') or {}
    currency = fundamental.get('currency')
    return {
        'metric': 'asset_overview', 'symbol': ticker, 'dcf_profile': profile,
        'captured_at': datetime.now(timezone.utc).isoformat(),
        'data_source': 'Synthetic demo fixture' if payload.get('demo_mode') else 'Yahoo Finance via yfinance; server dashboard calculations',
        'currency': currency if isinstance(currency, str) and len(currency) == 3 and currency.isalpha() else None,
        'period_actual': {'start_date': _date(dates[0]) if dates else None, 'end_date': _date(dates[-1]) if dates else None},
        'financial_periods': {key: _date((fundamental.get(key) or {}).get('period')) for key in ('latest_annual', 'latest_quarterly')},
        'heuristic_missing_components': [key for key in ('valuation', 'technical', 'data_quality', 'estimate_revisions', 'news_sentiment')
                                         if (insights.get('model_confidence', {}).get('breakdown') or {}).get(key) is None],
        'results': results, 'missing_data': [key for key, value in results.items() if value is None],
        'methodology': 'Dashboard values are computed from provider data. DCF and fair values are assumption-dependent estimates. Heuristic confidence is not a calibrated probability; unavailable components are imputed at neutral 50 when at least one component is observed. observed_weight gives the measured component coverage as a fraction. Valuation delta is (price - fair value) / fair value * 100. Rate inputs, growth and dcf_upside are fractions; valuation_delta_pct is percentage points. Capture time is not a market observation timestamp.',
    }


class SnapshotStore:
    def __init__(self, capacity=128, ttl_seconds=1800):
        self.capacity = capacity
        self.ttl_seconds = ttl_seconds
        self._items = OrderedDict()
        self._lock = Lock()

    def put(self, ticker, profile, payload):
        value = _summary(ticker, profile, payload)
        key = (ticker.upper(), profile)
        with self._lock:
            self._items[key] = (time.monotonic(), value)
            self._items.move_to_end(key)
            while len(self._items) > self.capacity:
                self._items.popitem(last=False)

    def get(self, ticker, profile):
        key = (ticker.upper(), profile)
        with self._lock:
            item = self._items.get(key)
            if not item:
                return None
            if time.monotonic() - item[0] >= self.ttl_seconds:
                del self._items[key]
                return None
            self._items.move_to_end(key)
            return deepcopy(item[1])


STORE = SnapshotStore()


def save_analysis_snapshot(ticker, profile, payload):
    STORE.put(ticker, profile, payload)


def get_analysis_snapshot(ticker, profile):
    return STORE.get(ticker, profile)
