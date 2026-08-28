# Deployment Reconnect Checklist

This project uses two separate runtimes with a strict boundary:

- Cloudflare Worker: dashboard, authentication, market-data collection, manual paper ON/OFF, Durable Object state and scheduler.
- FastAPI Cloud: CPython AI execution layer for the existing multi-agent Orchestrator.

The two services communicate only through HTTPS using `AI_ENGINE_URL` and `AI_ENGINE_SHARED_SECRET`.

## 1. FastAPI Cloud

Repository:
`doushitekana62-ship-it/ai-multi-agent-trading-bot`

Application Directory:
**blank / repository root**

Entrypoint:
`fastapi_cloud_app:app`

The repository root `pyproject.toml` already declares this entrypoint.

Environment secret:
`AI_ENGINE_SHARED_SECRET`

Use one random secret with at least 32 characters. Save it as a secret, not a normal variable.

After deployment:

- `GET /` must return `status=online`.
- `GET /health` must return `status=healthy`.
- `GET /ready` must return `status=ready` and `ai_engine_secret_configured=true`.

## 2. Cloudflare Worker

Worker name:
`ai-multi-agent-trading-bot`

Repository:
`doushitekana62-ship-it/ai-multi-agent-trading-bot`

Workers Builds root directory:
`fronted`

Build command:
`npm install --legacy-peer-deps && npm run build`

Deploy command:
`uvx --from workers-py pywrangler deploy`

Version command:
`npx wrangler versions upload`

The Wrangler source of truth is `fronted/wrangler.jsonc`.

Required binding:
`PAPER_STATE` -> `PaperTradingState`

The Worker must **not** have an `AI_ENGINE` service binding. FastAPI Cloud is external and is reached through HTTPS.

## 3. Cloudflare runtime variables/secrets

Normal variable:

`AI_ENGINE_URL`

Value: the FastAPI Cloud HTTPS base URL, without `/engine/analyze`.

Secrets:

`AI_ENGINE_SHARED_SECRET`
`JWT_SECRET_KEY`
`ADMIN_USERNAME`
`ADMIN_PASSWORD`
`SUPABASE_URL`
`SUPABASE_SERVICE_ROLE_KEY`

The `AI_ENGINE_SHARED_SECRET` value must exactly match the FastAPI Cloud secret.

## 4. GitHub Actions

GitHub Actions is CI/validation only for this architecture. It does not deploy the Worker.

Cloudflare Workers Builds is the single production deployment path. This prevents two independent systems from deploying the same Worker and producing stale binding/configuration states.

## 5. Paper-trading safety contract

The bot is manually controlled.

OFF:
- no AI cycle
- no Durable Object alarm execution
- no paper decision count increase

ON:
- Durable Object schedules one alarm at a time
- one cycle invokes the multi-agent Orchestrator through FastAPI Cloud
- result is persisted in `PaperTradingState`
- next alarm is scheduled only while the bot remains ON

STOP:
- clears the alarm
- sets `enabled=false`
- prevents future cycles
- never enables itself again

Real exchange execution remains locked in this architecture.

## 6. Reconnect order

Do not connect both services at the same time.

1. Create FastAPI Cloud app from the repository root.
2. Add `AI_ENGINE_SHARED_SECRET`.
3. Deploy FastAPI Cloud.
4. Verify `/health` and `/ready`.
5. Create/reconnect the Cloudflare Worker from the repository.
6. Set the Cloudflare Worker variables and secrets.
7. Verify the Worker deployment succeeds.
8. Open the dashboard and log in.
9. Verify database and market-data health.
10. Press `START PAPER BOT` manually.
11. Verify the first cycle reaches the FastAPI engine and `Cycles` becomes `1`.
12. Verify Agent/Orchestrator data appears.
13. Press `STOP PAPER BOT` and verify the cycle count stops.

Never add real exchange credentials during this reconnect/test phase.
