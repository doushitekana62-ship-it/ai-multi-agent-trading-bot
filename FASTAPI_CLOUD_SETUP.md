# FastAPI Cloud AI Engine

FastAPI Cloud is the external CPython execution layer for the heavy multi-agent AI analysis. Cloudflare Workers remains the dashboard/control plane, and the `PaperTradingState` Durable Object remains the authoritative manual ON/OFF gate and paper-account ledger.

## FastAPI Cloud app settings

Use the repository root. Do **not** set the Application Directory to `fronted` or `backend`.

- Repository: `doushitekana62-ship-it/ai-multi-agent-trading-bot`
- Application Directory / Root Directory: **leave empty**
- Entrypoint: `fastapi_cloud_app:app` (already declared in the root `pyproject.toml`)
- Python: use a supported CPython version in the repository range `>=3.11,<3.14`

The root `pyproject.toml` contains the production dependencies required by the existing Orchestrator, including NumPy, Pandas, SciPy and scikit-learn. This is important because those packages must not be imported by the Cloudflare Python Worker itself.

FastAPI's documentation recommends declaring the application entrypoint in `pyproject.toml`, especially when using deployment tools that need to discover the app automatically. urlFastAPI entrypoint documentationhttps://fastapi.tiangolo.com/fastapi-cli/

## FastAPI Cloud secret

Create exactly one secret:

`AI_ENGINE_SHARED_SECRET`

Use a random value of at least 32 characters. It must be identical to the Cloudflare Worker secret with the same name.

Do not put the value in GitHub, `.env.example`, frontend code, or source files.

## Cloudflare Worker variables and secrets

On the Worker, configure:

Normal variable:

`AI_ENGINE_URL` = the HTTPS base URL of the FastAPI Cloud application, for example `https://<your-app>.fastapicloud.dev`

Secrets:

- `AI_ENGINE_SHARED_SECRET` — same value as FastAPI Cloud
- `JWT_SECRET_KEY` — random secret, at least 32 characters
- `ADMIN_USERNAME` — dashboard login username
- `ADMIN_PASSWORD` — dashboard login password
- `SUPABASE_URL` — Supabase project URL
- `SUPABASE_SERVICE_ROLE_KEY` — Supabase service-role key

Do not add `CLOUDFLARE_API_TOKEN` or `CLOUDFLARE_ACCOUNT_ID` as Worker runtime variables. Those are deployment credentials only if GitHub Actions is used for deployment. This project uses Cloudflare Workers Builds as the production deployment path, so the GitHub workflow only validates the Worker and does not deploy it.

## Runtime flow

`START PAPER BOT` manually enables `PAPER_STATE`. The Durable Object schedules one alarm at a time. Each alarm calls `paper_cycle.py`, which obtains public Indodax data and sends the analysis payload to `POST /engine/analyze` on FastAPI Cloud. FastAPI Cloud runs the existing CPython multi-agent Orchestrator and returns the normalized decision. The Durable Object records the result and schedules the next cycle only while the manual gate remains ON.

FastAPI Cloud does not own the paper session, does not start a background trading loop, and does not submit exchange orders.

## Health checks

Open these URLs after deployment:

- `/` — confirms the service is online
- `/health` — process health
- `/ready` — confirms the shared secret is configured and real trading remains locked

`/engine/analyze` is intentionally authenticated and should return `401` without `X-AI-Engine-Key`.

## Required connection test

1. Open the FastAPI Cloud URL and verify `/health` returns `healthy`.
2. Verify `/ready` returns `ready` and `ai_engine_secret_configured: true`.
3. Put the same `AI_ENGINE_SHARED_SECRET` into the Cloudflare Worker secret store.
4. Put the FastAPI Cloud URL into the Cloudflare Worker variable `AI_ENGINE_URL`.
5. Deploy the Cloudflare Worker from Workers Builds.
6. Log in to the dashboard.
7. Confirm the dashboard reports database/market health before starting paper mode.
8. Press `START PAPER BOT` manually.
9. Wait for the first Durable Object alarm and confirm `Cycles` becomes `1`.
10. Confirm the latest decision contains `agents_invoked` and Orchestrator data.
11. Press `STOP PAPER BOT` and confirm the cycle counter stops increasing.

If step 9 fails, do not change the architecture. Inspect the Worker logs and the `/ready` response first.
