# Deployment and Secrets Guide

## Architecture

The static website is only the dashboard. All Python trading logic runs on the FastAPI host.

GitHub Pages/static HTML-CSS-JS -> FastAPI -> embedded Freqtrade Worker -> CCXT -> Indodax
                                          |
                                          +-> local SQLite persistence

There is no Supabase dependency and no Freqtrade HTTP API service. The FastAPI process starts and stops the Freqtrade Worker directly.

## 1. Create the server environment

Copy `.env.example` to `.env` on the FastAPI host. Do not commit `.env`.

Required values:

- `DASHBOARD_TOKEN`: long random token used by the dashboard to authenticate to FastAPI.
- `FREQTRADE_DB_PATH`: persistent path for the local Freqtrade SQLite database.
- `INDODAX_API_KEY`: Indodax API key with trading permissions only.
- `INDODAX_API_SECRET`: matching Indodax API secret.

The dashboard token is entered in the browser and stored in localStorage. It is never committed to GitHub.

## 2. Keep the bot in paper mode first

Set:

`TRADING_MODE=paper`

In paper mode the engine does not submit live orders. Do not change to `live` until the whole stack has been tested and the strategy has been evaluated.

## 3. Configure Indodax

Set:

`EXCHANGE_NAME=indodax`
`INDODAX_API_KEY=...`
`INDODAX_API_SECRET=...`

The credentials are injected into the embedded Freqtrade exchange configuration at runtime. They never enter the static website.

## 4. Configure GitHub Pages

The repository deploys `public/` through GitHub Pages. Set `CORS_ORIGINS` on FastAPI to the exact origin serving the dashboard.

## 5. FastAPI deployment

Build and run the Docker image on the FastAPI host. The image contains the Freqtrade source under `vendor/freqtrade` and installs it locally. The runtime does not call a Freqtrade REST endpoint.

Make sure `/app/data` is backed by persistent storage if the hosting platform replaces containers. Without persistent storage, the SQLite history can be lost on redeploy/restart.

## 6. Health checks

`GET /api/health` reports FastAPI, embedded Freqtrade, and local SQLite state.

`GET /api/health/dependencies` checks local SQLite and Indodax public market compatibility.

## 7. Start sequence

1. Start FastAPI.
2. Confirm `/api/health` is healthy.
3. Open the GitHub Pages dashboard.
4. Enter `DASHBOARD_TOKEN`.
5. Start the engine while `TRADING_MODE=paper`.
6. Inspect logs and the local Freqtrade database.
7. Test restart/recovery behavior.
8. Only after validation, switch to `TRADING_MODE=live` and restart FastAPI.

## 8. Secrets that must never be committed

Never commit `.env`, database passwords, Indodax API secrets, Freqtrade JWT secrets, SSH keys, dashboard tokens, or access tokens.
