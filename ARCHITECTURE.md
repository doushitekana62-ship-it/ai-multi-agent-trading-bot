# AI Trading Bot — Canonical Architecture

Status: CANONICAL / 2026-09-04

This document is the single runtime authority for the project. New features must fit this architecture; they must not introduce a second trading brain, second market-data truth, or a second execution state.

## 1. Production topology

```text
GitHub Pages (React/Vite)
        |
        | HTTPS / JSON + JWT
        v
Canonical FastAPI service (backend.api:app)
        |
        +--> INDODAX public market API
        |
        +--> Multi-agent Orchestrator
        |      Sentiment / Technical / Decision / Forecast / Reflector
        |
        +--> Risk + paper execution
        |
        +--> Supabase authoritative ledger/state
        |
        +--> Optional exchange credentials, paper mode only by default
```

Cloudflare is NOT part of the production path. There is no Cloudflare Worker, Durable Object, Worker proxy, or Cloudflare-specific runtime dependency in the canonical deployment.

## 2. Responsibilities

GitHub Pages: static dashboard only. It contains no server secrets and never calls Supabase with an elevated key. Its API base is supplied at build time with the public repository variable `VITE_API_URL` and has a safe canonical FastAPI fallback in the authentication client.

FastAPI: single backend entrypoint, authentication, market API, agent orchestration, risk decisions, paper execution, reports, and API responses consumed by the dashboard.

Supabase: authoritative persistent ledger for decisions, trades, paper history, market observations, and runtime controls. Server-side access uses `SUPABASE_SECRET_KEY` when available, otherwise the legacy `SUPABASE_SERVICE_ROLE_KEY`.

INDODAX: canonical public market-data source for the current paper/scalping implementation. The browser does not independently invent a different market signal.

## 3. Market Pulse contract

The backend owns Market Pulse. A rolling window contains 30 one-minute segments. Each minute is derived from observed public market data.

- Price change during a populated minute: GREEN for positive, RED for negative.
- A populated minute with a flat final move but an observed intraminute price change uses the last observed direction.
- Only a minute with no valid observations is GRAY.
- The same observations are available to the AI analysis pipeline; frontend rendering is presentation only.
- The rolling 30-minute result must never be treated as a prediction by itself.
- Intraminute state must preserve `sample_count`, `price_changed`, `last_direction`, and the minute open/close so a price move inside one minute is not silently flattened.

Data failure is never represented as normal HOLD. Missing/degraded evidence is excluded from directional scoring and produces an explicit data-quality state.

## 4. Trading safety and P0 hard gates

Default mode is paper. Real exchange orders are locked until an explicit, separately audited live-trading implementation exists. UI controls cannot bypass server-side risk gates.

Every paper/live candidate follows this mandatory order:

`Market snapshot -> freshness/quality gate -> AI analysis -> deterministic risk -> execution gate -> executor`

The market-data gate is mandatory before AI analysis. The canonical default is `MARKET_DATA_MAX_AGE_SECONDS=90` and minimum market quality is `0.70` for the live paper cycle. A stale, invalid, low-quality, or non-positive-price snapshot must produce an explicit `DATA_STALE`, `DATA_UNAVAILABLE`, `DATA_QUALITY_LOW`, or `INVALID_PRICE` state and cannot become a trading signal.

AI agents advise; they do not execute. Risk controls are mandatory and cannot be overridden by an AI-generated recommendation. Execution remains paper-only by default.

Paper execution must respect position limits, daily loss limits, minimum confidence, minimum confirmations, conflict thresholds, stop loss, take profit, and execution gating already defined by the core trading modules.

Normal `HOLD_EXISTING_POSITION` is distinct from a data-quality failure or `AI_DEGRADED` state.

## 5. Authentication and secrets

Required FastAPI runtime values:

- `SUPABASE_URL`
- `SUPABASE_SECRET_KEY` or `SUPABASE_SERVICE_ROLE_KEY`
- `JWT_SECRET_KEY` (>=32 characters)
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `CORS_ORIGINS` including the GitHub Pages origin

These values belong on the FastAPI hosting platform, never in the React build and never in source control.

The GitHub Pages build needs only one non-secret repository variable:

- `VITE_API_URL` = public HTTPS base URL of the canonical FastAPI service

Authentication accepts the configured admin username case-insensitively and optional non-secret identifier aliases via `ADMIN_USERNAME_ALIASES`. The alias does not create another password or another account.

## 6. API contract

Health:
- `GET /health`
- `GET /ready`

Authentication:
- `GET /api/auth/status`
- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `GET /api/auth/verify`
- `POST /api/auth/logout`

Dashboard:
- `GET /api/dashboard/status`
- `GET /api/dashboard/positions`
- `GET /api/dashboard/performance`
- `GET /api/dashboard/recent-decision`
- `GET /api/dashboard/agents`
- `POST /api/dashboard/analyze`

Paper:
- `GET /api/dashboard/paper/status`
- `POST /api/dashboard/paper/start`
- `POST /api/dashboard/paper/stop`
- `POST /api/dashboard/paper/reset`
- `POST /api/dashboard/paper/settings`
- `GET /api/dashboard/paper/risk`

Market:
- `GET /api/market/overview?pair=btc_idr`
- `GET /api/market/insights`

## 7. Deployment and P1 validation

Frontend: GitHub Pages workflow `.github/workflows/github-pages.yml` builds `fronted` and deploys `fronted/dist`.

Backend: deploy `backend.api:app` from the repository root on a persistent FastAPI host. `fastapi_cloud_app.py` is retained only as a compatibility import and points to the same canonical app.

CI must test Python compilation, authentication contract, core trading contracts, market-data freshness, canonical trading pipeline, FastAPI import/health, deployment identity, and frontend build. Cloudflare deployment and Cloudflare runtime smoke tests are not production gates.

A production-ready build is not sufficient by itself. The live deployment gate must prove the public FastAPI service exposes the expected canonical entrypoint/version and health contract.

## 8. Change discipline

Before changing a feature, identify its single owner:

- UI: `fronted/src`
- HTTP/backend: `backend/routes` and `backend/api.py`
- AI/trading logic: `agents`, `core`, `integration`, `paper_trading`
- persistence: `backend/core/database.py` and `supabase/migrations`
- deployment: GitHub Pages workflow / FastAPI host

Do not duplicate logic between frontend and backend when the result affects trading decisions. Do not add a new runtime provider merely to solve a deployment problem without amending this architecture first.
