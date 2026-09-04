# AI Multi-Agent Trading Bot

Canonical production architecture: GitHub Pages dashboard + FastAPI backend + Supabase ledger + INDODAX public market data.

Cloudflare Workers and Durable Objects are no longer part of the application runtime.

## Runtime

- Frontend: `fronted/` — React/Vite, deployed by GitHub Pages.
- Backend: `backend.api:app` — canonical FastAPI application.
- Trading logic: `agents/`, `core/`, `integration/`, `paper_trading/`.
- Persistence: Supabase.
- Market source: INDODAX public API.
- Mode: paper trading by default; real exchange trading remains locked.

## Local development

Backend:

```bash
pip install -e .
uvicorn backend.api:app --reload
```

Frontend:

```bash
cd fronted
npm install --legacy-peer-deps
npm run start
```

For local Vite development, `/api` is proxied to `http://localhost:8000`. For GitHub Pages, the workflow supplies `VITE_API_URL`.

## Required FastAPI environment

```text
SUPABASE_URL
SUPABASE_SECRET_KEY (preferred) or SUPABASE_SERVICE_ROLE_KEY
JWT_SECRET_KEY (minimum 32 characters)
ADMIN_USERNAME
ADMIN_PASSWORD
CORS_ORIGINS
```

Do not place server secrets in the React build.

## GitHub Pages

The workflow `.github/workflows/github-pages.yml` builds `fronted/dist` and deploys it to the repository GitHub Pages site. The dashboard talks directly to the canonical FastAPI URL; no Worker proxy is involved.

## Safety

Paper mode is the only supported execution mode in the current production architecture. Do not enable real-money exchange execution without a separate audit of authentication, risk gates, reconciliation, and kill-switch behavior.

See `ARCHITECTURE.md` for the single source of truth on system boundaries and change discipline.
