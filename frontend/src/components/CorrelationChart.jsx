import React, { useMemo, useState } from 'react';
import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
    ReferenceLine,
    ReferenceArea,
} from 'recharts';
import { formatDateIt, formatDateShortIt } from '../utils/dateFormat';

const isIsoDate = (val) => typeof val === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(val);
const isFiniteNumber = (val) => typeof val === 'number' && Number.isFinite(val);
const normalizeRange = (startIndex, endIndex, maxIndex) => {
    if (maxIndex < 0) return { startIndex: 0, endIndex: 0 };
    const safeStart = Math.max(0, Math.min(Number(startIndex), maxIndex));
    const safeEnd = Math.max(0, Math.min(Number(endIndex), maxIndex));
    return {
        startIndex: Math.min(safeStart, safeEnd),
        endIndex: Math.max(safeStart, safeEnd),
    };
};
const getEventIndex = (e, rows) => {
    if (!e || !Array.isArray(rows) || rows.length === 0) return null;
    const rawIdx = e.activeTooltipIndex;
    const parsed = Number(rawIdx);
    if (Number.isFinite(parsed)) return Math.max(0, Math.min(Math.round(parsed), rows.length - 1));
    const label = e.activeLabel;
    if (label !== undefined && label !== null) {
        const idxFromLabel = rows.findIndex((row) => row?.date === label);
        if (idxFromLabel >= 0) return idxFromLabel;
    }
    return null;
};
const toRangeReturnPct = (startNorm, endNorm) => {
    if (!isFiniteNumber(startNorm) || !isFiniteNumber(endNorm)) return null;
    const startFactor = 1 + (startNorm / 100);
    const endFactor = 1 + (endNorm / 100);
    if (Math.abs(startFactor) < 1e-12) return null;
    return ((endFactor / startFactor) - 1) * 100;
};
const computePearson = (xValues, yValues) => {
    if (!Array.isArray(xValues) || !Array.isArray(yValues)) return null;
    if (xValues.length !== yValues.length || xValues.length < 2) return null;
    const n = xValues.length;
    const meanX = xValues.reduce((acc, v) => acc + v, 0) / n;
    const meanY = yValues.reduce((acc, v) => acc + v, 0) / n;
    let cov = 0;
    let varX = 0;
    let varY = 0;
    for (let i = 0; i < n; i += 1) {
        const dx = xValues[i] - meanX;
        const dy = yValues[i] - meanY;
        cov += dx * dy;
        varX += dx * dx;
        varY += dy * dy;
    }
    if (varX < 1e-12 || varY < 1e-12) return null;
    return cov / Math.sqrt(varX * varY);
};

