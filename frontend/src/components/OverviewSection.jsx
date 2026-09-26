import React, { useMemo, useState } from 'react';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { formatDateIt, formatDateShortIt } from '../utils/dateFormat';
import HeuristicScore from './HeuristicScore';

const EMPTY_HISTORY = { dates: [], prices: [] };

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

const formatPrice = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

const toDateSafe = (value) => {
  if (!value) return null;
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [y, m, d] = value.split('-').map(Number);
    const out = new Date(y, m - 1, d);
    return Number.isNaN(out.getTime()) ? null : out;
  }
  const out = new Date(value);
  return Number.isNaN(out.getTime()) ? null : out;
};

const MarkerCapsuleLabel = ({ x, y, viewBox, value }) => {
  const px = Number.isFinite(Number(x)) ? Number(x) : Number(viewBox?.x);
  const py = Number.isFinite(Number(y)) ? Number(y) : Number(viewBox?.y);
  if (!Number.isFinite(px) || !Number.isFinite(py) || !value) return null;
  const text = String(value);
  const width = Math.max(54, text.length * 7 + 16);
  const height = 24;
  const offsetY = py > 90 ? py - 34 : py + 12;
  return (
    <g transform={`translate(${px - (width / 2)}, ${offsetY})`} style={{ pointerEvents: 'none' }}>
      <rect width={width} height={height} rx={12} ry={12} fill="#40b8a7" fillOpacity={0.95} />
      <text
        x={width / 2}
        y={16}
        textAnchor="middle"
        fontSize="12"
        fill="#0f4f47"
        stroke="#dffaf4"
        strokeWidth={0.2}
        fontWeight="700"
      >
        {text}
      </text>
    </g>
  );
};

const LeftPriceBadge = ({ viewBox, value }) => {
  if (!viewBox || !value) return null;
  const x = Number(viewBox.x) || 0;
  const y = Number(viewBox.y) || 0;
  const text = String(value);
  const width = Math.max(56, text.length * 8 + 18);
  const height = 30;
  return (
    <g transform={`translate(${x + 6}, ${y - (height / 2)})`}>
      <rect width={width} height={height} rx={15} ry={15} fill="#274c77" fillOpacity={0.95} />
      <text x={width / 2} y={19} textAnchor="middle" fontSize="14" fill="#f8fafc" fontWeight="700">
        {text}
      </text>
    </g>
  );
};

const OverviewTooltip = ({ active, payload, label }) => {
  if (!active || !payload || payload.length === 0) return null;
  const row = payload[0]?.payload || {};
  return (
    <div className="rounded-md border border-border bg-popover p-2 text-sm shadow-md">
      <div className="font-medium text-popover-foreground">{formatDateIt(label)}</div>
      <div className="mt-1 text-popover-foreground">
        <span className="text-muted-foreground">Price:</span>{' '}
        <span className="font-semibold">{formatPrice(row.price)}</span>
      </div>
      {row.netIncome !== null && row.netIncome !== undefined && (
        <div className="text-popover-foreground">
          <span className="text-muted-foreground">Net Income:</span>{' '}
          <span className="font-semibold">{formatCompact(row.netIncome)}</span>
        </div>
      )}
    </div>
  );
};

