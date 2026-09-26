import React, { useEffect, useMemo, useState } from 'react';
import { AlertCircle, ChartNoAxesCombined } from 'lucide-react';
import AssetSelector from './components/AssetSelector';
import CorrelationChart from './components/CorrelationChart';
import OverviewSection from './components/OverviewSection';
import InsightsPanel from './components/InsightsPanel';
import AIChatPanel from './components/AIChatPanel';
import { analyzeStock, fetchHealth, formatApiError } from './api';

const DemoNotice = () => (
  <div role="status" className="my-3 rounded-lg border border-amber-400/30 bg-amber-400/10 p-3 text-xs text-amber-200">
    <strong>Synthetic demo</strong> · Prices, returns and indicators use generated data. No live market data or AI calls. Fundamentals, news and insider filings are unavailable.
  </div>
);

const SECTION_TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'seasonality', label: 'Pattern Confluence' },
  { id: 'fundamental', label: 'Fundamental Analysis' },
  { id: 'technical', label: 'Technical Analysis' },
  { id: 'insiders', label: 'Insider Buys' },
  { id: 'news', label: 'News' },
  { id: 'chat', label: 'Research Chat' },
];

const AssetAvatar = ({ asset, ticker }) => {
  const [imgFailed, setImgFailed] = useState(false);
  const symbol = (asset?.symbol || ticker || '').toUpperCase();
  const initials = symbol.slice(0, 2) || '??';
  const logoUrl = asset?.logo_url;
  if (!logoUrl || imgFailed) {
    return (
      <div className="h-10 w-10 rounded-lg bg-secondary text-secondary-foreground border border-border flex items-center justify-center text-xs font-bold">
        {initials}
      </div>
    );
  }
  return (
    <img
      src={logoUrl}
      alt={`${symbol} logo`}
      className="h-10 w-10 rounded-lg border border-border bg-white object-contain p-1"
      onError={() => setImgFailed(true)}
      loading="lazy"
    />
  );
};