const EMPTY_ROWS = [];
const CorrelationChartContent = ({ data, title = 'Pattern Confluence', modeLabel = null, preferredChartType = 'annual' }) => {
    const { current_trend, best_match } = data;

    const preferredType = preferredChartType === 'window' ? 'window' : 'annual';
    const [chartType, setChartType] = useState(preferredType);
    const currentPrices = current_trend.prices || EMPTY_ROWS;
    const fullYearPrices = best_match.full_year_data || EMPTY_ROWS;
    const fullYearDates = best_match.full_year_dates || EMPTY_ROWS;
    const matchDates = best_match.match_dates || EMPTY_ROWS;
    const matchData = best_match.match_data || EMPTY_ROWS;
    const windowSize = best_match?.score_components?.window_size || Math.min(currentPrices.length, matchData.length);

    // We normalize around the start of each compared window to compare shape, not price level.
    const basePriceCurrent = currentPrices[0];
    const basePriceHistorical = matchData.length > 0 ? matchData[0] : fullYearPrices[0];

    const normalize = (val, base) => {
        if (!base) return 0;
        return ((val - base) / base) * 100;
    };

    const { annualData, windowData } = useMemo(() => {
        const currentByMatchDate = new Map();
        const alignedLen = Math.min(matchDates.length, currentPrices.length);
        for (let i = 0; i < alignedLen; i += 1) {
            const dt = matchDates[i];
            if (dt) currentByMatchDate.set(dt, normalize(currentPrices[i], basePriceCurrent));
        }

        const annualRows = [];
        for (let i = 0; i < fullYearPrices.length; i += 1) {
            const date = fullYearDates[i];
            annualRows.push({
                index: i,
                date,
                historical: normalize(fullYearPrices[i], basePriceHistorical),
                current: currentByMatchDate.has(date) ? currentByMatchDate.get(date) : null,
            });
        }

        const winLen = Math.min(currentPrices.length, matchData.length, matchDates.length || Number.MAX_SAFE_INTEGER);
        const windowRows = [];
        for (let i = 0; i < winLen; i += 1) {
            const date = matchDates[i] || `Step ${i + 1}`;
            windowRows.push({
                index: i,
                date,
                historical: normalize(matchData[i], basePriceHistorical),
                current: normalize(currentPrices[i], basePriceCurrent),
            });
        }

        return {
            annualData: annualRows,
            windowData: windowRows,
        };
    }, [
        currentPrices,
        fullYearPrices,
        fullYearDates,
        matchDates,
        matchData,
        basePriceCurrent,
        basePriceHistorical,
    ]);

    const hasWindowData = windowData.length > 1;
    const showWindow = chartType === 'window' && hasWindowData;
    const plotData = showWindow ? windowData : annualData;
    const historicalLegend = showWindow ? `Matched ${windowSize}BD (${best_match.match_year})` : `Year ${best_match.match_year}`;
    const currentLegend = 'Current Trend';
    const currentColor = '#3b82f6';
    const [selectedRange, setSelectedRange] = useState(null);
    const [dragRange, setDragRange] = useState(null);

    const changeChartType = (type) => {
        setChartType(type);
        setSelectedRange(null);
        setDragRange(null);
    };

    const activeRange = useMemo(() => {
        const maxIndex = plotData.length - 1;
        if (!selectedRange) return normalizeRange(0, maxIndex, maxIndex);
        return normalizeRange(selectedRange.startIndex, selectedRange.endIndex, maxIndex);
    }, [selectedRange, plotData.length]);

    const visualRange = useMemo(() => {
        const maxIndex = plotData.length - 1;
        if (!dragRange) return activeRange;
        return normalizeRange(dragRange.startIndex, dragRange.endIndex, maxIndex);
    }, [dragRange, activeRange, plotData.length]);

    const hasCustomRange = plotData.length > 1
        && (visualRange.startIndex > 0 || visualRange.endIndex < plotData.length - 1);
    const selectedStartDate = plotData[visualRange.startIndex]?.date;
    const selectedEndDate = plotData[visualRange.endIndex]?.date;
    const applyDragSelection = () => {
        if (!dragRange) return;
        const maxIndex = plotData.length - 1;
        const normalized = normalizeRange(dragRange.startIndex, dragRange.endIndex, maxIndex);
        setSelectedRange(normalized);
        setDragRange(null);
    };
    const onChartMouseDown = (e) => {
        if (plotData.length < 2) return;
        const idx = getEventIndex(e, plotData);
        if (!Number.isFinite(idx)) return;
        setDragRange({ startIndex: idx, endIndex: idx });
    };
    const onChartMouseMove = (e) => {
        if (!dragRange) return;
        const idx = getEventIndex(e, plotData);
        if (!Number.isFinite(idx)) return;
        setDragRange((prev) => (prev ? { ...prev, endIndex: idx } : prev));
    };

    const rangeMetrics = useMemo(() => {
        if (plotData.length === 0) {
            return {
                startLabel: '-',
                endLabel: '-',
                overlapPoints: 0,
                historicalPoints: 0,
                currentPoints: 0,
                currentReturn: null,
                historicalReturn: null,
                correlation: null,
            };
        }
        const slice = plotData.slice(visualRange.startIndex, visualRange.endIndex + 1);
        const startLabel = slice[0]?.date ?? '-';
        const endLabel = slice[slice.length - 1]?.date ?? '-';
        const historicalOnly = slice.filter((row) => isFiniteNumber(row?.historical)).map((row) => row.historical);
        const currentOnly = slice.filter((row) => isFiniteNumber(row?.current)).map((row) => row.current);
        const overlap = slice.filter((row) => isFiniteNumber(row?.current) && isFiniteNumber(row?.historical));
        const overlapHistorical = overlap.map((row) => row.historical);
        const overlapCurrent = overlap.map((row) => row.current);

        const historicalReturn = historicalOnly.length >= 2
            ? toRangeReturnPct(historicalOnly[0], historicalOnly[historicalOnly.length - 1])
            : null;
        const currentReturn = currentOnly.length >= 2
            ? toRangeReturnPct(currentOnly[0], currentOnly[currentOnly.length - 1])
            : null;
        const correlation = overlap.length >= 2
            ? computePearson(overlapCurrent, overlapHistorical)
            : null;

        if (overlap.length < 2) {
            return {
                startLabel,
                endLabel,
                overlapPoints: overlap.length,
                historicalPoints: historicalOnly.length,
                currentPoints: currentOnly.length,
                currentReturn,
                historicalReturn,
                correlation,
            };
        }
        return {
            startLabel,
            endLabel,
            overlapPoints: overlap.length,
            historicalPoints: historicalOnly.length,
            currentPoints: currentOnly.length,
            currentReturn,
            historicalReturn,
            correlation,
        };
    }, [plotData, visualRange.startIndex, visualRange.endIndex]);

    const formatPct = (val) => (isFiniteNumber(val) ? `${val >= 0 ? '+' : ''}${val.toFixed(2)}%` : '-');
    const formatCorr = (val) => (isFiniteNumber(val) ? val.toFixed(3) : '-');

    const yDomain = useMemo(() => {
        const selectedSlice = plotData.slice(visualRange.startIndex, visualRange.endIndex + 1);
        const overlapRows = !showWindow
            ? selectedSlice.filter((row) => isFiniteNumber(row?.current) && isFiniteNumber(row?.historical))
            : [];
        const comparisonRows = overlapRows.length >= 2 ? overlapRows : (selectedSlice.length >= 2 ? selectedSlice : plotData);

        const allValues = [];
        for (let i = 0; i < comparisonRows.length; i += 1) {
            const row = comparisonRows[i];
            if (isFiniteNumber(row?.historical)) allValues.push(row.historical);
            if (isFiniteNumber(row?.current)) allValues.push(row.current);
        }

        let minVal = -0.1;
        let maxVal = 0.1;
        if (allValues.length > 0) {
            minVal = Math.min(...allValues);
            maxVal = Math.max(...allValues);
            const spread = maxVal - minVal;
            const minSpread = 0.05;
            const spreadForPadding = spread < minSpread ? minSpread : spread;
            const pad = Math.max(spreadForPadding * 0.02, 0.005);
            minVal -= pad;
            maxVal += pad;
        }

        return [minVal, maxVal];
    }, [plotData, showWindow, visualRange.startIndex, visualRange.endIndex]);

    const crossesYearBoundary = useMemo(() => {
        if (matchDates.length < 2) return false;
        const firstDate = matchDates.find(isIsoDate);
        const lastDate = [...matchDates].reverse().find(isIsoDate);
        if (!firstDate || !lastDate) return false;
        return new Date(firstDate).getFullYear() !== new Date(lastDate).getFullYear();
    }, [matchDates]);

    return (
        <div className="w-full h-[500px] bg-card p-4 rounded-xl border border-border shadow-sm flex flex-col">
            <div className="mb-4 shrink-0">
                <h3 className="text-lg font-semibold">{title}</h3>
                <div className="text-sm text-muted-foreground">
                    Viewing: <span className="font-bold text-foreground">{modeLabel || 'Analog Match'}</span>
                    <span className="ml-4">Chart: <span className="font-bold text-foreground">{showWindow ? `${windowSize}BD Window` : 'Year Context'}</span></span>
                    <span className="ml-4">Year: <span className="font-bold text-foreground">{best_match.match_year}</span></span>
                    <span className="ml-4">Correlation: {(best_match.correlation * 100).toFixed(1)}%</span>
                </div>
                <div className="mt-3 inline-flex rounded-lg border border-border p-1 bg-secondary/30">
                    <button
                        type="button"
                        onClick={() => changeChartType('annual')}
                        className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                            !showWindow ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'
                        }`}
                    >
                        Year Context
                    </button>
                    <button
                        type="button"
                        onClick={() => hasWindowData && changeChartType('window')}
                        disabled={!hasWindowData}
                        className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                            showWindow ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'
                        } ${!hasWindowData ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                        {windowSize}BD Window
                    </button>
                </div>
                <div className="mt-3 text-xs text-muted-foreground">
                    <span>Drag across the chart to select a range.</span>
                    <button
                        type="button"
                        onClick={() => setSelectedRange({ startIndex: 0, endIndex: Math.max(0, plotData.length - 1) })}
                        className="ml-3 rounded border border-border px-2 py-0.5 text-[11px] hover:bg-secondary/40"
                    >
                        Reset Range
                    </button>
                </div>
                <div className="mt-2 text-xs text-muted-foreground">
                    Historical similarity and continuation; not a forecast or calibrated probability.
                </div>
                <div className="mt-2 text-xs text-muted-foreground">
                    <span className="font-medium text-foreground">Range:</span>{' '}
                    {isIsoDate(rangeMetrics.startLabel) ? formatDateIt(rangeMetrics.startLabel) : rangeMetrics.startLabel}
                    {' -> '}
                    {isIsoDate(rangeMetrics.endLabel) ? formatDateIt(rangeMetrics.endLabel) : rangeMetrics.endLabel}
                    <span className="ml-4">Past Return: <span className="font-semibold text-foreground">{formatPct(rangeMetrics.historicalReturn)}</span></span>
                    <span className="ml-4">Current Return: <span className="font-semibold text-foreground">{formatPct(rangeMetrics.currentReturn)}</span></span>
                    <span className="ml-4">Corr: <span className="font-semibold text-foreground">{formatCorr(rangeMetrics.correlation)}</span></span>
                    <span className="ml-4">Overlap: {rangeMetrics.overlapPoints}</span>
                </div>
                {!showWindow && crossesYearBoundary && (
                    <div className="mt-2 text-xs text-amber-300/90">
                        This seasonal window crosses year-end. Year Context shows only the selected year; use {windowSize}BD Window to see all compared business days.
                    </div>
                )}
            </div>

            <div className="flex-1 w-full min-h-0">
                <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                        data={plotData}
                        margin={{ top: 5, right: 20, left: 8, bottom: 20 }}
                        onMouseDown={onChartMouseDown}
                        onMouseMove={onChartMouseMove}
                        onMouseUp={applyDragSelection}
                        onMouseLeave={applyDragSelection}
                    >
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
                        {hasCustomRange && selectedStartDate && selectedEndDate && (
                            <ReferenceArea
                                x1={selectedStartDate}
                                x2={selectedEndDate}
                                fill="#94a3b8"
                                fillOpacity={0.12}
                            />
                        )}
                        <XAxis
                            dataKey="date"
                            stroke="hsl(var(--muted-foreground))"
                            tick={{ fontSize: 12 }}
                            minTickGap={50}
                            tickFormatter={(val) => {
                                if (!val) return '';
                                return isIsoDate(val) ? formatDateShortIt(val) : val;
                            }}
                        />
                        <YAxis hide domain={yDomain} />
                        <Tooltip
                            contentStyle={{ backgroundColor: 'hsl(var(--popover))', borderColor: 'hsl(var(--border))', color: 'hsl(var(--popover-foreground))' }}
                            labelFormatter={(label) => (isIsoDate(label) ? `Date: ${formatDateIt(label)}` : label)}
                            formatter={(value, name) => [value !== null && value !== undefined ? `${value.toFixed(2)}%` : '', name]}
                        />
                        <Legend verticalAlign="top" height={36} />
                        {hasCustomRange && selectedStartDate && (
                            <ReferenceLine x={selectedStartDate} stroke="#94a3b8" strokeDasharray="3 3" />
                        )}
                        {hasCustomRange && selectedEndDate && (
                            <ReferenceLine x={selectedEndDate} stroke="#94a3b8" strokeDasharray="3 3" />
                        )}
                        <ReferenceLine y={0} stroke="hsl(var(--border))" strokeDasharray="4 4" />
                        <Line
                            type="linear"
                            dataKey="historical"
                            name={historicalLegend}
                            stroke="#94a3b8"
                            strokeWidth={showWindow ? 2 : 2.5}
                            dot={false}
                            opacity={showWindow ? 0.6 : 0.75}
                        />

                        <Line
                            type="linear"
                            dataKey="current"
                            name={currentLegend}
                            stroke={currentColor}
                            strokeWidth={3}
                            dot={false}
                            connectNulls={!showWindow ? false : true}
                        />
                    </LineChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
};

const CorrelationChart = (props) => {
    if (!props.data?.current_trend || !props.data?.best_match) return null;
    const { current_trend, best_match } = props.data;
    const identity = [props.modeLabel, props.preferredChartType, best_match.match_year,
        current_trend.dates?.[0], current_trend.dates?.at(-1), current_trend.prices?.length,
        best_match.match_dates?.[0], best_match.match_dates?.at(-1), best_match.full_year_data?.length].join('|');
    return <CorrelationChartContent key={identity} {...props} />;
};

export default CorrelationChart;
