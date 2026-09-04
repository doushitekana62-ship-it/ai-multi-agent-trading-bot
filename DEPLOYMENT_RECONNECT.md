# Deployment Reconnect Checklist

The production architecture has two layers with a safe fallback:

- Cloudflare Worker: dashboard, authentication, INDODAX public market data, manual paper ON/OFF, Durable Object state and scheduler.
- FastAPI Cloud: preferred CPython execution layer for the repository's full multi-agent Orchestrator.
- Cloudflare local fallback: a deterministic five-agent market ensemble keeps paper analysis functional if FastAPI Cloud is unavailable. It never places real orders.

The Worker calls FastAPI Cloud through HTTPS using `AI_ENGINE_URL` and `AI_ENGINE_SHARED_SECRET` when configured.

## FastAPI Cloud

Repository: `doushitekana62-ship-it/ai-multi-agent-trading-bot`

Application directory: repository root

Entrypoint: `fastapi_cloud_app:app`

Secret: `AI_ENGINE_SHARED_SECRET` with at least 32 characters.

After deployment:

- `GET /` -> `status=online`
- `GET /health` -> `status=healthy`
- `GET /ready` -> `status=ready` and `ai_engine_secret_configured=true`

## Cloudflare Worker

Worker name: `ai-multi-agent-trading-bot`

Workers Builds root directory: `fronted`

Build command: `npm install --legacy-peer-deps && npm run build`

Deploy command: `uvx --from workers-py pywrangler deploy`

Wrangler source of truth: `fronted/wrangler.jsonc`

Required binding: `PAPER_STATE` -> `PaperTradingState`

The Worker must not use an `AI_ENGINE` service binding. FastAPI Cloud is an external HTTPS service.

## Cloudflare runtime variables/secrets

`SUPABASE_URL` is now pinned in `fronted/wrangler.jsonc` to the production Supabase project URL.

The following must exist in the Cloudflare Worker production environment:

- Secret `SUPABASE_SECRET_KEY` — preferred current Supabase server secret key (`sb_secret_...`).
- Legacy secret `SUPABASE_SERVICE_ROLE_KEY` is also accepted for compatibility.

Do not commit either secret to GitHub or put it in the frontend build.

Also required by the dashboard/runtime:

- `AI_ENGINE_URL` — FastAPI Cloud HTTPS base URL without `/engine/analyze`.
- `AI_ENGINE_SHARED_SECRET`
- `JWT_SECRET_KEY`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`

The AI secret must match the FastAPI Cloud secret exactly. If the AI variables are absent or the external engine fails, the Worker automatically uses the local five-agent fallback instead of disabling the paper bot.

## Supabase smoke test

The Worker exposes a read-only health endpoint:

`GET /api/system/health`

For a real database probe use:

`GET /api/system/health?deep=1`

Expected after the Cloudflare secret is configured:

- `config.supabase_configured = true`
- `database.configured = true`
- `database.connected = true`
- `database.reason = rest_probe_ok`

Before the secret is configured, the expected diagnostic is `database.reason = credentials_missing`.

The probe only reads one row from `public.decisions`; it does not modify the trading ledger.

## INDODAX public data

The Worker uses the documented public endpoints:

- `/api/{pair}/ticker`
- `/api/{pair}/trades`
- `/api/tickers`

No INDODAX private credentials are required for the dashboard market-data layer.

## GitHub Actions

GitHub Actions is validation only. Cloudflare Workers Builds is the production deployment path.

The validation workflow must not be interpreted as proof that the production Worker has deployed. Production runtime verification requires the Worker deployment itself to be current and its runtime variables/secrets to be present.

## Paper-trading runtime write gate

Supabase contains a singleton runtime write gate used to prevent ledger writes during destructive paper-ledger reset. `PAPER_STATE.enable_paper()` enables this gate before arming the Durable Object scheduler; `stop()` disables it. A reset leaves the gate disabled until the next explicit start.

If the dashboard is tested immediately after a reset, the production Worker must be running the current `paper_state.py` implementation so that Start re-enables the gate. A stale Worker build can otherwise fail when the database write triggers are locked.

## Paper-trading safety contract

OFF:
- no AI cycle
- no Durable Object alarm execution
- no paper decision count increase

ON:
- Durable Object schedules one alarm at a time
- each cycle fetches current INDODAX public data
- FastAPI Cloud is used when configured and reachable; otherwise the local multi-agent fallback is used
- the result is persisted in `PaperTradingState`
- the next alarm is scheduled only while BOT remains ON

STOP:
- clears the alarm
- sets `enabled=false`
- prevents future cycles
- never enables itself again

Real exchange execution remains locked.
