import React from 'react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Info } from 'lucide-react';
import { formatDateIt, formatDateShortIt, formatDateTimeIt } from '../utils/dateFormat';
const EMPTY_NEWS = [];

const formatCompact = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  const n = Number(value);
  const abs = Math.abs(n);
  if (abs >= 1_000_000_000_000) return `${(n / 1_000_000_000_000).toFixed(2)}T`;
  if (abs >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(2)}B`;
  if (abs >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `${(n / 1_000).toFixed(2)}K`;
  return n.toFixed(2);
};

const formatPct = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return `${(Number(value) * 100).toFixed(2)}%`;
};

const formatMultiple = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return `${Number(value).toFixed(2)}x`;
};

const formatSigned = (value, digits = 3) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  const n = Number(value);
  return `${n > 0 ? '+' : ''}${n.toFixed(digits)}`;
};

const formatPrice = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

const formatCount = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 });
};

const formatRevisionPeriodLabel = (period) => {
  const p = String(period || '').trim().toLowerCase();
  if (!p) return '-';
  const map = {
    '0q': 'Current quarter (0Q)',
    '+1q': 'Next quarter (+1Q)',
    '-1q': 'Previous quarter (-1Q)',
    '0y': 'Current fiscal year (0Y)',
    '+1y': 'Next fiscal year (+1Y)',
    '-1y': 'Previous fiscal year (-1Y)',
  };
  return map[p] || String(period);
};

const statusColor = (status) => {
  if (status === 'overbought') return 'text-red-500';
  if (status === 'oversold') return 'text-green-500';
  if (status && status.includes('divergence')) return 'text-yellow-500';
  if (status && status.includes('confirmed')) return 'text-blue-500';
  if (status === 'positive') return 'text-green-500';
  if (status === 'negative') return 'text-red-500';
  return 'text-muted-foreground';
};

const DCF_PROFILES = [
  { id: 'conservative', label: 'Conservative' },
  { id: 'base', label: 'Base' },
  { id: 'aggressive', label: 'Aggressive' },
];

const DCF_PROFILE_INFO = {
  conservative: {
    title: 'Conservative',
    useWhen: 'Use for cyclical or lower-visibility businesses.',
    assumptions: 'Lower growth, higher discount rate, shorter horizon.',
  },
  base: {
    title: 'Base',
    useWhen: 'Use as default for stable, quality companies.',
    assumptions: 'Balanced growth and discount assumptions.',
  },
  aggressive: {
    title: 'Aggressive',
    useWhen: 'Use for high-quality compounders with strong visibility.',
    assumptions: 'Higher growth, lower discount rate, longer horizon.',
  },
};

const FundamentalSection = ({ fundamental, dcfProfile, onDcfProfileChange, isLoading }) => {
  const [trendView, setTrendView] = React.useState('annual');
  const annualTrend = fundamental.annual_trend || [];
  const quarterlyTrend = fundamental.quarterly_trend || [];
  const hasQuarterlyTrend = quarterlyTrend.length > 0;
  const effectiveTrendView = trendView === 'quarterly' && hasQuarterlyTrend ? 'quarterly' : 'annual';
  const trendSource = effectiveTrendView === 'quarterly' ? quarterlyTrend : annualTrend;
  const dcf = fundamental.discounted_cash_flow || {};
  const evSales = fundamental.ev_to_sales || {};
  const revisions = fundamental.estimate_revisions || {};
  const fundamentalChartData = trendSource.map((row) => ({
    period: effectiveTrendView === 'quarterly'
      ? String(row.period || '').slice(0, 10)
      : String(row.period || '').slice(0, 4),
    revenueB: row.revenue !== null && row.revenue !== undefined ? Number(row.revenue) / 1_000_000_000 : null,
    netIncomeB: row.net_income !== null && row.net_income !== undefined ? Number(row.net_income) / 1_000_000_000 : null,
    netMarginPct: row.net_margin !== null && row.net_margin !== undefined ? Number(row.net_margin) * 100 : null,
  }));

  const dcfMethodNote = (() => {
    const view = dcf.valuation_view;
    if (view === 'undervalued') return 'Intrinsic value is above market price (potentially undervalued).';
    if (view === 'overvalued') return 'Intrinsic value is below market price (potentially overvalued).';
    if (view === 'fairly_valued') return 'Intrinsic value is close to current market price.';
    return 'DCF = PV of projected FCF (8/10/12 years by profile) + discounted terminal value.';
  })();
  const evSalesMethodNote = 'EV/Sales = Enterprise Value / Revenue. Target multiple blends current EV/Sales with a heuristic from revenue growth and net margin.';

  const selectedProfile = (dcfProfile || fundamental.dcf_profile || 'base').toLowerCase();
  const profileInfo = DCF_PROFILE_INFO[selectedProfile] || DCF_PROFILE_INFO.base;
  const primaryModelKey = dcf.intrinsic_value_per_share !== null && dcf.intrinsic_value_per_share !== undefined
    ? 'dcf'
    : 'ev_to_sales';
  const valuationCards = [
    {
      key: 'dcf',
      modelKey: 'dcf',
      label: 'Discounted Cash Flow',
      value: dcf.intrinsic_value_per_share,
      hint: `${dcf.inputs?.projection_years || 10}y • WACC ${formatPct(dcf.inputs?.discount_rate)} • g ${formatPct(dcf.inputs?.growth_rate)}`,
      note: dcfMethodNote,
    },
    {
      key: 'evsales',
      modelKey: 'ev_to_sales',
      label: 'EV / Sales',
      value: evSales.fair_value_per_share,
      hint: `Current ${formatMultiple(evSales.ratio)} • Target ${formatMultiple(evSales.target_multiple)}`,
      note: evSalesMethodNote,
    },
  ]
    .sort((a, b) => {
      if (a.modelKey === primaryModelKey) return -1;
      if (b.modelKey === primaryModelKey) return 1;
      return 0;
    })
    .map((card, idx) => ({
      ...card,
      badge: card.modelKey === primaryModelKey ? 'Primary' : idx === 1 ? 'Secondary' : null,
    }));
  const revUp30 = Number(revisions?.summary?.up_30d || 0);
  const revDown30 = Number(revisions?.summary?.down_30d || 0);
  const revNet30 = Number.isFinite(Number(revisions?.summary?.net_30d))
    ? Number(revisions.summary.net_30d)
    : revUp30 - revDown30;
  const revTotal30 = Math.max(1, revUp30 + revDown30);
  const revMomentumPct = Math.round((Math.abs(revNet30) / revTotal30) * 100);
  const revSignal = revNet30 > 0 ? 'positive' : revNet30 < 0 ? 'negative' : 'neutral';
  const revSignalText = revSignal === 'positive'
    ? 'Analyst revisions are improving.'
    : revSignal === 'negative'
      ? 'Analyst revisions are weakening.'
      : 'Analyst revisions are balanced.';

  return (
    <div className="bg-card p-4 rounded-xl border border-border shadow-sm">
      <div className="mb-3 flex flex-col md:flex-row md:items-center md:justify-between gap-2">
        <h3 className="text-lg font-semibold">Fundamental Analysis</h3>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">DCF Profile</span>
          <div className="inline-flex rounded-lg border border-border overflow-hidden">
            {DCF_PROFILES.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => onDcfProfileChange?.(p.id)}
                disabled={isLoading}
                className={`px-3 py-1.5 text-xs transition-colors ${(dcfProfile || 'base') === p.id
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
                  } ${isLoading ? 'opacity-60 cursor-not-allowed' : ''}`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="mb-4 rounded-lg border border-border bg-background/30 p-3">
        <div className="flex items-start gap-2">
          <Info className="h-4 w-4 mt-0.5 text-muted-foreground" />
          <div className="text-xs text-muted-foreground leading-relaxed">
            <span className="font-medium text-foreground">DCF InfoLog ({profileInfo.title})</span>
            {' '}| {profileInfo.useWhen}
            {' '}| {profileInfo.assumptions}
            {' '}| Best practice: use Base as reference, then compare Conservative and Aggressive as a valuation range.
          </div>
        </div>
      </div>
      {!fundamental.has_data ? (
        <div className="text-sm text-muted-foreground">Fundamental statement data is not available for this asset.</div>
      ) : (
        <>
          <details className="mb-4 rounded-lg border border-border bg-background/30 p-3 text-xs">
            <summary className="cursor-pointer font-medium">DCF assumptions &amp; scenarios</summary>
            <p className="mt-2 text-muted-foreground">Illustrative valuation driven by growth, discount rate and terminal value assumptions. Scenario weights are fixed modelling choices, not probabilities. Estimates are sensitive to these inputs and are not price predictions.</p>
            <div className="mt-2 grid grid-cols-2 md:grid-cols-3 gap-2 text-muted-foreground">
              <div>Base free cash flow: {formatCompact(dcf.inputs?.base_fcf)}</div>
              <div>Projection horizon: {dcf.inputs?.projection_years ?? '-'} years</div>
              <div>Growth rate: {formatPct(dcf.inputs?.growth_rate)}</div>
              <div>Discount rate: {formatPct(dcf.inputs?.discount_rate)}</div>
              <div>Terminal growth: {formatPct(dcf.inputs?.terminal_growth)}</div>
              <div>Shares outstanding: {formatCompact(dcf.inputs?.shares_outstanding)}</div>
            </div>
            {Object.keys(dcf.scenarios || {}).length > 0 && (
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-left">
                  <thead><tr>{['Scenario', 'Weight', 'Growth', 'Discount rate', 'Terminal growth', 'Value / share'].map((name) => <th key={name} className="p-2 font-medium">{name}</th>)}</tr></thead>
                  <tbody>{Object.entries(dcf.scenarios).map(([name, scenario]) => (
                    <tr key={name} className="border-t border-border">
                      <th className="p-2 font-medium capitalize">{name}</th>
                      <td className="p-2">{formatPct(scenario.weight)}</td>
                      <td className="p-2">{formatPct(scenario.growth_rate)}</td>
                      <td className="p-2">{formatPct(scenario.discount_rate)}</td>
                      <td className="p-2">{formatPct(scenario.terminal_growth)}</td>
                      <td className="p-2">{formatPrice(scenario.intrinsic_value_per_share)}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
          </details>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
            <div className="rounded-lg border border-border p-3">
              <div className="text-xs text-muted-foreground">Revenue (Latest Annual)</div>
              <div className="text-lg font-semibold">{formatCompact(fundamental.latest_annual?.revenue)}</div>
            </div>
            <div className="rounded-lg border border-border p-3">
              <div className="text-xs text-muted-foreground">Net Income (Latest Annual)</div>
              <div className="text-lg font-semibold">{formatCompact(fundamental.latest_annual?.net_income)}</div>
            </div>
            <div className="rounded-lg border border-border p-3">
              <div className="text-xs text-muted-foreground">Net Margin</div>
              <div className="text-lg font-semibold">{formatPct(fundamental.latest_annual?.net_margin)}</div>
            </div>
            <div className="rounded-lg border border-border p-3">
              <div className="text-xs text-muted-foreground">Revenue YoY</div>
              <div className={`text-lg font-semibold ${Number(fundamental.revenue_growth_yoy) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                {formatPct(fundamental.revenue_growth_yoy)}
              </div>
            </div>
            <div className="rounded-lg border border-border p-3">
              <div className="text-xs text-muted-foreground">Net Income YoY</div>
              <div className={`text-lg font-semibold ${Number(fundamental.net_income_growth_yoy) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                {formatPct(fundamental.net_income_growth_yoy)}
              </div>
            </div>
            <div className="rounded-lg border border-border p-3">
              <div className="text-xs text-muted-foreground">Market Cap</div>
              <div className="text-lg font-semibold">{formatCompact(fundamental.market_cap)}</div>
            </div>
          </div>

          <div className="text-xs text-muted-foreground mb-4">
            Statement currency: {fundamental.currency || 'N/A'} | P/E: {fundamental.trailing_pe ?? '-'} | Forward P/E:{' '}
            {fundamental.forward_pe ?? '-'} | P/B: {fundamental.price_to_book ?? '-'}
          </div>

          <div className="rounded-lg border border-border bg-background/30 p-3 mb-4">
            <div className="text-sm font-medium">Estimate Revisions</div>
            {!revisions?.has_data ? (
              <div className="mt-2 text-xs text-muted-foreground">No estimate revision dataset available for this asset.</div>
            ) : (
              <>
                <div className="mt-2 rounded border border-border p-3">
                  <div className="text-xs text-muted-foreground">Simple signal (last 30 days)</div>
                  <div className={`mt-1 text-lg font-semibold ${statusColor(revSignal)}`}>
                    {revSignal === 'positive' ? 'Bullish' : revSignal === 'negative' ? 'Bearish' : 'Neutral'}
                  </div>
                  <div className="mt-1 text-sm text-muted-foreground">{revSignalText}</div>
                  <div className="mt-2 text-xs text-muted-foreground">
                    Up revisions: <span className="text-foreground font-medium">{revUp30}</span> | Down revisions: <span className="text-foreground font-medium">{revDown30}</span> | Net: <span className={`font-medium ${revNet30 >= 0 ? 'text-green-500' : 'text-red-500'}`}>{revNet30}</span>
                  </div>
                  <div className="mt-2">
                    <div className="h-2 w-full rounded bg-muted overflow-hidden">
                      <div
                        className={`h-full ${revSignal === 'positive' ? 'bg-green-500' : revSignal === 'negative' ? 'bg-red-500' : 'bg-yellow-500'}`}
                        style={{ width: `${Math.min(100, Math.max(6, revMomentumPct))}%` }}
                      />
                    </div>
                    <div className="mt-1 text-[11px] text-muted-foreground">
                      Momentum strength: {revMomentumPct}% (based on net revisions vs total revisions)
                    </div>
                  </div>
                </div>
                {(revisions.rows || []).length > 0 && (
                  <div className="mt-2 rounded border border-border p-2 text-xs text-muted-foreground">
                    Main impact period: <span className="text-foreground">{formatRevisionPeriodLabel(revisions.rows[0]?.period)}</span>
                  </div>
                )}
              </>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
            {valuationCards.map((card) => (
              <div key={card.key} className="rounded-lg border border-border bg-background/30 p-4 text-center">
                <div className="text-xs md:text-sm text-muted-foreground">
                  {card.label}
                  {card.badge ? (
                    <span className="ml-2 inline-flex items-center rounded-full border border-border px-2 py-0.5 text-[10px] text-foreground">
                      {card.badge}
                    </span>
                  ) : null}
                </div>
                <div className="mt-1 text-3xl font-bold tracking-tight text-foreground">
                  {formatPrice(card.value)}
                </div>
                <div className="mt-2 flex items-center justify-center gap-1 text-xs text-muted-foreground">
                  <span>{card.hint}</span>
                  {card.note && (
                    <div className="relative group">
                      <button
                        type="button"
                        className="inline-flex items-center justify-center rounded-full text-muted-foreground hover:text-foreground focus:outline-none"
                        aria-label={`${card.label} formula`}
                      >
                        <Info className="h-3.5 w-3.5" />
                      </button>
                      <div className="pointer-events-none absolute left-1/2 top-full z-20 mt-2 w-72 -translate-x-1/2 rounded-md border border-border bg-popover p-2 text-left text-[11px] leading-snug text-popover-foreground opacity-0 shadow-lg transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
                        {card.note}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          {fundamentalChartData.length > 0 && (
            <div>
              <div className="mb-2 flex justify-end">
                <div className="inline-flex rounded-lg border border-border overflow-hidden">
                  <button
                    type="button"
                    onClick={() => setTrendView('annual')}
                    className={`px-3 py-1.5 text-xs transition-colors ${
                      effectiveTrendView === 'annual'
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
                    }`}
                  >
                    Annual
                  </button>
                  <button
                    type="button"
                    onClick={() => setTrendView('quarterly')}
                    disabled={!hasQuarterlyTrend}
                    className={`px-3 py-1.5 text-xs transition-colors ${
                      effectiveTrendView === 'quarterly'
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
                    } ${!hasQuarterlyTrend ? 'opacity-50 cursor-not-allowed' : ''}`}
                  >
                    Quarterly
                  </button>
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="h-[260px] rounded-lg border border-border p-2">
                <div className="text-sm font-medium px-2 pt-1">
                  {effectiveTrendView === 'quarterly' ? 'Quarterly' : 'Annual'} Revenue vs Net Income
                </div>
                <ResponsiveContainer width="100%" height="90%">
                  <LineChart data={fundamentalChartData} margin={{ top: 8, right: 20, left: 10, bottom: 16 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
                    <XAxis dataKey="period" tick={{ fontSize: 12 }} />
                    <YAxis tick={{ fontSize: 12 }} tickFormatter={(v) => `${v.toFixed(0)}B`} />
                    <Tooltip
                      labelFormatter={(label) => `Year: ${label}`}
                      formatter={(value, name) => [`${Number(value).toFixed(2)}B`, name]}
                    />
                    <Legend />
                    <Line type="monotone" dataKey="revenueB" name="Revenue (B)" stroke="#3b82f6" strokeWidth={2.5} dot={false} connectNulls />
                    <Line type="monotone" dataKey="netIncomeB" name="Net Income (B)" stroke="#10b981" strokeWidth={2.5} dot={false} connectNulls />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              <div className="h-[260px] rounded-lg border border-border p-2">
                <div className="text-sm font-medium px-2 pt-1">
                  {effectiveTrendView === 'quarterly' ? 'Quarterly' : 'Annual'} Net Margin Trend
                </div>
                <ResponsiveContainer width="100%" height="90%">
                  <LineChart data={fundamentalChartData} margin={{ top: 8, right: 20, left: 10, bottom: 16 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
                    <XAxis dataKey="period" tick={{ fontSize: 12 }} />
                    <YAxis tick={{ fontSize: 12 }} tickFormatter={(v) => `${v.toFixed(0)}%`} />
                    <Tooltip
                      labelFormatter={(label) => `Year: ${label}`}
                      formatter={(value, name) => [`${Number(value).toFixed(2)}%`, name]}
                    />
                    <ReferenceLine y={0} stroke="#6b7280" strokeDasharray="4 4" />
                    <Line type="monotone" dataKey="netMarginPct" name="Net Margin %" stroke="#f59e0b" strokeWidth={2.5} dot={false} connectNulls />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};

const TechnicalSection = ({ wyckoff, os }) => {
  const wyckoffSeries = wyckoff.series || { dates: [], price: [], price_norm: [], wyckoff_line: [] };
  const wyckoffChartData = wyckoffSeries.dates.map((date, i) => ({
    date,
    price: wyckoffSeries.price[i],
    priceNorm: wyckoffSeries.price_norm[i],
    wyckoffLine: wyckoffSeries.wyckoff_line[i],
  }));

  const wyLast = wyckoffChartData.length ? wyckoffChartData[wyckoffChartData.length - 1] : null;

  const osHistory = os.history || { dates: [], rsi: [] };
  const osChartData = osHistory.dates.map((date, i) => ({
    date,
    rsi: osHistory.rsi[i],
  }));

  return (
    <div className="grid grid-cols-1 gap-4">
      <div className="bg-card p-4 rounded-xl border border-border shadow-sm">
        <h3 className="text-lg font-semibold mb-1">Wyckoff</h3>
        <div className="text-sm text-muted-foreground mb-3">{wyckoff.interpretation || 'No signal available.'}</div>
        <div className={`text-sm font-medium mb-3 ${statusColor(wyckoff.signal)}`}>
          Signal: {(wyckoff.signal || 'neutral').replaceAll('_', ' ')}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
          <div className="rounded-lg border border-border p-3">
            <div className="text-xs text-muted-foreground">Latest Wyckoff</div>
            <div className={`text-lg font-semibold ${(wyLast?.wyckoffLine ?? 0) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
              {wyLast ? formatSigned(wyLast.wyckoffLine, 2) : '-'}
            </div>
          </div>
          <div className="rounded-lg border border-border p-3">
            <div className="text-xs text-muted-foreground">Price Slope (30d)</div>
            <div className={`text-lg font-semibold ${Number(wyckoff.price_slope) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
              {formatSigned(wyckoff.price_slope, 4)}
            </div>
          </div>
          <div className="rounded-lg border border-border p-3">
            <div className="text-xs text-muted-foreground">Wyckoff Slope (30d)</div>
            <div className={`text-lg font-semibold ${Number(wyckoff.wyckoff_slope) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
              {formatSigned(wyckoff.wyckoff_slope, 4)}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3">
          <div className="h-[300px] rounded-lg border border-border p-2">
            <div className="text-xs font-medium text-muted-foreground px-1">Asset Price (Close)</div>
            <ResponsiveContainer width="100%" height="88%">
              <LineChart
                data={wyckoffChartData}
                syncId="wyckoff-sync"
                margin={{ top: 8, right: 16, left: 10, bottom: 8 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
                <XAxis dataKey="date" hide />
                <YAxis
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v) => formatCompact(v)}
                  domain={[
                    (dataMin) => dataMin - Math.abs(dataMin) * 0.01,
                    (dataMax) => dataMax + Math.abs(dataMax) * 0.01,
                  ]}
                />
                <Tooltip
                  cursor={{ stroke: '#94a3b8', strokeDasharray: '4 4' }}
                  content={() => null}
                />
                <Line type="monotone" dataKey="price" name="Close Price" stroke="#94a3b8" strokeWidth={2.2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="h-[300px] rounded-lg border border-border p-2">
            <div className="text-xs font-medium text-muted-foreground px-1">Wyckoff Causes/Effects Line</div>
            <ResponsiveContainer width="100%" height="88%">
              <LineChart
                data={wyckoffChartData}
                syncId="wyckoff-sync"
                margin={{ top: 8, right: 16, left: 10, bottom: 8 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11 }}
                  minTickGap={42}
                  tickFormatter={(v) => formatDateShortIt(v)}
                />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip
                  cursor={{ stroke: '#94a3b8', strokeDasharray: '4 4' }}
                  content={() => null}
                />
                <Legend />
                <ReferenceLine y={0} stroke="#6b7280" strokeDasharray="4 4" />
                <Line type="monotone" dataKey="wyckoffLine" name="Wyckoff Line" stroke="#22d3ee" strokeWidth={2.6} dot={false} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="bg-card p-4 rounded-xl border border-border shadow-sm">
        <h3 className="text-lg font-semibold mb-1">Overbought / Oversold</h3>
        <div className={`text-sm font-medium mb-3 ${statusColor(os.status)}`}>
          Status: {(os.status || 'neutral').replaceAll('_', ' ')}
        </div>
        <div className="grid grid-cols-1 gap-3 mb-4">
          <div className="rounded-lg border border-border p-3">
            <div className="text-xs text-muted-foreground">RSI (14)</div>
            <div className="text-lg font-semibold">{os.rsi !== null && os.rsi !== undefined ? Number(os.rsi).toFixed(2) : '-'}</div>
          </div>
        </div>
        <div className="h-[360px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={osChartData} margin={{ top: 10, right: 20, left: 10, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 12 }}
                minTickGap={40}
                tickFormatter={(v) => formatDateShortIt(v)}
              />
              <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} />
              <Tooltip
                labelFormatter={(label) => `Date: ${formatDateIt(label)}`}
                formatter={(value, name) => [Number(value).toFixed(2), name]}
              />
              <Legend />
              <ReferenceLine y={70} stroke="#ef4444" strokeDasharray="4 4" />
              <ReferenceLine y={30} stroke="#22c55e" strokeDasharray="4 4" />
              <Line type="monotone" dataKey="rsi" name="RSI" stroke="#f59e0b" strokeWidth={2.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};

const NewsSection = ({ news, ticker, earningsEvents, socialSentiment }) => {
  const safeNews = Array.isArray(news) ? news : EMPTY_NEWS;
  const [newsFilter, setNewsFilter] = React.useState('all');

  const sentimentStats = React.useMemo(() => {
    const stats = { total: safeNews.length, positive: 0, neutral: 0, negative: 0 };
    safeNews.forEach((item) => {
      const s = String(item?.sentiment || 'neutral').toLowerCase();
      if (s === 'positive') stats.positive += 1;
      else if (s === 'negative') stats.negative += 1;
      else stats.neutral += 1;
    });
    return stats;
  }, [safeNews]);

  const filteredNews = React.useMemo(() => {
    if (newsFilter === 'all') return safeNews;
    return safeNews.filter((item) => String(item?.sentiment || 'neutral').toLowerCase() === newsFilter);
  }, [safeNews, newsFilter]);

  const dominantNewsSignal = React.useMemo(() => {
    if (sentimentStats.total === 0) return 'neutral';
    if (sentimentStats.positive > sentimentStats.negative) return 'positive';
    if (sentimentStats.negative > sentimentStats.positive) return 'negative';
    return 'neutral';
  }, [sentimentStats]);

  const sentimentBadgeClass = (sentiment) => {
    const s = String(sentiment || 'neutral').toLowerCase();
    if (s === 'positive') return 'border-green-500/30 bg-green-500/10 text-green-400';
    if (s === 'negative') return 'border-red-500/30 bg-red-500/10 text-red-400';
    return 'border-yellow-500/30 bg-yellow-500/10 text-yellow-300';
  };

  const filters = [
    { id: 'all', label: 'All', count: sentimentStats.total },
    { id: 'positive', label: 'Positive', count: sentimentStats.positive },
    { id: 'neutral', label: 'Neutral', count: sentimentStats.neutral },
    { id: 'negative', label: 'Negative', count: sentimentStats.negative },
  ];

  return (
    <div className="space-y-4">
      <div className="bg-card p-4 rounded-xl border border-border shadow-sm">
        <div className="flex flex-col gap-1 md:flex-row md:items-end md:justify-between">
          <div>
            <h3 className="text-lg font-semibold">News Radar ({ticker})</h3>
            <div className="text-xs text-muted-foreground">Live feed from free sources with sentiment tagging.</div>
          </div>
          <div className={`text-sm font-semibold ${statusColor(dominantNewsSignal)}`}>
            Signal: {dominantNewsSignal}
          </div>
        </div>
        <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2">
          <div className="rounded-lg border border-border p-2.5">
            <div className="text-[11px] text-muted-foreground">Headlines</div>
            <div className="text-base font-semibold">{sentimentStats.total}</div>
          </div>
          <div className="rounded-lg border border-border p-2.5">
            <div className="text-[11px] text-muted-foreground">Positive / Negative</div>
            <div className="text-base font-semibold">{sentimentStats.positive} / {sentimentStats.negative}</div>
          </div>
          <div className="rounded-lg border border-border p-2.5">
            <div className="text-[11px] text-muted-foreground">Next Event</div>
            <div className="text-base font-semibold">
              {earningsEvents?.next_event_date ? formatDateShortIt(earningsEvents.next_event_date) : '-'}
            </div>
          </div>
          <div className="rounded-lg border border-border p-2.5">
            <div className="text-[11px] text-muted-foreground">Reddit Signal</div>
            <div className={`text-base font-semibold ${statusColor(socialSentiment?.sentiment)}`}>
              {(socialSentiment?.sentiment || 'neutral').replaceAll('_', ' ')}
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
        <div className="xl:col-span-8 bg-card p-4 rounded-xl border border-border shadow-sm">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <h3 className="text-lg font-semibold">Latest News</h3>
            <div className="flex flex-wrap gap-2">
              {filters.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setNewsFilter(f.id)}
                  className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                    newsFilter === f.id
                      ? 'border-primary bg-primary/15 text-primary'
                      : 'border-border text-muted-foreground hover:bg-accent/40'
                  }`}
                >
                  {f.label} ({f.count})
                </button>
              ))}
            </div>
          </div>

          {filteredNews.length === 0 ? (
            <div className="mt-3 text-sm text-muted-foreground">No recent news available for this filter.</div>
          ) : (
            <div className="mt-3 space-y-2">
              {filteredNews.slice(0, 12).map((item, idx) => (
                <a
                  key={`${item.url}-${idx}`}
                  href={item.url}
                  target="_blank"
                  rel="noreferrer"
                  className="block rounded-lg border border-border bg-background/20 px-3 py-3 hover:bg-accent/35 transition-colors"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-medium leading-snug">{item.title}</div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {item.publisher || 'Unknown'} {item.published_at ? `• ${formatDateTimeIt(item.published_at)}` : ''}
                      </div>
                    </div>
                    <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-medium ${sentimentBadgeClass(item.sentiment)}`}>
                      {String(item.sentiment || 'neutral')}
                    </span>
                  </div>
                </a>
              ))}
            </div>
          )}
        </div>

        <div className="xl:col-span-4 space-y-4">
          <div className="bg-card p-4 rounded-xl border border-border shadow-sm">
            <h3 className="text-lg font-semibold mb-2">Earnings & Events</h3>
            {!earningsEvents?.has_data ? (
              <div className="text-sm text-muted-foreground">No earnings/event calendar available.</div>
            ) : (
              <>
                <div className="text-xs text-muted-foreground">
                  Next event: <span className="text-foreground font-medium">{formatDateIt(earningsEvents.next_event_date)}</span>
                </div>
                <div className="mt-2 space-y-2">
                  {(earningsEvents.events || []).slice(0, 6).map((ev, idx) => (
                    <div key={`${ev.type}-${ev.date}-${idx}`} className="rounded border border-border p-2">
                      <div className="text-xs text-muted-foreground">{ev.label || ev.type}</div>
                      <div className="text-sm font-medium">{formatDateIt(ev.date)}</div>
                      {(ev.eps_estimate !== null && ev.eps_estimate !== undefined) && (
                        <div className="text-xs text-muted-foreground">EPS Est: {Number(ev.eps_estimate).toFixed(2)}</div>
                      )}
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>

          <div className="bg-card p-4 rounded-xl border border-border shadow-sm">
            <h3 className="text-lg font-semibold mb-2">Social Sentiment (Reddit Beta)</h3>
            {!socialSentiment?.has_data ? (
              <div className="text-sm text-muted-foreground">
                No Reddit social sentiment available for this asset right now.
              </div>
            ) : (
              <>
                <div className="grid grid-cols-2 gap-2">
                  <div className="rounded border border-border p-2">
                    <div className="text-xs text-muted-foreground">Score</div>
                    <div className="text-sm font-semibold">{socialSentiment.score ?? '-'}/100</div>
                  </div>
                  <div className="rounded border border-border p-2">
                    <div className="text-xs text-muted-foreground">Heuristic coverage</div>
                    <div className="text-sm font-semibold">{socialSentiment.confidence ?? '-'}%</div>
                  </div>
                  <div className="rounded border border-border p-2">
                    <div className="text-xs text-muted-foreground">Mentions (24h)</div>
                    <div className="text-sm font-semibold">{socialSentiment.mentions_24h ?? 0}</div>
                  </div>
                  <div className="rounded border border-border p-2">
                    <div className="text-xs text-muted-foreground">Mentions (7d)</div>
                    <div className="text-sm font-semibold">{socialSentiment.mentions_7d ?? 0}</div>
                  </div>
                </div>
                <div className="mt-2 text-xs text-muted-foreground">
                  Bullish: <span className="text-foreground">{formatPct(socialSentiment.bullish_ratio)}</span>
                  {' '}| Bearish: <span className="text-foreground">{formatPct(socialSentiment.bearish_ratio)}</span>
                </div>
                {socialSentiment.note ? (
                  <div className="mt-1 text-[11px] text-muted-foreground">{socialSentiment.note}</div>
                ) : null}
                {(socialSentiment.posts || []).length > 0 && (
                  <div className="mt-3 space-y-2">
                    {(socialSentiment.posts || []).slice(0, 3).map((post, idx) => (
                      <a
                        key={`${post.url}-${idx}`}
                        href={post.url}
                        target="_blank"
                        rel="noreferrer"
                        className="block rounded border border-border p-2 hover:bg-accent/35 transition-colors"
                      >
                        <div className="text-sm font-medium leading-snug">{post.title}</div>
                        <div className="mt-1 text-xs text-muted-foreground">
                          r/{post.subreddit || 'unknown'} {post.published_at ? `• ${formatDateTimeIt(post.published_at)}` : ''}
                        </div>
                        <div className="mt-1 text-xs text-muted-foreground">
                          Score: <span className="text-foreground">{post.score ?? 0}</span>
                          {' '}| Comments: <span className="text-foreground">{post.num_comments ?? 0}</span>
                        </div>
                      </a>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

const InsiderSection = ({ insiderActivity, ticker }) => {
  const activity = insiderActivity || {};
  const summary = activity.summary || {};
  const transactions = Array.isArray(activity.transactions) ? activity.transactions : [];
  const windowDays = activity.window_days || 90;

  return (
    <div className="space-y-4">
      <div className="bg-card p-4 rounded-xl border border-border shadow-sm">
        <div className="flex flex-col gap-1 md:flex-row md:items-end md:justify-between">
          <div>
            <h3 className="text-lg font-semibold">Insider Buys ({ticker})</h3>
            <div className="text-xs text-muted-foreground">
              Corporate insider purchases from the last {windowDays} days only. Politician trades are excluded.
            </div>
          </div>
          <div className={`text-sm font-semibold ${activity.has_purchases ? 'text-green-500' : 'text-muted-foreground'}`}>
            {activity.has_data === false ? 'Insider records unavailable' : activity.has_purchases ? 'Recent insider buying found' : 'No recent insider buys found'}
          </div>
        </div>

        <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2">
          <div className="rounded-lg border border-border p-2.5">
            <div className="text-[11px] text-muted-foreground">Purchase Rows</div>
            <div className="text-base font-semibold">{formatCount(summary.purchase_count)}</div>
          </div>
          <div className="rounded-lg border border-border p-2.5">
            <div className="text-[11px] text-muted-foreground">Shares Bought</div>
            <div className="text-base font-semibold">{formatCompact(summary.purchase_shares)}</div>
          </div>
          <div className="rounded-lg border border-border p-2.5">
            <div className="text-[11px] text-muted-foreground">Reported Value</div>
            <div className="text-base font-semibold">{formatCompact(summary.purchase_value)}</div>
          </div>
          <div className="rounded-lg border border-border p-2.5">
            <div className="text-[11px] text-muted-foreground">Latest Buy</div>
            <div className="text-base font-semibold">
              {summary.latest_purchase_date ? formatDateShortIt(summary.latest_purchase_date) : '-'}
            </div>
          </div>
        </div>

        {activity.note ? (
          <div className="mt-3 text-xs text-muted-foreground">{activity.note}</div>
        ) : null}
      </div>

      <div className="bg-card p-4 rounded-xl border border-border shadow-sm">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-lg font-semibold">Latest Insider Purchase Filings</h3>
          <div className="text-xs text-muted-foreground">{activity.has_data === false ? 'No source records available' : 'Source: Yahoo Finance / yfinance'}</div>
        </div>

        {transactions.length === 0 ? (
          <div className="mt-3 text-sm text-muted-foreground">
            No recent insider purchase rows are available for this asset right now. This is common for ETFs, crypto, indexes, or companies with no recent buy filings.
          </div>
        ) : (
          <div className="mt-3 space-y-2">
            {transactions.map((item, idx) => (
              <div
                key={`${item.insider}-${item.date}-${idx}`}
                className="rounded-lg border border-border bg-background/20 px-3 py-3"
              >
                <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                  <div className="min-w-0">
                    <div className="text-sm font-medium leading-snug">{item.insider || 'Unknown insider'}</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {item.relation || 'Company insider'}
                      {item.date ? ` • ${formatDateIt(item.date)}` : ''}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {item.transaction_type || 'Purchase'}
                      {item.ownership ? ` • ${item.ownership}` : ''}
                    </div>
                  </div>
                  <div className="grid grid-cols-3 gap-2 md:min-w-[280px]">
                    <div className="rounded border border-border p-2">
                      <div className="text-[11px] text-muted-foreground">Shares</div>
                      <div className="text-sm font-semibold">{formatCompact(item.shares)}</div>
                    </div>
                    <div className="rounded border border-border p-2">
                      <div className="text-[11px] text-muted-foreground">Value</div>
                      <div className="text-sm font-semibold">{formatCompact(item.value)}</div>
                    </div>
                    <div className="rounded border border-border p-2">
                      <div className="text-[11px] text-muted-foreground">Avg Price</div>
                      <div className="text-sm font-semibold">{formatPrice(item.price)}</div>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

const InsightsPanel = ({ insights, ticker, section, dcfProfile, onDcfProfileChange, isLoading }) => {
  if (!insights) return null;

  const fundamental = insights.fundamental || {};
  const wyckoff = insights.wyckoff || {};
  const os = insights.overbought_oversold || {};
  const insiderActivity = insights.insider_activity || {};
  const news = insights.news || [];
  const socialSentiment = insights.social_sentiment || {};

  if (section === 'fundamental') {
    return (
      <FundamentalSection
        fundamental={fundamental}
        dcfProfile={dcfProfile || fundamental.dcf_profile || 'base'}
        onDcfProfileChange={onDcfProfileChange}
        isLoading={isLoading}
      />
    );
  }
  if (section === 'technical') {
    return <TechnicalSection wyckoff={wyckoff} os={os} />;
  }
  if (section === 'insiders') {
    return <InsiderSection insiderActivity={insiderActivity} ticker={ticker} />;
  }
  if (section === 'news') {
    return <NewsSection news={news} ticker={ticker} earningsEvents={fundamental.earnings_events} socialSentiment={socialSentiment} />;
  }
  return null;
};

export default InsightsPanel;
