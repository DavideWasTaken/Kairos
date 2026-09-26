const COMPONENTS = [
  ['valuation', 'Valuation', 0.34],
  ['technical', 'Technical', 0.24],
  ['data_quality', 'Data quality', 0.22],
  ['estimate_revisions', 'Revisions', 0.12, 'revisions'],
  ['news_sentiment', 'News', 0.08, 'news'],
];
const scoreText = (value) => typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(0)}/100` : 'Unavailable';

export default function HeuristicScore({ confidence }) {
  if (!confidence) return null;
  const method = confidence.methodology || {};
  const weights = method.weights || {};
  const breakdown = confidence.breakdown || {};
  return (
    <section className="bg-card p-4 rounded-xl border border-border shadow-sm">
      <div className="flex flex-wrap justify-between items-center gap-2">
        <h3 className="text-lg font-semibold">Heuristic score</h3>
        <span className="text-xl font-bold">{scoreText(confidence.score)}</span>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">A weighted rule-based summary of available signals; not a calibrated probability of a gain or forecast accuracy.</p>
      <div className="mt-3 grid grid-cols-2 md:grid-cols-5 gap-2">
        {COMPONENTS.map(([key, name, defaultWeight, alias]) => (
          <div key={key} className="rounded-lg border border-border p-2.5">
            <div className="text-xs text-muted-foreground">{name} · {Math.round((weights[key] ?? weights[alias] ?? defaultWeight) * 100)}%</div>
            <div className="mt-1 text-sm font-semibold">{scoreText(breakdown[key] ?? breakdown[alias])}</div>
          </div>
        ))}
      </div>
      <p className="mt-2 text-xs text-muted-foreground">{method.missing_data_policy || 'Unavailable inputs are marked explicitly. The score depends on data coverage and fixed heuristic weights.'}</p>
      {Array.isArray(method.assumptions) && method.assumptions.length > 0 && (
        <details className="mt-2 text-xs text-muted-foreground">
          <summary className="cursor-pointer">Scoring assumptions</summary>
          <ul className="mt-2 list-disc pl-4 space-y-1">{method.assumptions.map((assumption, index) => <li key={index}>{assumption}</li>)}</ul>
        </details>
      )}
    </section>
  );
}
