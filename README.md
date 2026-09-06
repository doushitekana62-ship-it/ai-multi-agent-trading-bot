# Compound Scalping

Architecture:

GitHub Pages (static dashboard) -> FastAPI -> embedded Freqtrade Worker -> CCXT -> Indodax
                                      -> local SQLite runtime state

The repository contains the Freqtrade source under `vendor/freqtrade`. FastAPI starts the Freqtrade Worker directly in a child process. There is no separate Freqtrade HTTP/API service and the application does not call `FREQTRADE_URL`.

## Static website

The frontend lives in `public/` and is compatible with GitHub Pages. Configure `public/config.js` with only the public FastAPI HTTPS base URL.

The dashboard token is entered in the browser and stored in localStorage. No Indodax secret, database password, or dashboard token belongs in `public/`.

## FastAPI / Docker

Copy `.env.example` to `.env` on the server that runs FastAPI. Run:

`docker compose up --build`

The container installs Freqtrade from `vendor/freqtrade` and exposes FastAPI on port 8000. Use one Uvicorn worker because the embedded trading runtime is process-owned by the FastAPI instance.

Health: `http://localhost:8000/api/health`
Dependency health: `GET /api/health/dependencies`
Engine status: `GET /api/engine/status` (dashboard token required)
Engine start: `POST /api/engine/start` (dashboard token required)
Engine stop: `POST /api/engine/stop` (dashboard token required)

## Indodax

This project is Indodax-only. The application ignores stale exchange environment values and always configures the supported exchange as `indodax`.

Paper mode is the default. Keep `LIVE_TRADING_ENABLED=false` until compatibility, strategy, reconciliation, and recovery tests are complete.

## Local SQLite

The FastAPI Cloud-compatible default is `/tmp/compound-scalping/tradesv3.sqlite`. The runtime and dashboard use the same writable-path resolver.

The `/tmp` filesystem is not guaranteed to persist across hosting-instance replacement. Use host/platform persistent storage for durable trade history when available.

## Secrets

Keep `.env` only on the FastAPI host. Never commit it.

Server-only secrets:

- `DASHBOARD_TOKEN`
- `INDODAX_API_KEY`
- `INDODAX_API_SECRET`

The dashboard token is entered in the browser and stored in localStorage. It is never committed to GitHub.

## Freqtrade source pin

The source vendor workflow pins the project-owned Freqtrade repository to commit:

`29186a9a0e62af7e52a0f0d386c8b02a0d4b2206`

The vendor workflow normalizes Freqtrade package metadata to a static version after copying upstream `pyproject.toml`, preventing the Cloud build from importing the package while generating metadata.

The Freqtrade package itself is GPLv3 licensed. Keep the vendored `LICENSE` file with the source.
