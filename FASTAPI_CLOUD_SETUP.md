# FastAPI Cloud AI Engine

FastAPI Cloud is used only as the CPython AI execution layer. The Cloudflare Worker remains the dashboard/control plane and the Durable Object remains the authoritative manual paper-trading state and scheduler.

## FastAPI Cloud app settings

- Repository: `doushitekana62-ship-it/ai-multi-agent-trading-bot`
- Root Directory / Application Directory: repository root (leave it blank when the UI asks for a root directory)
- Entrypoint: `fastapi_cloud_app:app`
- Python: 3.11 or another supported 3.11–3.13 runtime

The repository root now contains `pyproject.toml` with the explicit FastAPI entrypoint and only the runtime dependencies required by the CPython AI engine.

## FastAPI Cloud environment variable

Set a secret named `AI_ENGINE_SHARED_SECRET` to a random value of at least 32 characters.

Do not commit this secret to GitHub.

## Cloudflare Worker environment variables

On the dashboard Worker set:

- `AI_ENGINE_URL` = the HTTPS base URL provided by FastAPI Cloud for this app
- `AI_ENGINE_SHARED_SECRET` = the exact same secret used by FastAPI Cloud

Mark `AI_ENGINE_SHARED_SECRET` as an encrypted secret. `AI_ENGINE_URL` may be a normal variable.

## Runtime flow

`START PAPER BOT` enables `PAPER_STATE` and schedules the Durable Object Alarm. Each alarm calls `paper_cycle.py`, which obtains public Indodax data and sends the analysis payload to `POST /engine/analyze`. FastAPI Cloud executes the existing CPython Orchestrator and returns the normalized decision. The Durable Object then records the result and schedules the next cycle while the manual gate remains ON.

FastAPI Cloud does not start a background trading loop and does not submit exchange orders.

## Health checks

- `/health` — process health
- `/ready` — configuration readiness and real-trading lock
- `/engine/analyze` — authenticated AI analysis endpoint
