# FastAPI Cloud AI Engine

FastAPI Cloud is the external CPython execution layer for the heavy multi-agent AI analysis. Cloudflare Workers remains the dashboard/control plane, and the `PaperTradingState` Durable Object remains the authoritative manual ON/OFF gate and paper-account ledger.

## FastAPI Cloud app settings

Use the repository root. Do **not** set the Application Directory to `fronted` or `backend`.

- Repository: `doushitekana62-ship-it/ai-multi-agent-trading-bot`
- Application Directory / Root Directory: **leave empty**
- Entrypoint: `fastapi_cloud_app:app` (already declared in the root `pyproject.toml`)
- Python: use a supported CPython version in the repository range `>=3.11,<3.14`

The root `pyproject.toml` contains the production dependencies required by the existing Orchestrator, including NumPy, Pandas, SciPy and scikit-learn. This is important because those packages must not be imported by the Cloudflare Python Worker itself.

FastAPI recommends declaring the application entrypoint in `pyproject.toml`, especially when using deployment tools that need to discover the app automatically.

## FastAPI Cloud secret

Create exactly one secret:

`AI_ENGINE_SHARED_SECRET`

Use a random value of at least 32 characters. It must be identical to the Cloudflare Worker secret with the same name.

Do not put the value in GitHub, `.env.example`, frontend code, or source files.

## Cloudflare Worker variables and secrets

These are **runtime Worker variables/secrets**. They are different from the `Variables and secrets` section under Workers Builds, which only affects the build environment.

On the Worker, configure:

Normal runtime variable:

`AI_ENGINE_URL` = the HTTPS base URL of the FastAPI Cloud application, for example `https://<your-app>.fastapicloud.dev`

Runtime secrets:

- `AI_ENGINE_SHARED_SECRET` — same value as FastAPI Cloud
- `JWT_SECRET_KEY` — random secret, at least 32 characters
- `ADMIN_USERNAME` — dashboard login username
- `ADMIN_PASSWORD` — dashboard login password
- `SUPABASE_SECRET_KEY` — preferred current Supabase server secret (`sb_secret_...`)
- `SUPABASE_SERVICE_ROLE_KEY` — legacy compatibility name, accepted if already configured

`SUPABASE_URL` is pinned in `fronted/wrangler.jsonc` to the production Supabase project URL, so it does not need to be stored as a secret.

Do not put these runtime values only in Workers Builds variables. The Worker code reads them from its runtime `env` object when a request or Durable Object alarm executes.

Do not add `CLOUDFLARE_API_TOKEN` or `CLOUDFLARE_ACCOUNT_ID` as Worker runtime variables. Those are deployment credentials only if GitHub Actions is used for deployment. This project uses Cloudflare Workers Builds as the production deployment path, so the GitHub workflow only validates the Worker and does not deploy it.

## Runtime flow

`START PAPER BOT` manually enables `PAPER_STATE`. The Durable Object schedules one alarm at a time. Each alarm calls `paper_cycle.py`, which obtains public Indodax data and sends the analysis payload to `POST /engine/analyze` on FastAPI Cloud. FastAPI Cloud runs the existing CPython multi-agent Orchestrator and returns the normalized decision. The Durable Object records the result and schedules the next cycle only while the manual gate remains ON.

The Worker now checks `AI_ENGINE_URL` and `AI_ENGINE_SHARED_SECRET` before enabling paper mode. If either is missing, START returns a configuration error instead of turning the bot ON and waiting for a cycle to fail later.

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
3. Put the same `AI_ENGINE_SHARED_SECRET` into the **Cloudflare Worker runtime secret store**.
4. Put the FastAPI Cloud URL into the **Cloudflare Worker runtime variable store** as `AI_ENGINE_URL`.
5. Ensure the Worker runtime has either `SUPABASE_SECRET_KEY` or the legacy `SUPABASE_SERVICE_ROLE_KEY` configured with the server-side Supabase credential.
6. Deploy the Cloudflare Worker from Workers Builds.
7. Open `GET /api/system/health?deep=1` and require `database.connected: true` and `database.reason: rest_probe_ok`.
8. Log in to the dashboard.
9. Confirm the dashboard reports database/market health before starting paper mode.
10. Press `START PAPER BOT` manually.
11. Wait for the first Durable Object alarm and confirm `Cycles` becomes `1`.
12. Confirm the latest decision contains `agents_invoked` and Orchestrator data.
13. Press `STOP PAPER BOT` and confirm the cycle counter stops increasing.

If START reports `ai_engine_not_configured`, fix the Worker runtime variables/secrets first. If the first alarm still fails after START succeeds, inspect the Worker logs and the FastAPI `/ready` response before changing the architecture.
