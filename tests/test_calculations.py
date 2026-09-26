import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import insights
import market_data


class CalculationTests(unittest.TestCase):
    def test_rsi_one_direction_and_flat(self):
        for prices, expected in [(range(1, 40), 100), (range(40, 1, -1), 0), ([10] * 40, 50)]:
            with self.subTest(expected=expected):
                self.assertEqual(insights._compute_rsi(pd.Series(prices)).iloc[-1], expected)

    def test_single_symbol_preserves_ohlcv_in_both_multiindex_orders(self):
        fields = ["Open", "High", "Low", "Close", "Volume"]
        frame = pd.DataFrame([[1, 3, 0.5, 2, 100]], columns=fields, index=pd.date_range("2026-01-01", periods=1))
        for reverse in (False, True):
            download = frame.copy()
            download.columns = pd.MultiIndex.from_tuples([( "TEST", f) if reverse else (f, "TEST") for f in fields])
            with self.subTest(reverse=reverse), patch.object(market_data.yf, "download", return_value=download):
                pd.testing.assert_frame_equal(market_data.get_market_data("TEST"), frame)
                pd.testing.assert_frame_equal(market_data.get_current_trend("TEST"), frame)

    def test_only_explicit_purchase_records_are_buys(self):
        descriptions = ["Purchase", "Buy", "Stock Award", "Grant", "Gift", "Acquisition", "", "Sale", "Purchase through option exercise", "Purchase / Gift"]
        frame = pd.DataFrame([{"Text": text, "Shares": 100, "Start Date": "2026-01-01"} for text in descriptions])
        rows = insights._normalize_insider_transactions(frame)
        self.assertEqual([r["transaction_type"] for r in rows], ["Purchase", "Buy"])

    def test_insider_summary_counts_all_provider_rows_before_display_limit(self):
        date = (datetime.now(timezone.utc) - timedelta(days=120)).date().isoformat()
        frame = pd.DataFrame([{"Text": "Purchase", "Shares": 10, "Value": 20, "Start Date": date} for _ in range(30)])
        provider = SimpleNamespace(insider_transactions=frame, insider_purchases=pd.DataFrame())
        with patch.object(insights.yf, "Ticker", return_value=provider):
            result = insights.get_insider_activity("TEST", max_items=8, window_days=180)
        self.assertEqual(result["summary"]["purchase_count"], 30)
        self.assertEqual(result["summary"]["purchase_value"], 600)
        self.assertEqual(len(result["transactions"]), 8)
        self.assertTrue(result["transactions_truncated"])
        self.assertEqual(result["window_days"], 180)

    def _insights(self, quality=None):
        with patch.object(insights, "compute_fundamental_analysis", return_value={"data_quality": {"score": quality}}), patch.object(insights, "get_asset_news", return_value=[]), patch.object(insights, "get_reddit_social_sentiment", return_value={}), patch.object(insights, "get_insider_activity", return_value={}):
            return insights.build_asset_insights("TEST", pd.DataFrame())

    def test_missing_data_is_not_a_measured_neutral_score(self):
        result = self._insights()
        score = result["model_confidence"]
        self.assertIsNone(score["score"])
        self.assertEqual(score["label"], "unavailable")
        self.assertEqual(score["methodology"]["name"], "Heuristic composite")
        self.assertFalse(score["methodology"]["calibrated_probability"])
        self.assertAlmostEqual(sum(score["methodology"]["weights"].values()), 1)
        self.assertEqual(len(score["methodology"]["missing_components"]), 5)
        self.assertEqual(result["quick_verdict"]["label"], "unavailable")

    def test_zero_quality_is_preserved(self):
        self.assertEqual(self._insights(0)["model_confidence"]["breakdown"]["data_quality"], 0)

    def test_fundamentals_expose_dcf_assumptions_even_without_provider_data(self):
        provider = SimpleNamespace(info={}, fast_info={}, income_stmt=pd.DataFrame(), financials=pd.DataFrame())
        with patch.object(insights.yf, "Ticker", return_value=provider):
            result = insights.compute_fundamental_analysis("TEST")
        self.assertIn("limitations", result["discounted_cash_flow"])
        self.assertIn("risk_free_rate", result["discounted_cash_flow"]["assumptions"])

    def test_provider_errors_do_not_log_secrets(self):
        with patch.object(market_data.yf, "download", side_effect=RuntimeError("secret-token")), self.assertLogs("market_data", level="ERROR") as captured:
            self.assertTrue(market_data.get_market_data("TEST").empty)
        self.assertNotIn("secret-token", " ".join(captured.output))

    def test_rsi_interpretation_makes_no_unmeasured_probability_claim(self):
        history = pd.DataFrame({"Close": range(40, 0, -1)}, index=pd.date_range("2026-01-01", periods=40))
        result = insights.compute_overbought_oversold(history)
        self.assertNotIn("probability is elevated", result["interpretation"])


if __name__ == "__main__":
    unittest.main()
