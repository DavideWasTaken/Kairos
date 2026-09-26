import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

const server = await createServer({ server: { middlewareMode: true }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
after(() => server.close());
const render = async (path, props) => {
  const { default: Component } = await server.ssrLoadModule(path);
  return renderToStaticMarkup(React.createElement(Component, props));
};

test('calculated answer keeps its sources, dates and zero values without an AI explanation', async () => {
  const html = await render('/src/components/AnswerContent.jsx', {
    content: 'Total return: 0%.',
    facts: [{ metric: 'historical_return_stats', symbol: 'DEMO', data_source: 'Synthetic fixture',
      period_actual: { start_date: '2020-01-02', end_date: '2025-01-02' },
      results: { total_return_pct: 0, cagr_pct: null } }],
  });
  for (const text of ['Total return: 0%.', 'Synthetic fixture', '2020-01-02', '2025-01-02', '0.00%', 'Unavailable']) {
    assert.ok(html.includes(text), `Missing ${text}`);
  }
  assert.ok(!html.includes('AI-selected explanation'));
});

test('AI explanation is a separate labelled region and cannot replace the calculated answer', async () => {
  const html = await render('/src/components/AnswerContent.jsx', {
    content: 'Correlation: 0.75.', explanation: 'Historical association does not imply causation.', usedLlm: true,
    facts: [{ metric: 'historical_correlation_stats', data_source: 'Fixture', results: { correlation: 0.75 } }],
  });
  assert.match(html, /Correlation: 0.75\./);
  assert.match(html, /AI-selected explanation/);
  assert.match(html, /not a verified calculation/);
  assert.match(html, /Historical association does not imply causation/);
});

test('failed LLM response does not display an AI explanation', async () => {
  const html = await render('/src/components/AnswerContent.jsx', {
    content: 'No data.', explanation: 'Untrusted fallback.', usedLlm: false,
    facts: [{ metric: 'historical_return_stats_unavailable', reason: 'No history', data_source: 'Fixture' }],
  });
  assert.ok(!html.includes('Untrusted fallback.'));
  assert.match(html, /No history/);
});

test('insider fact cards retain filing dates and source alongside nested transactions', async () => {
  const html = await render('/src/components/AnswerContent.jsx', {
    content: 'One purchase.', facts: [{ metric: 'cap_segment_insider_activity', window_days: 30,
      data_source: 'Filings fixture', results: [{ symbol: 'TEST', purchase_count: 1,
        transactions: [{ insider: 'Example director', date: '2026-01-03', shares: 12 }] }] }],
  });
  for (const text of ['Filings fixture', '2026-01-03', 'Example director', 'TEST', '30']) assert.ok(html.includes(text));
});

test('heuristic score shows missing inputs explicitly and disclaims a probability interpretation', async () => {
  const html = await render('/src/components/HeuristicScore.jsx', { confidence: {
    score: null, breakdown: { valuation: null, technical: null, data_quality: null, revisions: null, news: null },
    methodology: { weights: { valuation: .34, technical: .24, data_quality: .22, revisions: .12, news: .08 },
      missing_data_policy: 'Exclude missing inputs.' },
  } });
  for (const text of ['Heuristic score', 'not a calibrated probability', '34%', '24%', '22%', '12%', '8%', 'Unavailable', 'Exclude missing inputs.']) {
    assert.ok(html.includes(text), `Missing ${text}`);
  }
  assert.ok(!html.includes('50/100'));
});

test('heuristic breakdown preserves real zero scores and backend weight names', async () => {
  const html = await render('/src/components/HeuristicScore.jsx', { confidence: {
    score: 0, breakdown: { estimate_revisions: 0, news_sentiment: 20 },
    methodology: { weights: { estimate_revisions: .12, news_sentiment: .08 } },
  } });
  assert.match(html, /0\/100/);
  assert.match(html, /20\/100/);
});

test('DCF renders numerical assumptions and scenario values supplied by the API', async () => {
  const html = await render('/src/components/InsightsPanel.jsx', { section: 'fundamental', insights: { fundamental: {
    has_data: true, discounted_cash_flow: {
      inputs: { base_fcf: 1000, growth_rate: .05, discount_rate: .09, terminal_growth: .02, projection_years: 10, shares_outstanding: 100 },
      scenarios: { bear: { weight: .25, growth_rate: .02, discount_rate: .1, terminal_growth: .017, intrinsic_value_per_share: 45.67 } },
    },
  } } });
  for (const text of ['DCF assumptions', 'not probabilities', '5.00%', '9.00%', '2.00%', '25.00%']) {
    assert.ok(html.includes(text), `Missing ${text}`);
  }
  assert.match(html, /45[.,]67/); // Currency values follow the runtime locale.
});

test('price-only overview does not imply unavailable income observations', async () => {
  const html = await render('/src/components/OverviewSection.jsx', { insights: {
    price_history: { dates: ['2024-01-02', '2024-01-03'], prices: [100, 102] },
    fundamental: { annual_trend: [{ period: '2024-01-02', net_income: null }], quarterly_trend: [] },
  } });
  assert.match(html, /Price History/);
  assert.match(html, /Net income observations are unavailable/);
  assert.ok(!html.includes('Price vs Net Income'));
  assert.ok(!html.includes('Green path and labels'));
});
