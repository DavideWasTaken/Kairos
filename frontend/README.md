# Kairos Frontend

React + Vite application for the Kairos dashboard. See the [project README](../README.md) for backend setup, the offline synthetic demo and Docker deployment. Use Node.js 22.12+ (Node 24 is also supported).

## Local run

```bash
npm ci
cp .env.example .env
npm run dev
```

By default the frontend calls `/api` and relies on Vite proxy (`VITE_PROXY_TARGET`) in development. The development server binds to `127.0.0.1`. Set `KAIROS_DEMO=1` on the backend to make `/api/health` announce demo mode; the UI then offers the DEMO asset and labels generated data explicitly.

## Checks

```bash
npm run lint
npm test
npm run build
npm audit
```

Presentation tests use Node's test runner, React server rendering and the existing Vite transform. They verify that source facts, observed dates, missing values, heuristic score weights and DCF assumptions remain visible independently of optional AI-selected explanation text. They do not call market providers or an LLM.

## Build

```bash
npm run build
npm run preview
```

`npm run preview` serves the built frontend only. Use the development proxy or the Docker setup for API connectivity.
