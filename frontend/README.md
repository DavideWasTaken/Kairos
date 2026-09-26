# Kairos Frontend

React + Vite application for the Kairos dashboard. See the [project README](../README.md) for backend setup, the offline synthetic demo and Docker deployment. Use Node.js 22.12+ (Node 24 is also supported).

## Local run

```bash
npm ci
cp .env.example .env
npm run dev
```

By default the frontend calls `/api` and relies on Vite proxy (`VITE_PROXY_TARGET`) in development. The development server binds to `127.0.0.1`. Set `KAIROS_DEMO=1` on the backend to make `/api/health` announce demo mode; the UI then offers the DEMO asset and labels generated data explicitly.

Research Chat reads the backend's AI capability from `/api/health`. Without a backend `GROQ_API_KEY`, calculated queries remain available. A configured key enables natural questions and optional commentary on the selected asset; the initial badge reports configuration, not a tested provider connection. Each answer reports whether AI was used or failed. Generated commentary may contain errors; its evidence links point to the separately displayed calculated facts and source records. The selected DCF profile accompanies requests, and evidence comes from the backend's analysis snapshot rather than client-supplied facts. Never put a provider key in a frontend environment variable.

## Checks

```bash
npm run lint
npm test
npm run build
npm audit
```

Presentation tests use Node's test runner, React server rendering and the existing Vite transform. They verify capability states, evidence links, bounded request history and error text, and that source facts, observed dates, missing values, heuristic score weights and DCF assumptions remain visible independently of generated AI commentary. They do not call market providers or an LLM.

## Build

```bash
npm run build
npm run preview
```

`npm run preview` serves the built frontend only. Use the development proxy or the Docker setup for API connectivity.
