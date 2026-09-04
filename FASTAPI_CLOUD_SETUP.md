# FastAPI Cloud setup

FastAPI Cloud is the production CPython API layer. GitHub Pages hosts only the frontend. Supabase stores application data. Cloudflare Workers, Durable Objects, Wrangler, and Workers Builds are not part of the production architecture.

## Application settings

Use the repository root as the application directory.

- Repository: `doushitekana62-ship-it/ai-multi-agent-trading-bot`
- Root / Application Directory: repository root
- Entrypoint: `backend.api:app`
- Python: a supported CPython version in `>=3.11,<3.14`

The canonical entrypoint is declared in the root `pyproject.toml`:

`[tool.fastapi] entrypoint = "backend.api:app"`

`fastapi_cloud_app.py` and `main.py` are compatibility entrypoints that import the same canonical `backend.api:app`. They do not contain a separate application.

## Runtime environment

Configure the required server-side environment variables in FastAPI Cloud. At minimum, the production API needs the Supabase connection values used by `backend.core.database`.

Do not expose server secrets through GitHub Pages or any `VITE_*` variable. The frontend only receives the public HTTPS API base URL as `VITE_API_URL`.

## Health verification

After deployment, verify:

- `/` reports the FastAPI service and current version.
- `/health` returns `status=healthy`, `entrypoint=backend.api:app`, `paper_mode=true`, and `real_trading_locked=true`.
- `/ready` reports the Supabase connection state and keeps real trading locked.

The production safety contract is paper-only. The API must never submit real exchange orders.

## Frontend connection

Set the GitHub repository variable `VITE_API_URL` to the actual FastAPI Cloud HTTPS URL. If the variable is absent, the Pages workflow uses the repository's current FastAPI Cloud URL fallback.

The GitHub Pages workflow builds `fronted/` and publishes it under the repository Pages path. It does not deploy backend code.

## Deployment troubleshooting

If the public FastAPI URL still returns an older `/health` response containing only legacy runtime fields, the repository code is not the problem: the FastAPI Cloud application is serving an older deployment. Trigger/redeploy the FastAPI Cloud application from its dashboard and ensure it is connected to the `main` branch at the repository root with `backend.api:app` as the entrypoint.

The repository CI gate will reject a stale FastAPI deployment rather than silently treating an older application as production-ready.
