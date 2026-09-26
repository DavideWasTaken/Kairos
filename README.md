# Kairos

[![Checks](https://github.com/DavideWasTaken/Kairos/actions/workflows/checks.yml/badge.svg)](https://github.com/DavideWasTaken/Kairos/actions/workflows/checks.yml)

**A financial research dashboard that brings price patterns, company fundamentals and traceable calculations into one workspace.**

Kairos is a personal exploration of financial data and software architecture: a Python analysis engine, a React interface, and a constrained chat layer. It helps inspect the evidence behind a metric and compare different views of an asset. It has no validated trading edge or calibrated return forecasts.

![Kairos running with synthetic demo data](docs/images/kairos-demo.png)

## What you can explore

- **Historical patterns:** compare the latest price window with similar past windows, including a separate seasonal match. See what followed the historical match, with the dates visible.
- **Company analysis:** financial trends, valuation scenarios, analyst revisions and a breakdown of data availability.
- **Technical context:** moving averages, RSI, MACD and volume indicators calculated from OHLCV history.
- **Insider activity:** explicitly identified purchases, with reported dates, shares and values where available.
- **A traceable chat:** returns, correlations and insider scans produce structured facts with their source and observed period. Numerical answers are formatted by code.

## Try it without API keys

Docker Compose starts in **synthetic demo mode** by default:

```sh
docker compose up --build
```

Open [localhost:8080](http://localhost:8080), then choose **Explore synthetic demo**. The `DEMO` and `DEMO2` assets use deterministic generated prices and volumes. Pattern matching, technical calculations and supported chat metrics run locally against those fixtures. Company fundamentals, news and insider data remain unavailable rather than being invented.

Demo mode makes no market-data or model requests. Its historical dates and prices are deliberately fixed; they are not current quotes. Stop with `docker compose down`.

### Local development

Requires Python 3.13 and Node.js 22. From the repository root:

```sh
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# PowerShell:  .\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements-dev.txt
```

Copy `backend/.env.example` to `backend/.env`, then start the API:

```sh
cd backend
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open [localhost:5173](http://localhost:5173). The Vite proxy sends `/api` requests to the local backend. API documentation is at [localhost:8000/docs](http://localhost:8000/docs).

### Use live data

Set `KAIROS_DEMO=0` in `backend/.env` for local development. With Docker, copy the root `.env.example` to `.env`, change the same setting, and recreate the containers.

Live mode uses Yahoo Finance through `yfinance` and public endpoints, plus public news/social sources where available. Coverage, rate limits and missing data affect the results. Respect the providers' terms; this repository does not distribute their datasets.

`GROQ_API_KEY` is optional. When configured, the model can select a predefined qualitative explanation appropriate to a computed metric. It cannot write or replace the numerical answer. Without a key, or when model validation fails, calculations and deterministic answers still work. In live mode with the key enabled, the current question and metric type are sent to Groq.

| Variable | Purpose |
| --- | --- |
| `KAIROS_DEMO` | `1` for synthetic, offline fixtures; `0` for live providers |
| `ALLOWED_ORIGINS` | Explicit allowed browser origins |
| `GROQ_API_KEY`, `GROQ_MODEL` | Optional explanation selection |
| `VITE_API_URL` | Frontend API base, normally `/api` |
| `VITE_PROXY_TARGET` | Local development backend, default `http://localhost:8000` |
| `FRONTEND_PORT`, `BACKEND_PORT` | Docker host ports, default `8080` and `8000` |

## How it is built

```text
React + Recharts
      | /api
      v
FastAPI
      +-- Historical pattern engine (NumPy / pandas)
      +-- Fundamental, technical and insider calculations
      +-- Deterministic chat facts -> optional explanation selector
      +-- Data source: synthetic fixtures OR live providers
```

Docker serves the frontend through Nginx and runs the API with Uvicorn. Local environment files are loaded by the backend; process variables take precedence.

## Reading the results honestly

**Pattern similarity is descriptive.** The engine searches many historical windows using Pearson correlation of price levels. A strong match can happen by chance. The displayed continuation is what followed a past window, not a forecast. There is no out-of-sample validation, transaction-cost model or strategy backtest.

**The composite score is a heuristic.** Its weights and thresholds are hand chosen. Missing components appear as unavailable; partial scores use disclosed neutral imputation. A score is not a probability or a measure of predictive accuracy. Demo mode omits the composite entirely.

**Valuations are scenarios.** DCF estimates depend on projected cash flow, discount rates, terminal growth, shares and debt. The interface exposes assumptions and missing inputs. They are not independently validated fair values.

**Verified facts means computed from the retrieved inputs.** It does not certify the provider's accuracy or completeness. Insider summaries cover available records and the scanned universe, not every market transaction. See [methodology and limitations](docs/METHODOLOGY.md).

## Checks

```sh
python -m unittest discover -s tests -v
python -m compileall -q backend
cd frontend
npm test
npm run lint
npm run build
npm audit --audit-level=high
```

The regression suite uses synthetic or mocked inputs: RSI edge cases, Yahoo column layouts, insider classification and lookback windows, missing-data scoring, chat output validation, API demo isolation and frontend presentation. CI runs these checks. These tests do not certify current live-provider availability or investment performance.

## Scope

Designed for local research and demonstration. Compose binds host ports to loopback. Authentication, per-user isolation and rate limiting are not implemented; add them before exposing an instance to other users. Keep credentials in ignored environment files. Nothing here places trades.

## License

[MIT](LICENSE) · Built by [Davide Gaglione](https://davide.sh).