const OverviewSection = ({ insights }) => {
  const [seriesMode, setSeriesMode] = useState('annual');
  const quickVerdict = insights?.quick_verdict || {};
  const priceHistory = insights?.price_history || EMPTY_HISTORY;
  const annualTrend = insights?.fundamental?.annual_trend || [];
  const quarterlyTrend = insights?.fundamental?.quarterly_trend || [];
  const hasQuarterly = quarterlyTrend.length > 0;
  const effectiveSeriesMode = seriesMode === 'quarterly' && hasQuarterly ? 'quarterly' : 'annual';
  const selectedTrend = effectiveSeriesMode === 'quarterly' ? quarterlyTrend : annualTrend;

  const {
    chartData,
    markerRows,
    currentPrice,
  } = useMemo(() => {
    const maxLen = Math.min(priceHistory?.dates?.length || 0, priceHistory?.prices?.length || 0);
    const start = Math.max(0, maxLen - 1500);
    const rows = [];
    for (let i = start; i < maxLen; i += 1) {
      const date = priceHistory.dates[i];
      const price = Number(priceHistory.prices[i]);
      const parsed = toDateSafe(date);
      if (!parsed || !Number.isFinite(price)) continue;
      rows.push({
        date,
        ts: parsed.getTime(),
        price,
        netIncome: null,
        netIncomeScaled: null,
      });
    }
    if (rows.length === 0) {
      return { chartData: [], markerRows: [], currentPrice: null };
    }

    const markers = [];
    const trendForMarkers = (selectedTrend || []).slice(effectiveSeriesMode === 'quarterly' ? -12 : -10);
    trendForMarkers.forEach((row) => {
      if (row?.net_income === null || row?.net_income === undefined) return;
      const ni = Number(row?.net_income);
      const d = toDateSafe(row?.period);
      if (!d || !Number.isFinite(ni)) return;
      const targetTs = d.getTime();

      let bestBeforeIdx = -1;
      let bestBeforeDelta = Number.POSITIVE_INFINITY;
      for (let i = 0; i < rows.length; i += 1) {
        const delta = targetTs - rows[i].ts;
        if (delta >= 0 && delta < bestBeforeDelta) {
          bestBeforeDelta = delta;
          bestBeforeIdx = i;
        }
      }
      let idx = bestBeforeIdx;
      if (idx < 0) {
        let closestIdx = 0;
        let closestAbs = Math.abs(rows[0].ts - targetTs);
        for (let i = 1; i < rows.length; i += 1) {
          const abs = Math.abs(rows[i].ts - targetTs);
          if (abs < closestAbs) {
            closestAbs = abs;
            closestIdx = i;
          }
        }
        idx = closestIdx;
      }
      markers.push({
        index: idx,
        date: rows[idx].date,
        netIncome: ni,
      });
    });

    const dedup = new Map();
    markers.forEach((m) => {
      dedup.set(m.date, m);
    });
    const markerRowsSorted = Array.from(dedup.values()).sort((a, b) => a.index - b.index);

    const priceValues = rows.map((r) => r.price);
    const priceMin = Math.min(...priceValues);
    const priceMax = Math.max(...priceValues);
    const priceSpan = Math.max(1, priceMax - priceMin);
    const niValues = markerRowsSorted.map((m) => m.netIncome);
    const niMin = niValues.length ? Math.min(...niValues) : 0;
    const niMax = niValues.length ? Math.max(...niValues) : 1;
    const niSpan = Math.max(1, niMax - niMin);

    markerRowsSorted.forEach((m) => {
      const normalized = (m.netIncome - niMin) / niSpan;
      const scaled = priceMin + (priceSpan * 0.25) + (normalized * priceSpan * 0.65);
      rows[m.index].netIncome = m.netIncome;
      rows[m.index].netIncomeScaled = scaled;
    });

    const markerRowsWithScale = markerRowsSorted.map((m) => ({
      ...m,
      netIncomeScaled: rows[m.index]?.netIncomeScaled ?? null,
    }));

    return {
      chartData: rows.map((r) => ({
        date: r.date,
        price: r.price,
        netIncome: r.netIncome,
        netIncomeScaled: r.netIncomeScaled,
      })),
      markerRows: markerRowsWithScale,
      currentPrice: rows[rows.length - 1]?.price ?? null,
    };
  }, [selectedTrend, effectiveSeriesMode, priceHistory]);
  const hasIncomeObservations = markerRows.length > 0;

  const verdictLabel = (quickVerdict.label || 'neutral').toLowerCase();
  const verdictClass = verdictLabel === 'bullish'
    ? 'bg-green-500/10 text-green-500 border-green-500/20'
    : verdictLabel === 'bearish'
      ? 'bg-red-500/10 text-red-500 border-red-500/20'
      : 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20';

  const reasons = Array.isArray(quickVerdict.reasons) && quickVerdict.reasons.length > 0
    ? quickVerdict.reasons
    : ['Signals are mixed across valuation, technical trend, and revisions.'];

  return (
    <div className="space-y-4">
      <HeuristicScore confidence={insights?.model_confidence} />
      <div className="bg-card p-4 rounded-xl border border-border shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2 mb-3">
          <div>
            <div className="text-xs text-muted-foreground uppercase tracking-wider font-semibold">Quick Verdict</div>
            <div className="text-lg font-bold text-foreground mt-1">
              {quickVerdict.summary || 'Neutral setup with mixed signals.'}
            </div>
          </div>
          <div className={`text-sm font-bold px-3 py-1.5 rounded-md border ${verdictClass}`}>
            {verdictLabel.toUpperCase()}
          </div>
        </div>
        <ul className="text-sm text-muted-foreground space-y-1.5 list-disc pl-4">
          {reasons.slice(0, 3).map((reason, idx) => (
            <li key={idx}>{reason}</li>
          ))}
        </ul>
      </div>

      <div className="bg-card p-4 rounded-xl border border-border shadow-sm">
        <div className="mb-3 flex items-center justify-between gap-2 flex-wrap">
          <h3 className="text-lg font-semibold">{hasIncomeObservations ? 'Price vs Net Income' : 'Price History'}</h3>
          {(annualTrend.length > 0 || hasQuarterly) && <div className="inline-flex rounded-lg border border-border overflow-hidden">
            <button
              type="button"
              onClick={() => setSeriesMode('annual')}
              className={`px-3 py-1.5 text-xs transition-colors ${
                effectiveSeriesMode === 'annual'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
              }`}
            >
              Annual
            </button>
            <button
              type="button"
              onClick={() => setSeriesMode('quarterly')}
              disabled={!hasQuarterly}
              className={`px-3 py-1.5 text-xs transition-colors ${
                effectiveSeriesMode === 'quarterly'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
              } ${!hasQuarterly ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              Quarterly
            </button>
          </div>}
        </div>
        <div className="text-sm text-muted-foreground mb-3">
          {hasIncomeObservations
            ? `Blue area is price. Green path and labels represent ${effectiveSeriesMode} Net Income checkpoints.`
            : 'Blue area is price. Net income observations are unavailable for this period.'}
        </div>

        {chartData.length === 0 ? (
          <div className="text-sm text-muted-foreground">Not enough historical data to render this chart.</div>
        ) : (
          <div className="h-[460px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} margin={{ top: 30, right: 18, left: 10, bottom: 8 }}>
                <defs>
                  <linearGradient id="priceFillGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#60a5fa" stopOpacity={0.45} />
                    <stop offset="100%" stopColor="#60a5fa" stopOpacity={0.05} />
                  </linearGradient>
                </defs>

                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11 }}
                  minTickGap={50}
                  tickFormatter={(v) => formatDateShortIt(v)}
                />
                <YAxis
                  tick={{ fontSize: 12 }}
                  tickFormatter={(v) => formatPrice(v)}
                  domain={[
                    (dataMin) => dataMin - Math.abs(dataMin) * 0.04,
                    (dataMax) => dataMax + Math.abs(dataMax) * 0.12,
                  ]}
                />
                <Tooltip content={<OverviewTooltip />} />
                <Legend />

                {markerRows.map((m, idx) => (
                  <ReferenceLine
                    key={`${m.date}-${idx}`}
                    x={m.date}
                    stroke="#40b8a7"
                    strokeDasharray="4 4"
                    strokeWidth={1.6}
                    opacity={0.85}
                  />
                ))}

                {currentPrice !== null && (
                  <ReferenceLine
                    y={currentPrice}
                    stroke="#3b82f6"
                    strokeDasharray="4 4"
                    strokeWidth={1.6}
                    opacity={0.9}
                    label={<LeftPriceBadge value={formatPrice(currentPrice)} />}
                  />
                )}

                <Area
                  type="monotone"
                  dataKey="price"
                  name="Price"
                  stroke="#5d9ce6"
                  fill="url(#priceFillGradient)"
                  strokeWidth={2.6}
                  dot={false}
                />
                {hasIncomeObservations && <Line
                  type="linear"
                  dataKey="netIncomeScaled"
                  name="Net Income Path"
                  stroke="#36b19f"
                  strokeWidth={3}
                  dot={false}
                  connectNulls
                  isAnimationActive={false}
                />}

                {markerRows.map((m, idx) => (
                  <ReferenceDot
                    key={`label-${m.date}-${idx}`}
                    x={m.date}
                    y={m.netIncomeScaled}
                    r={4}
                    fill="#36b19f"
                    stroke="#eafffb"
                    strokeWidth={1}
                    ifOverflow="extendDomain"
                    label={<MarkerCapsuleLabel value={formatCompact(m.netIncome)} />}
                  />
                ))}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
};

export default OverviewSection;
