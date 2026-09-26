import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import requests
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import chat_engine
import main


def response(content=None, status=200):
    out = Mock(status_code=status)
    out.json.return_value = {'choices': [{'message': {'content': json.dumps(content)}}]}
    return out


class GroundedAssistantTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {'GROQ_API_KEY': 'private-test-key', 'GROQ_MODEL': 'test-model', 'KAIROS_DEMO': '0'}).start()
        patch.object(chat_engine.requests, 'post', side_effect=AssertionError('Unmocked AI boundary')).start()
        dates = pd.date_range(pd.Timestamp.now().normalize() - pd.Timedelta(days=800), periods=800)
        frame = pd.DataFrame({'Close': [100 + n / 10 for n in range(800)]}, index=dates)
        patch.object(chat_engine.yf, 'download', return_value=frame).start()
        patch.object(chat_engine.yf, 'Ticker', side_effect=AssertionError('Unexpected provider fallback')).start()

    def test_two_phase_plan_executes_real_calculation_and_cites_generated_commentary(self):
        with patch.object(chat_engine.requests, 'post', side_effect=[
            response({'operation': 'returns', 'ticker': 'MSFT', 'years': 2}),
            response({'explanation': 'Compounding and the available calendar years answer different questions.', 'evidence_ids': ['fact-1']}),
        ]) as post:
            result = chat_engine.answer_financial_chat('How has the software company grown?', 'AAPL', [{'role': 'user', 'content': 'I mean MSFT.'}])
        self.assertEqual(result['verified_facts'][0]['symbol'], 'MSFT')
        self.assertIn('CAGR', result['answer'])
        self.assertTrue(result['used_llm'])
        self.assertIn('different questions', result['explanation'])
        self.assertEqual(result['evidence_ids'], ['fact-1'])
        self.assertEqual(result['ai']['status'], 'used')
        self.assertEqual(post.call_count, 2)
        payload = post.call_args_list[1].kwargs['json']
        self.assertIn('period_actual', payload['messages'][1]['content'])
        self.assertIn('data_source', payload['messages'][1]['content'])
        self.assertLessEqual(payload['max_completion_tokens'], 1200)
        self.assertLessEqual(post.call_args.kwargs['timeout'], 20)
        self.assertNotIn('private-test-key', str(result))

    def test_invalid_plan_falls_back_without_executing_arbitrary_operations(self):
        for plan in [
            {'operation': 'shell', 'code': 'touch /tmp/a'},
            {'operation': 'returns', 'ticker': 'AAPL', 'years': 3, 'url': 'https://invalid'},
            {'operation': 'returns', 'ticker': '../bad', 'years': 3},
            {'operation': 'returns', 'ticker': 'AAPL', 'years': 101},
            {'operation': 'returns', 'ticker': 'AAPL', 'years': True},
            [{'operation': 'returns', 'ticker': 'AAPL', 'years': 3}],
        ]:
            with self.subTest(plan=plan), patch.object(chat_engine.requests, 'post', return_value=response(plan)) as post:
                result = chat_engine.answer_financial_chat('CAGR AAPL last 2 years', 'AAPL')
            self.assertIn('CAGR', result['answer'])
            self.assertFalse(result['used_llm'])
            self.assertEqual(result.get('ai', {}).get('code'), 'invalid_plan')
            self.assertEqual(post.call_count, 1)

    def test_commentary_rejects_unknown_references_and_extra_keys(self):
        for commentary in [
            {'explanation': 'Untrusted.', 'evidence_ids': ['made-up']},
            {'explanation': 'Untrusted.', 'evidence_ids': ['fact-1'], 'extra': 1},
            {'explanation': 'Untrusted.', 'evidence_ids': []},
        ]:
            with self.subTest(commentary=commentary), patch.object(chat_engine.requests, 'post', side_effect=[response({'operation': 'returns', 'ticker': 'AAPL', 'years': 2}), response(commentary)]):
                result = chat_engine.answer_financial_chat('Explain performance', 'AAPL')
            self.assertIsNone(result['explanation'])
            self.assertEqual(result.get('ai', {}).get('status'), 'partial')
            self.assertEqual(result['ai']['code'], 'invalid_commentary')
            self.assertTrue(result['used_llm'])

    def test_safe_provider_statuses_are_distinct(self):
        cases = [(401, 'authentication_failed'), (403, 'authentication_failed'), (404, 'model_unavailable'), (429, 'rate_limited'), (503, 'provider_unavailable')]
        for status, code in cases:
            with self.subTest(status=status), patch.object(chat_engine.requests, 'post', return_value=response({'secret': 'private-test-key'}, status)):
                result = chat_engine.answer_financial_chat('CAGR AAPL last 2 years', 'AAPL')
            self.assertEqual(result.get('ai', {}).get('code'), code)
            self.assertIn('CAGR', result['answer'])
            self.assertNotIn('private-test-key', str(result))
        for failure, code in [(requests.Timeout('private-test-key'), 'timeout'), (requests.ConnectionError('private-test-key'), 'transport_error')]:
            with patch.object(chat_engine.requests, 'post', side_effect=failure):
                result = chat_engine.answer_financial_chat('hello')
            self.assertEqual(result['ai']['code'], code)
            self.assertNotIn('private-test-key', str(result))

    def test_no_key_skips_both_ai_stages(self):
        with patch.dict(os.environ, {'GROQ_API_KEY': ''}), patch.object(chat_engine.requests, 'post') as post:
            result = chat_engine.answer_financial_chat('CAGR AAPL last 2 years', 'AAPL')
        self.assertEqual(result.get('ai', {}).get('status'), 'disabled')
        self.assertFalse(result['used_llm'])
        self.assertIn('CAGR', result['answer'])
        post.assert_not_called()

    def test_concepts_have_no_fabricated_verified_evidence(self):
        with patch.object(chat_engine.requests, 'post', side_effect=[response({'operation': 'concept', 'topic': 'CAGR'}), response({'explanation': 'CAGR measures the constant annual growth rate connecting two values.', 'evidence_ids': []})]):
            result = chat_engine.answer_financial_chat('What does CAGR mean?')
        self.assertEqual(result['verified_facts'], [])
        self.assertEqual(result['evidence_ids'], [])
        self.assertIn('constant annual', result['explanation'])
        self.assertIn('General concept', result['answer'])

    def test_api_capability_and_profile_contract(self):
        with patch.object(main, 'DEMO_MODE', False), TestClient(main.app) as client:
            health = client.get('/api/health').json()
            self.assertEqual(health.get('ai', {}).get('status'), 'configured')
            self.assertEqual(health['ai']['model'], 'test-model')
            self.assertEqual(client.post('/api/chat', json={'message': 'hello', 'dcf_profile': 'optimistic'}).status_code, 422)
        with patch.object(main, 'DEMO_MODE', True), patch.object(chat_engine.requests, 'post') as post, TestClient(main.app) as client:
            body = client.post('/api/chat', json={'message': 'returns', 'ticker': 'DEMO'}).json()
            self.assertEqual(body.get('ai', {}).get('status'), 'demo')
            self.assertEqual(body['verified_facts'][0]['id'], 'fact-1')
            post.assert_not_called()

    def test_explicit_request_cannot_be_changed_by_plan(self):
        cases = [
            ('CAGR AAPL last 6 months', {'operation': 'returns', 'ticker': 'AAPL', 'years': 1}, 'whole years'),
            ('CAGR AAPL last 2 years', {'operation': 'returns', 'ticker': 'MSFT', 'years': 2}, 'AAPL'),
            ('CAGR AAPL last 2 years', {'operation': 'returns', 'ticker': 'AAPL', 'years': 7}, 'AAPL'),
        ]
        for question, plan, expected in cases:
            with self.subTest(question=question, plan=plan), patch.object(chat_engine.requests, 'post', return_value=response(plan)) as post:
                result = chat_engine.answer_financial_chat(question, 'AAPL')
            self.assertIn(expected, result['answer'])
            self.assertFalse(result['used_llm'])
            self.assertLessEqual(post.call_count, 1)

    def test_explicit_index_and_compound_symbols_preserve_plan(self):
        for symbol in ('^GSPC', 'BRK-B', 'BRK.B', 'BTC-USD'):
            with self.subTest(symbol=symbol), patch.object(chat_engine.requests, 'post', side_effect=[response({'operation': 'returns', 'ticker': symbol, 'years': 2}), response({'explanation': 'The observed period defines this result.', 'evidence_ids': ['fact-1']})]):
                result = chat_engine.answer_financial_chat(f'CAGR {symbol} last 2 years')
            self.assertEqual(result['ai']['planning_status'], 'used')
            self.assertEqual(result['verified_facts'][0]['symbol'], symbol)

    def test_natural_short_periods_cannot_be_silently_changed_to_years(self):
        for question in ('What is AAPL return over the last month?', 'What is AAPL return over six months?', 'AAPL return last week', 'rendimento AAPL ultimo mese'):
            with self.subTest(question=question), patch.object(chat_engine.yf, 'download') as market, patch.object(chat_engine.requests, 'post', return_value=response({'operation': 'returns', 'ticker': 'AAPL', 'years': 1})):
                result = chat_engine.answer_financial_chat(question, 'AAPL')
                self.assertIn('whole years', result['answer'])
                self.assertFalse(result['used_llm'])
                market.assert_not_called()
        with patch.dict(os.environ, {'GROQ_API_KEY': ''}), patch.object(chat_engine.yf, 'download') as market:
            result = chat_engine.answer_financial_chat('What is AAPL return over the last month?', 'AAPL')
            self.assertIn('whole years', result['answer'])
            market.assert_not_called()
        with patch.object(chat_engine.requests, 'post', side_effect=[response({'operation': 'returns', 'ticker': 'AAPL', 'years': 5}), response({'explanation': 'The observed period is shorter than requested.', 'evidence_ids': ['fact-1']})]):
            result = chat_engine.answer_financial_chat('daily returns for AAPL over 5 years', 'AAPL')
            self.assertEqual(result['ai']['planning_status'], 'used')

    def test_client_facts_are_rejected(self):
        with TestClient(main.app) as client:
            result = client.post('/api/chat', json={'message': 'hello', 'snapshot': {'current_price': 999}})
        self.assertEqual(result.status_code, 422)

    def test_successful_overview_uses_only_cached_server_data_with_profile(self):
        import snapshot_store
        snapshot_store.save_analysis_snapshot('OVERVIEW', 'aggressive', {
            'insights': {'fundamental': {'current_price': 42, 'discounted_cash_flow': {'intrinsic_value_per_share': 50}}, 'news': [{'title': 'UNTRUSTED-PROVIDER-PROSE'}]},
            'current_trend': {'dates': ['2025-01-01', '2025-12-31']},
        })
        with patch.object(chat_engine.requests, 'post', side_effect=[response({'operation': 'asset_overview', 'ticker': 'OVERVIEW'}), response({'explanation': 'The model estimate depends on assumptions.', 'evidence_ids': ['fact-1']})]) as post:
            result = chat_engine.answer_financial_chat('Explain the DCF and RSI in this dashboard', 'OVERVIEW', dcf_profile='aggressive')
        fact = result['verified_facts'][0]
        self.assertEqual(fact['results']['current_price'], 42)
        self.assertEqual(fact['dcf_profile'], 'aggressive')
        self.assertEqual(fact['period_actual']['end_date'], '2025-12-31')
        self.assertIn('42.00', result['answer'])
        self.assertEqual(result['ai']['status'], 'used')
        sent = post.call_args.kwargs['json']['messages'][1]['content']
        self.assertIn('captured_at', sent)
        self.assertIn('missing_data', sent)
        self.assertNotIn('UNTRUSTED-PROVIDER-PROSE', sent)

    def test_commentary_transport_failure_keeps_accepted_plan_and_numbers(self):
        with patch.object(chat_engine.requests, 'post', side_effect=[response({'operation': 'returns', 'ticker': 'AAPL', 'years': 2}), requests.Timeout('secret-request')]):
            with self.assertLogs('chat_engine', level='WARNING') as logged:
                result = chat_engine.answer_financial_chat('CAGR AAPL last 2 years', 'AAPL')
        self.assertEqual(result['ai'], {'status': 'partial', 'code': 'timeout', 'planning_status': 'used', 'commentary_status': 'unavailable'})
        self.assertEqual(result['answer'], chat_engine._fallback_verified_answer('', result['verified_facts']))
        self.assertTrue(result['used_llm'])
        self.assertIsNone(result['explanation'])
        self.assertNotIn('secret-request', str(result) + str(logged.output))

    def test_malformed_and_truncated_provider_payloads_are_safe(self):
        bodies = [{}, {'choices': []}, {'choices': [{'message': {'content': 'x' * 12001}}]}, {'choices': [{'finish_reason': 'length', 'message': {'content': '{}'}}]}, {'choices': [{'message': {'content': 'not-json'}}]}]
        for body in bodies:
            out = response()
            out.json.return_value = body
            with self.subTest(body=str(body)[:100]), patch.object(chat_engine.requests, 'post', return_value=out) as post:
                result = chat_engine.answer_financial_chat('CAGR AAPL last 2 years', 'AAPL')
            self.assertEqual(result['ai']['code'], 'invalid_response')
            self.assertFalse(result['used_llm'])
            self.assertEqual(post.call_count, 1)

    def test_asset_overview_requires_server_snapshot(self):
        with patch.object(chat_engine.requests, 'post', return_value=response({'operation': 'asset_overview', 'ticker': 'NOSNAPSHOT'})) as post:
            result = chat_engine.answer_financial_chat('Explain this dashboard', 'NOSNAPSHOT')
        self.assertIn('analyze', result['answer'].lower())
        self.assertEqual(result['verified_facts'][0]['metric'], 'asset_overview_unavailable')
        self.assertEqual(post.call_count, 1)


if __name__ == '__main__':
    unittest.main()