function App() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeSection, setActiveSection] = useState('overview');
  const [patternView, setPatternView] = useState('seasonal');
  const [dcfProfile, setDcfProfile] = useState('base');
  const [lastTicker, setLastTicker] = useState('');
  const [healthDemoMode, setHealthDemoMode] = useState(false);
  const [aiCapability, setAiCapability] = useState(null);
  const demoMode = data?.demo_mode ?? healthDemoMode;

  useEffect(() => {
    let active = true;
    fetchHealth().then((health) => {
      if (active) {
        setHealthDemoMode(health.demo_mode === true);
        setAiCapability(health.ai || null);
      }
    }).catch(() => {});
    return () => { active = false; };
  }, []);

  const hasAssetView = Boolean(data);

  const runAnalysis = async (ticker, profile, resetSection = false, clearData = true) => {
    setLoading(true);
    setError(null);
    if (clearData) {
      setData(null);
    }
    try {
      const result = await analyzeStock(ticker, '3mo', profile);
      setData(result);
      if (resetSection) {
        setActiveSection('overview');
      }
    } catch (err) {
      setError(formatApiError(err, 'Failed to fetch analysis.'));
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async (ticker) => {
    const clean = (ticker || '').trim().toUpperCase();
    if (!clean) return;
    setLastTicker(clean);
    setPatternView('seasonal');
    const keepCurrentView = Boolean(data);
    await runAnalysis(clean, dcfProfile, true, !keepCurrentView);
  };

  const handleDcfProfileChange = async (profile) => {
    const next = (profile || 'base').toLowerCase();
    setDcfProfile(next);
    if (!lastTicker) return;
    await runAnalysis(lastTicker, next, false, false);
  };

  const currentAsset = useMemo(() => data?.asset || null, [data]);
  const currentTicker = (data?.ticker || lastTicker || '').toUpperCase();
  const currentName = currentAsset?.name || currentTicker;
  const seasonalityPayload = data?.seasonality ?? (data ? { current_trend: data.current_trend, best_match: data.best_match } : null);
  const currentTrendAnalog = seasonalityPayload?.current_trend_analog ?? seasonalityPayload?.current_trend ?? data?.current_trend ?? null;
  const currentTrendSeasonal = seasonalityPayload?.current_trend_seasonal ?? seasonalityPayload?.current_trend ?? data?.current_trend ?? null;
  const analogMatch = seasonalityPayload?.best_match_analog ?? seasonalityPayload?.best_match ?? data?.best_match ?? null;
  const seasonalMatch = seasonalityPayload?.best_match_seasonal ?? null;
  const selectedPatternView = patternView === 'seasonal' && seasonalMatch ? 'seasonal' : 'analog';
  const activeMatch = selectedPatternView === 'seasonal' ? seasonalMatch : analogMatch;
  const activeCurrentTrend = selectedPatternView === 'seasonal' ? currentTrendSeasonal : currentTrendAnalog;
  const chartPayload = seasonalityPayload && activeMatch && activeCurrentTrend
    ? {
      current_trend: activeCurrentTrend,
      best_match: activeMatch,
    }
    : null;

  if (!hasAssetView) {
    return (
      <div className="min-h-screen bg-background text-foreground px-4 pt-[12vh] md:pt-[16vh]">
        <main className="w-full max-w-3xl mx-auto">
          <div className="text-center">
            <div className="flex items-center justify-center gap-2">
              <ChartNoAxesCombined className="h-7 w-7 text-cyan-300" />
              <h1 className="text-3xl font-bold tracking-tight">Kairos</h1>
            </div>
            <p className="text-muted-foreground mt-2 text-sm">
              Multi-angle asset analysis in one workspace.
            </p>
          </div>

          <AssetSelector
            onSearch={handleSearch}
            isLoading={loading}
            initialQuery={lastTicker || (demoMode ? 'DEMO' : 'AAPL')}
            className="mt-6"
          />
          {demoMode && <DemoNotice />}
          {demoMode && (
            <div className="text-center">
              <button type="button" onClick={() => handleSearch('DEMO')} disabled={loading} className="rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50">Explore synthetic demo</button>
            </div>
          )}

          {error && (
            <div className="mt-4 p-4 bg-destructive/10 border border-destructive/20 rounded-lg flex items-center gap-2 text-destructive">
              <AlertCircle className="h-5 w-5" />
              <span>{error}</span>
            </div>
          )}
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-foreground px-4 py-3">
      <header className="w-full max-w-6xl mx-auto mb-4">
        <div className="rounded-xl border border-border bg-card/80 px-3 py-3">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-center gap-2 min-w-0">
              <ChartNoAxesCombined className="h-5 w-5 text-cyan-300 shrink-0" />
              <span className="font-bold text-lg shrink-0">Kairos</span>
              <div className="mx-1 h-5 w-px bg-border hidden md:block" />
              <div className="flex items-center gap-2 min-w-0">
                <AssetAvatar asset={currentAsset} ticker={currentTicker} />
                <div className="min-w-0">
                  <div className="text-sm font-semibold truncate">{currentTicker}</div>
                  <div className="text-xs text-muted-foreground truncate">{currentName}</div>
                </div>
              </div>
            </div>

            <AssetSelector
              onSearch={handleSearch}
              isLoading={loading}
              compact
              initialQuery={currentTicker || 'AAPL'}
              className="w-full lg:max-w-[520px]"
            />
          </div>

          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap gap-2">
              {SECTION_TABS.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveSection(tab.id)}
                  className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                    activeSection === tab.id
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            <div className="text-xs text-muted-foreground">Timeframe: Daily (1D)</div>
          </div>
        </div>
      </header>

      <main className="w-full max-w-6xl mx-auto">
        {demoMode && <DemoNotice />}
        {error && (
          <div className="mb-4 p-4 bg-destructive/10 border border-destructive/20 rounded-lg flex items-center gap-2 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>{error}</span>
          </div>
        )}

        {activeSection === 'overview' && (
          <OverviewSection insights={data.insights} ticker={data.ticker} />
        )}

        {activeSection === 'seasonality' && (
          <>
            <div className="mb-4 rounded-xl border border-border bg-card/70 p-3">
              <div className="inline-flex w-full max-w-[360px] rounded-xl bg-secondary/50 p-1">
                <button
                  type="button"
                  onClick={() => setPatternView('seasonal')}
                  disabled={!seasonalMatch}
                  className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition-all ${
                    selectedPatternView === 'seasonal'
                      ? 'bg-background text-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground'
                  } ${!seasonalMatch ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  Seasonal Strict
                </button>
                <button
                  type="button"
                  onClick={() => setPatternView('analog')}
                  className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition-all ${
                    selectedPatternView === 'analog'
                      ? 'bg-background text-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  Analog Match
                </button>
              </div>
              <div className="mt-2 text-xs text-muted-foreground">
                {selectedPatternView === 'analog'
                  ? 'Analog Match finds the best 90 business-day Pearson shape across all history.'
                  : 'Seasonal Strict applies 60 business-day Pearson with the window end anchored to the latest observation.'}
              </div>
            </div>

            <CorrelationChart
              data={chartPayload}
              title="Pattern Confluence"
              modeLabel={selectedPatternView === 'seasonal' ? 'Seasonal Strict' : 'Analog Match'}
              preferredChartType="annual"
            />

            <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
              {selectedPatternView === 'analog' ? (
                <div className="bg-card p-4 rounded-xl border border-border">
                  <h4 className="text-sm font-medium text-muted-foreground mb-1">Analog Year</h4>
                  <div className="text-2xl font-bold">
                    {analogMatch?.match_year ?? '-'}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    Corr: {analogMatch ? `${(analogMatch.correlation * 100).toFixed(1)}%` : '-'}
                  </div>
                </div>
              ) : (
                <div className="bg-card p-4 rounded-xl border border-border">
                  <h4 className="text-sm font-medium text-muted-foreground mb-1">Seasonal Year</h4>
                  <div className="text-2xl font-bold">
                    {seasonalMatch?.match_year ?? '-'}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    Corr: {seasonalMatch ? `${(seasonalMatch.correlation * 100).toFixed(1)}%` : 'No strict seasonal match'}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    Pearson 60D with calendar anchor on window end date.
                  </div>
                </div>
              )}
              <div className="bg-card p-4 rounded-xl border border-border">
                <h4 className="text-sm font-medium text-muted-foreground mb-1">
                  {selectedPatternView === 'seasonal' ? 'Seasonal Correlation' : 'Analog Correlation'}
                </h4>
                <div className="text-2xl font-bold text-green-500">
                  {activeMatch ? `${(activeMatch.correlation * 100).toFixed(1)}%` : '-'}
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  Correlation of the currently selected match year.
                </div>
              </div>
            </div>
          </>
        )}

        {activeSection === 'chat' && (
          <AIChatPanel key={`${currentTicker}-${dcfProfile}`} ticker={currentTicker} assetName={currentName} demoMode={demoMode} aiCapability={aiCapability} dcfProfile={dcfProfile} />
        )}

        {activeSection !== 'seasonality' && activeSection !== 'overview' && activeSection !== 'chat' && (
          <InsightsPanel
            insights={data.insights}
            ticker={data.ticker}
            section={activeSection}
            dcfProfile={dcfProfile}
            onDcfProfileChange={handleDcfProfileChange}
            isLoading={loading}
          />
        )}
      </main>
    </div>
  );
}

export default App;
