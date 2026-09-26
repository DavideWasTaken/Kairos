import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import chat_engine
import main
from fastapi.testclient import TestClient


class SnapshotTests(unittest.TestCase):
    def test_analyze_populates_bounded_numeric_snapshot_and_preserves_observation_dates(self):
        with patch.object(main, 'DEMO_MODE', True), TestClient(main.app) as client:
            self.assertEqual(client.get('/api/analyze/DEMO', params={'dcf_profile': 'aggressive'}).status_code, 200)
        self.assertTrue(hasattr(chat_engine, 'get_analysis_snapshot'), 'Server snapshot store must exist')
        snapshot = chat_engine.get_analysis_snapshot('DEMO', 'aggressive')
        self.assertEqual(snapshot['dcf_profile'], 'aggressive')
        self.assertIn('captured_at', snapshot)
        self.assertIn('end_date', snapshot['period_actual'])
        self.assertIn('current_price', snapshot['missing_data'])
        self.assertNotIn('price_history', str(snapshot))
        self.assertNotIn('news', snapshot)

    def test_snapshot_ttl_capacity_copy_and_profile_isolation(self):
        self.assertTrue(hasattr(chat_engine, 'snapshot_store'), 'Bounded snapshot store must exist')
        store = chat_engine.snapshot_store.SnapshotStore(capacity=2, ttl_seconds=10)
        payload = {'ticker': 'TEST', 'data_source': 'Yahoo Finance via yfinance', 'insights': {'fundamental': {'current_price': 123, 'discounted_cash_flow': {'intrinsic_value_per_share': None}}, 'news': [{'title': 'UNTRUSTED_PROMPT'}]}, 'current_trend': {'dates': ['2025-01-01', '2025-02-01']}}
        with patch.object(chat_engine.snapshot_store.time, 'monotonic', return_value=10):
            store.put('TEST', 'base', payload)
            payload['insights']['fundamental']['current_price'] = 999
            one = store.get('TEST', 'base')
            self.assertEqual(one['results']['current_price'], 123)
            self.assertNotIn('UNTRUSTED_PROMPT', str(one))
            self.assertIsNone(store.get('TEST', 'aggressive'))
            one['results']['current_price'] = 444
            self.assertEqual(store.get('TEST', 'base')['results']['current_price'], 123)
            store.put('TWO', 'base', payload)
            store.put('THREE', 'base', payload)
            self.assertIsNone(store.get('TEST', 'base'))
        with patch.object(chat_engine.snapshot_store.time, 'monotonic', return_value=21):
            self.assertIsNone(store.get('THREE', 'base'))

    def test_valuation_ratio_converts_to_percentage_points(self):
        store = chat_engine.snapshot_store.SnapshotStore()
        store.put('TEST', 'base', {'insights': {'fundamental': {'valuation_summary': {'delta_pct': 0.2}}}})
        self.assertEqual(store.get('TEST', 'base')['results']['valuation_delta_pct'], 20)

    def test_heuristic_snapshot_preserves_observed_coverage(self):
        store = chat_engine.snapshot_store.SnapshotStore()
        store.put('TEST', 'base', {'insights': {'model_confidence': {'score': 60, 'breakdown': {'valuation': None, 'technical': 70}, 'methodology': {'observed_weight': 0.66, 'missing_components': ['valuation', 'arbitrary-provider-prose']}}}})
        fact = store.get('TEST', 'base')
        self.assertEqual(fact['results'].get('heuristic_observed_weight'), 0.66)
        self.assertIn('valuation', fact.get('heuristic_missing_components', []))
        self.assertNotIn('arbitrary-provider-prose', str(fact))
