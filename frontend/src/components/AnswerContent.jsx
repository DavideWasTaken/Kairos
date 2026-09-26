const label = (key) => key.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
const formatValue = (value, key) => {
  if (value === null || value === undefined) return 'Unavailable';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value !== 'number') return String(value);
  if (!Number.isFinite(value)) return 'Unavailable';
  if (key.endsWith('_pct')) return `${value.toFixed(2)}%`;
  if (key === 'correlation') return value.toFixed(3);
  return value.toLocaleString('en-US', { maximumFractionDigits: 3 });
};

// Render provider facts directly, including nested insider filings. Never parse LLM prose for numbers.
const FactFields = ({ value }) => {
  if (Array.isArray(value)) return value.length ? (
    <div className="space-y-2">{value.map((entry, index) => (
      <div key={index} className="rounded border border-border p-2"><FactFields value={entry} /></div>
    ))}</div>
  ) : <span className="text-muted-foreground">No records</span>;
  if (!value || typeof value !== 'object') return <span>{formatValue(value, '')}</span>;
  return (
    <dl className="space-y-1">
      {Object.entries(value).map(([key, field]) => (
        <div key={key} className="break-words">
          <dt className="inline text-muted-foreground">{label(key)}: </dt>
          <dd className={field && typeof field === 'object' ? 'mt-1 pl-2' : 'inline'}>
            {field && typeof field === 'object' ? <FactFields value={field} /> : formatValue(field, key)}
          </dd>
        </div>
      ))}
    </dl>
  );
};

export default function AnswerContent({ content, facts = [], explanation, usedLlm = false }) {
  return (
    <div className="space-y-3">
      <div className="whitespace-pre-wrap">{content}</div>
      {Array.isArray(facts) && facts.length > 0 && (
        <section aria-label="Calculated facts" className="space-y-2 border-t border-border pt-2">
          <h4 className="font-semibold">Calculated facts &amp; source records</h4>
          {facts.map((fact, index) => (
            <article key={index} className="rounded-lg border border-border bg-background/40 p-3 text-xs">
              <h5 className="font-semibold mb-2">{label(fact.metric || 'Source record')}</h5>
              <FactFields value={Object.fromEntries(Object.entries(fact).filter(([key]) => key !== 'metric'))} />
            </article>
          ))}
        </section>
      )}
      {usedLlm === true && typeof explanation === 'string' && explanation.trim() && (
        <section aria-label="AI-selected explanation" className="rounded-lg border border-cyan-500/30 bg-cyan-500/5 p-3">
          <h4 className="font-semibold">AI-selected explanation</h4>
          <p className="mt-1 text-xs text-muted-foreground">Qualitative context; not a verified calculation or a prediction.</p>
          <p className="mt-2 whitespace-pre-wrap">{explanation}</p>
        </section>
      )}
    </div>
  );
}
