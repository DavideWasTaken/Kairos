"""Offline API integration checks: demo mode must never use external services."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import main
from fastapi.testclient import TestClient


class DemoAPITests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        patch.object(main, 'DEMO_MODE', True, create=True).start()
        for name in ('get_market_data', 'search_ticker', 'build_asset_insights', 'answer_financial_chat'):
            patch.object(main, name, side_effect=AssertionError('External boundary called in demo')).start()
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)

    def test_health_and_search_identify_synthetic_demo(self):
        self.assertTrue(self.client.get('/api/health').json().get('demo_mode'))
        response = self.client.get('/api/search', params={'q': 'demo'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]['symbol'], 'DEMO')

    def test_analysis_is_reproducible_and_contains_no_fabricated_fundamentals(self):
        one = self.client.get('/api/analyze/DEMO')
        two = self.client.get('/api/analyze/DEMO')
        self.assertEqual(one.status_code, 200)
        self.assertEqual(one.json(), two.json())
        body = one.json()
        self.assertTrue(body['demo_mode'])
        self.assertIn('synthetic', body['data_source'].lower())
        self.assertFalse(body['insights']['fundamental']['has_data'])
        self.assertIsNone(body['insights']['model_confidence']['score'])
        pattern = body['seasonality']['best_match_analog']
        self.assertLess(pattern['prediction_dates'][-1], body['current_trend']['dates'][0])
        json.dumps(body, allow_nan=False)

    def test_demo_does_not_mislabel_real_ticker(self):
        self.assertEqual(self.client.get('/api/analyze/AAPL').status_code, 400)

    def test_chat_exposes_computed_facts_without_model(self):
        response = self.client.post('/api/chat', json={'message': 'Show return statistics', 'ticker': 'DEMO'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['demo_mode'])
        self.assertFalse(body['used_llm'])
        self.assertIsNone(body['explanation'])
        self.assertIn('synthetic', body['verified_facts'][0]['data_source'].lower())

    def test_demo_chat_unsupported_data_is_explicit(self):
        response = self.client.post('/api/chat', json={'message': 'Show insider purchases', 'ticker': 'DEMO'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['verified_facts'], [])

    def test_oversized_chat_is_rejected(self):
        response = self.client.post('/api/chat', json={'message': 'x' * 4001})
        self.assertEqual(response.status_code, 422)


if __name__ == '__main__':
    unittest.main()
