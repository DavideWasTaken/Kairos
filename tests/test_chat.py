import sys
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import chat_engine
import insights

FACTS = [{"metric": "historical_return_stats", "symbol": "TEST", "period_actual": {"start_date": "2020-01-01", "end_date": "2025-01-01"}, "results": {"cagr_pct": 8.2, "mean_calendar_year_return_pct": 9.1, "total_return_pct": 48.0}}]


class ChatTests(unittest.TestCase):
    def test_period_parsers_respect_explicit_units(self):
        for text, days in [("last 2 years", 730), ("last 6 months", 180), ("ultimi 2 anni", 730), ("last 3 weeks", 21), ("last 30 days", 30)]:
            with self.subTest(text=text):
                self.assertEqual(chat_engine._extract_days_maybe(text), days)
        self.assertIsNone(chat_engine._extract_years_maybe("return AAPL last 30 days"))
        self.assertIsNone(chat_engine._extract_years_maybe("return AAPL last 6 months"))
        self.assertEqual(chat_engine._extract_years_maybe("return AAPL last 5 years"), 5)

    def test_short_return_period_is_explicitly_unsupported(self):
        with patch.object(chat_engine, "_compute_verified_return_stats") as compute:
            for question in ["return AAPL last 30 days", "return AAPL last 6 months", "return AAPL last 2 weeks"]:
                facts = chat_engine._build_verified_facts(question, "MSFT")
                self.assertEqual(facts[0]["metric"], "historical_period_unsupported")
                self.assertIn("whole years", chat_engine._fallback_verified_answer(question, facts))
            compute.assert_not_called()

    def test_symbol_after_finance_stopword_wins_over_selected_ticker(self):
        with patch.object(chat_engine, "_compute_verified_return_stats", return_value=FACTS[0]) as compute:
            chat_engine._build_verified_facts("CAGR AAPL last 5 years", "MSFT")
            compute.assert_called_once_with("AAPL", 5)

    def test_constant_correlation_is_unavailable_and_json_serializable(self):
        prices = pd.Series([100.0] * 40, index=pd.date_range("2026-01-01", periods=40))
        with patch.object(chat_engine, "_download_yahoo_history", return_value=prices):
            self.assertIsNone(chat_engine._compute_verified_correlation_stats("AAPL", "MSFT", 5))
            facts = chat_engine._build_verified_facts("correlation AAPL MSFT last 5 years", None)
        self.assertEqual(facts[0]["metric"], "historical_correlation_stats_unavailable")
        json.dumps(facts, allow_nan=False)

    def test_all_history_paths_trim_to_requested_dates(self):
        frame = pd.DataFrame({"Close": range(1, 9)}, index=pd.date_range("2025-01-01", periods=8))
        start = datetime(2025, 1, 3, tzinfo=timezone.utc)
        end = datetime(2025, 1, 7, tzinfo=timezone.utc)
        for path in ("download", "period", "max"):
            provider = Mock()
            provider.history.side_effect = [pd.DataFrame(), frame] if path == "max" else [frame]
            with self.subTest(path=path), patch.object(chat_engine.yf, "download", return_value=frame if path == "download" else pd.DataFrame()), patch.object(chat_engine.yf, "Ticker", return_value=provider):
                result = chat_engine._download_yahoo_history("TEST", start, end)
                self.assertEqual(list(result.index), list(pd.date_range("2025-01-03", periods=4)))

    def test_calendar_year_mean_excludes_partial_last_year(self):
        prices = pd.Series([100.0, 110.0, 220.0], index=pd.to_datetime(["2023-12-31", "2024-12-31", "2025-06-30"]))
        with patch.object(chat_engine, "_download_yahoo_history", return_value=prices):
            result = chat_engine._compute_verified_return_stats("TEST", 3)
        self.assertAlmostEqual(result["results"]["mean_calendar_year_return_pct"], 10.0)
        self.assertEqual(result["results"]["calendar_year_samples"], 1)

    def test_fact_routing_never_calls_a_classifier(self):
        with patch.dict("os.environ", {"GROQ_API_KEY": "test-only-key"}), patch.object(chat_engine.requests, "post", side_effect=AssertionError("unexpected model request")), patch.object(chat_engine, "_compute_verified_return_stats", return_value=FACTS[0]):
            self.assertEqual(chat_engine._build_verified_facts("Average return for TEST over 5 years", "TEST"), FACTS)

    def test_no_key_is_offline(self):
        with patch.dict("os.environ", {"GROQ_API_KEY": ""}), patch.object(chat_engine, "_build_verified_facts", return_value=FACTS), patch.object(chat_engine.requests, "post", side_effect=AssertionError("network")):
            result = chat_engine.answer_financial_chat("Return for TEST")
        self.assertIsNone(result["explanation"])
        self.assertFalse(result["used_llm"])

    def test_missing_metrics_format_as_unavailable(self):
        fact = {**FACTS[0], "results": {"cagr_pct": 8.2, "mean_calendar_year_return_pct": None, "total_return_pct": 48}}
        self.assertIn("n/a", chat_engine._fallback_verified_answer("", [fact]))
        self.assertIn("n/a", chat_engine._fallback_verified_answer("", [{"metric": "historical_correlation_stats", "results": {}}]))

    def test_scan_passes_window_and_uses_full_summary(self):
        date = (datetime.now(timezone.utc) - timedelta(days=120)).date().isoformat()
        frame = pd.DataFrame([{"Text": "Purchase", "Shares": 10, "Value": 20, "Start Date": date} for _ in range(30)])
        provider = SimpleNamespace(insider_transactions=frame, insider_purchases=pd.DataFrame())
        with patch.object(chat_engine, "_fetch_us_equity_symbols", return_value=([{"symbol": "TEST"}], "curated_fallback")), patch.object(insights.yf, "Ticker", return_value=provider):
            result = chat_engine._compute_cap_segment_insider_activity("Top small cap insider purchases last 180 days")
        self.assertEqual(result["window_days"], 180)
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["purchase_count"], 30)
        self.assertEqual(result["results"][0]["purchase_value"], 600)


if __name__ == "__main__":
    unittest.main()
