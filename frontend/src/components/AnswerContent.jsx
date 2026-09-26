import { useId } from 'react';

const label = (key) => key.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
const AI_ERRORS = {
  authentication_failed: 'The provider denied authentication or access. Check the backend API key and model permissions.',
  model_unavailable: 'The configured model is unavailable. Check the backend model setting.',
  rate_limited: 'The provider rate limit was reached. Try again later.',
  timeout: 'The AI request timed out. Try again later.',
  provider_unavailable: 'The AI provider is temporarily unavailable.',
  transport_error: 'The backend could not reach the AI provider.',
  invalid_response: 'The provider returned an unusable response.',
  invalid_request: 'The provider could not accept the request. Check the backend model configuration.',
  invalid_plan: 'The AI request interpretation could not be validated.',
  invalid_commentary: 'The AI commentary or its evidence references could not be validated.',
};
const AI_STATES = {
  demo: 'Synthetic demo · No AI calls',
  disabled: 'AI disabled · Calculated queries only',
  used: 'AI used for this request',
  partial: 'AI partially used for this request',
  unavailable: 'AI unavailable for this request · Calculated fallback',
};
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

export default function AnswerContent({ content, facts = [], explanation, usedLlm = false, ai, evidenceIds = [] }) {
  const answerId = useId();
  const records = Array.isArray(facts) ? facts : [];
  const factTarget = (id) => `${answerId}-${id}`;
  const references = Array.isArray(evidenceIds) ? evidenceIds.filter((id) => records.some((fact) => fact.id === id)) : [];
  const linkedCommentary = typeof explanation === 'string' ? explanation.split(/(\[[A-Za-z0-9_-]+\])/g).map((part, index) => {
    const id = part.slice(1, -1);
    return references.includes(id) && part.startsWith('[')
      ? <a key={index} href={`#${factTarget(id)}`} className="text-cyan-300 underline">{part}</a>
      : part;
  }) : null;
  return (
    <div className="space-y-3">
      <div className="whitespace-pre-wrap">{content}</div>
      {ai && AI_STATES[ai.status] && (
        <div className="text-xs text-muted-foreground" role="status">
          <span>{AI_STATES[ai.status]}.</span>
          {ai.code && <span> {AI_ERRORS[ai.code] || 'The AI step could not be completed.'}</span>}
          {ai.planning_status === 'used' && ai.commentary_status === 'unavailable' && <span> Question interpreted; generated commentary unavailable.</span>}
        </div>
      )}
      {Array.isArray(facts) && facts.length > 0 && (
        <section aria-label="Calculated facts" className="space-y-2 border-t border-border pt-2">
          <h4 className="font-semibold">Calculated facts &amp; source records</h4>
          {facts.map((fact, index) => (
            <article id={fact.id ? factTarget(fact.id) : undefined} key={index} className="rounded-lg border border-border bg-background/40 p-3 text-xs">
              <h5 className="font-semibold mb-2">{fact.id ? `[${fact.id}] ` : ''}{label(fact.metric || 'Source record')}</h5>
              <FactFields value={Object.fromEntries(Object.entries(fact).filter(([key]) => key !== 'metric' && key !== 'id'))} />
            </article>
          ))}
        </section>
      )}
      {usedLlm === true && typeof explanation === 'string' && explanation.trim() && (
        <section aria-label="AI commentary" className="rounded-lg border border-cyan-500/30 bg-cyan-500/5 p-3">
          <h4 className="font-semibold">AI commentary</h4>
          <p className="mt-1 text-xs text-muted-foreground">Generated by AI; may contain errors. References identify source records, not verification of the commentary.</p>
          <p className="mt-2 whitespace-pre-wrap">{linkedCommentary}</p>
          {references.length > 0 && <div className="mt-2 flex flex-wrap gap-2 text-xs">
            <span>Referenced records:</span>
            {references.map((id) => <a key={id} href={`#${factTarget(id)}`} className="text-cyan-300 underline">[{id}]</a>)}
          </div>}
        </section>
      )}
    </div>
  );
}
