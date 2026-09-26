import React, { useState } from 'react';
import { askFinancialChat, formatApiError } from '../api';
import AnswerContent from './AnswerContent';

const CALCULATED_PROMPTS = [
  'Average S&P 500 return over the last 30 years.',
  'What is the CAGR of this asset over the last 10 years?',
  'Show verified return stats for this ticker over 5 years.',
  'What is the correlation between Nasdaq 100 and S&P 500 over 5 years?',
  'Tell me the most important recent insider buys among U.S. small caps.',
  'Show me the most important insider buys among Nasdaq small caps over the last 30 days.',
];

const RESEARCH_PROMPTS = [
  'Summarize this asset using the dashboard data.',
  'What are the main risks and missing data for this asset?',
  'Explain the valuation assumptions for this asset.',
  'What is the correlation between this asset and the S&P 500 over 5 years?',
];

const Bubble = ({ role, content, facts, explanation, usedLlm, ai, evidenceIds }) => (
  <div className={`max-w-[88%] rounded-xl px-3 py-2 text-sm whitespace-pre-wrap ${
    role === 'user'
      ? 'ml-auto bg-primary text-primary-foreground'
      : 'mr-auto bg-secondary text-secondary-foreground'
  }`}
  >
    {role === 'user' ? content : <AnswerContent content={content} facts={facts} explanation={explanation} usedLlm={usedLlm} ai={ai} evidenceIds={evidenceIds} />}
  </div>
);

const AIChatPanel = ({ ticker, assetName, demoMode = false, aiCapability, dcfProfile = 'base' }) => {
  const isDemo = demoMode || aiCapability?.status === 'demo';
  const aiConfigured = !isDemo && aiCapability?.status === 'configured';
  const greeting = isDemo
    ? 'Explore calculated returns and correlation from synthetic DEMO and DEMO2 prices. No live data or AI calls are used.'
    : aiConfigured
      ? `Ask about ${ticker || 'the selected asset'}, its valuation assumptions, risks or historical returns. AI can interpret your question and generate commentary from server-held data. Check its references against the calculated facts and source records.`
      : `Ask about calculated returns, correlation or insider records${ticker ? ` for ${ticker}` : ''}. Answers show their data source and observed dates.`;
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  const prompts = isDemo ? ['Show returns for DEMO.', 'What is the correlation between DEMO and DEMO2?'] : aiConfigured ? RESEARCH_PROMPTS : CALCULATED_PROMPTS;

  const sendMessage = async (raw) => {
    const question = (raw || '').trim();
    if (!question || loading) return;

    const nextMessages = [...messages, { role: 'user', content: question }];
    setMessages(nextMessages);
    setInput('');
    setLoading(true);
    try {
      const response = await askFinancialChat(question, ticker, messages, dcfProfile);
      const answer = typeof response?.answer === 'string' ? response.answer.trim() : 'No answer generated.';
      setMessages((prev) => [...prev, {
        role: 'assistant', content: answer, facts: response?.verified_facts,
        explanation: response?.explanation, usedLlm: response?.used_llm === true,
        ai: response?.ai, evidenceIds: response?.evidence_ids,
      }]);
    } catch (err) {
      const detail = formatApiError(err, 'Chat request failed.');
      setMessages((prev) => [...prev, { role: 'assistant', content: `Error: ${detail}` }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-card p-4 rounded-xl border border-border shadow-sm">
      <h3 className="text-lg font-semibold">Research Chat</h3>
      <div className="text-sm text-muted-foreground mt-1">
        Calculated facts and source records, with optional AI commentary.
      </div>
      <div role="status" className="mt-2 rounded-lg border border-border bg-background/40 px-3 py-2 text-xs text-muted-foreground">
        {isDemo ? <><strong>Synthetic demo</strong> · No live data or AI calls.</>
          : aiConfigured ? <><strong>AI configured</strong> · Ready to attempt a request; connection not yet verified.{aiCapability.model ? ` Model: ${aiCapability.model}.` : ''}</>
            : aiCapability?.status === 'disabled' ? <><strong>AI disabled</strong> · Calculated queries remain available. To enable AI, set GROQ_API_KEY on the backend and restart it.</>
              : <><strong>AI status unavailable</strong> · The backend has not reported its AI configuration.</>}
      </div>
      {aiConfigured && <p className="mt-2 text-xs text-muted-foreground">Questions, recent chat history and selected source records are sent to Groq.</p>}
      <div className="text-xs text-muted-foreground mt-1">
        Context asset: <span className="text-foreground">{ticker || '-'}</span>
        {assetName ? <span>{` (${assetName})`}</span> : null}
        <span>{` · DCF profile: ${dcfProfile}`}</span>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {prompts.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => sendMessage(p)}
            disabled={loading}
            className="rounded-full border border-border px-3 py-1.5 text-xs text-muted-foreground hover:bg-secondary transition-colors disabled:opacity-50"
          >
            {p}
          </button>
        ))}
      </div>

      <div className="mt-3 h-[420px] overflow-y-auto rounded-lg border border-border bg-background/30 p-3 space-y-2">
        <Bubble role="assistant" content={greeting} />
        {messages.map((m, idx) => (
          <Bubble key={`${m.role}-${idx}`} {...m} />
        ))}
        {loading && (
          <div className="mr-auto inline-flex items-center gap-2 rounded-xl bg-secondary px-3 py-2 text-xs text-secondary-foreground">
            <span className="animate-spin h-3.5 w-3.5 border-2 border-b-transparent rounded-full" />
            Computing answer...
          </div>
        )}
      </div>

      <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-start">
        <textarea
          aria-label="Question about this asset"
          maxLength={2000}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              sendMessage(input);
            }
          }}
          placeholder={aiConfigured ? 'Ask about this asset, valuation assumptions or risks' : 'Ask about returns, correlation or insider records'}
          className="min-h-[60px] max-h-40 w-full flex-1 resize-y rounded-2xl border border-border/80 bg-background/70 px-4 py-3 text-sm leading-6 text-foreground shadow-[inset_0_1px_0_rgba(255,255,255,0.03)] transition placeholder:text-muted-foreground/80 focus:border-primary/70 focus:bg-background focus:outline-none focus:ring-2 focus:ring-primary/35 disabled:cursor-not-allowed disabled:opacity-70"
          disabled={loading}
        />
        <button
          type="button"
          onClick={() => sendMessage(input)}
          disabled={loading || !input.trim()}
          className="inline-flex h-[60px] w-full min-w-[120px] items-center justify-center gap-2 rounded-2xl border border-primary/30 bg-primary px-4 text-sm font-semibold text-primary-foreground shadow-[0_8px_20px_rgba(255,255,255,0.12)] transition hover:-translate-y-0.5 hover:bg-primary/95 hover:shadow-[0_12px_28px_rgba(255,255,255,0.16)] active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none sm:w-auto"
        >
          {loading ? (
            <>
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-primary-foreground/60 border-b-transparent" />
              Sending...
            </>
          ) : (
            <>
              <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
                <path d="M2.5 4.8a1 1 0 0 1 1.34-.98l13.2 5.2a1 1 0 0 1 0 1.86l-13.2 5.2A1 1 0 0 1 2.5 15.1V11l7.2-1-7.2-1V4.8z" />
              </svg>
              Send
            </>
          )}
        </button>
      </div>
    </div>
  );
};

export default AIChatPanel;
