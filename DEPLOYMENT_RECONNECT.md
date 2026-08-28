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

Variable:

`AI_ENGINE_URL` — FastAPI Cloud HTTPS base URL without `/engine/analyze`.

Secrets/variables:

`AI_ENGINE_SHARED_SECRET`
`JWT_SECRET_KEY`
`ADMIN_USERNAME`
`ADMIN_PASSWORD`
`SUPABASE_URL`
`SUPABASE_SERVICE_ROLE_KEY`

The AI secret must match the FastAPI Cloud secret exactly. If the AI variables are absent or the external engine fails, the Worker automatically uses the local five-agent fallback instead of disabling the paper bot.

## INDODAX public data

The Worker uses the documented public endpoints:

- `/api/{pair}/ticker`
- `/api/{pair}/trades`
- `/api/tickers`

No INDODAX private credentials are required for the dashboard market-data layer.

## GitHub Actions

GitHub Actions is validation only. Cloudflare Workers Builds is the production deployment path.

The repository's Actions runs were observed failing before any job steps executed. That is consistent with a runner/account-level Actions availability or billing problem rather than a source-code assertion failure. The code changes are committed independently of that external runner state.

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
