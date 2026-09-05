# Deployment and Secrets Guide

## Architecture

The static website is only the frontend. Trading runs on the FastAPI server.

GitHub Pages/static HTML-CSS-JS -> FastAPI -> embedded Freqtrade Worker -> CCXT -> Indodax
                                          |
                                          +-> Supabase Auth / Data API
                                          +-> Supabase PostgreSQL (Freqtrade persistence)

There is no dependency on a separate Freqtrade HTTP API service. The FastAPI process starts and stops the Freqtrade Worker directly.

## 1. Create the server environment

Copy `.env.example` to `.env` on the FastAPI host. Do not commit `.env`.

Required values:

- `SUPABASE_URL`: Supabase project URL.
- `SUPABASE_ANON_KEY`: publishable/legacy anon key used by the browser and authenticated API calls.
- `SUPABASE_SERVICE_ROLE_KEY`: server-only key. Never put it in GitHub Pages JavaScript.
- `SUPABASE_DB_URL`: PostgreSQL connection string from Supabase Connect. Freqtrade stores its persistence tables in the private `freqtrade` schema.
- `BOT_OWNER_USER_ID`: UUID of the Supabase Auth user allowed to start and stop the engine.
- `INDODAX_API_KEY`: Indodax API key with trading permissions only.
- `INDODAX_API_SECRET`: matching Indodax API secret.

Supabase currently provides a full PostgreSQL database. For a persistent FastAPI server, use the Direct connection when IPv6 is available or the Supavisor Session pooler when the host is IPv4-only. See the Supabase Connect panel for the exact connection string.

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

## 4. Configure the owner

`BOT_OWNER_USER_ID` must equal the UUID of the intended Supabase Auth account. The API rejects engine start/stop requests from any other authenticated user.

## 5. Configure GitHub static frontend

Set `CORS_ORIGINS` to the exact origin serving the static frontend, for example:

`https://YOUR-GITHUB-USERNAME.github.io`

or, for a project site:

`https://YOUR-GITHUB-USERNAME.github.io/YOUR-REPOSITORY`

Do not use `*` in production.

## 6. FastAPI deployment

Build the Docker image from the repository after the Freqtrade vendor workflow has populated `vendor/freqtrade`.

`docker compose up -d --build`

The image contains the Freqtrade source under `vendor/freqtrade` and installs it locally. The runtime does not call a Freqtrade REST endpoint.

## 7. Health checks

`GET /api/health` verifies FastAPI configuration, the Supabase REST endpoint, and the local Freqtrade process state.

`GET /api/engine/status` requires Supabase authentication and owner authorization.

## 8. Start sequence

1. Start FastAPI.
2. Confirm `/api/health` is healthy.
3. Log in through the static dashboard.
4. Confirm the dashboard sees the expected Supabase user.
5. Start the engine while `TRADING_MODE=paper`.
6. Inspect logs and Freqtrade persistence tables.
7. Test restart/recovery behavior.
8. Only after validation, switch to `TRADING_MODE=live` and restart FastAPI.

## 9. Secrets that must never be committed

Never commit `.env`, database passwords, Supabase service-role keys, Indodax API secrets, Freqtrade JWT secrets, SSH keys, or access tokens.

The repository already ignores `.env` and `.env.*` except `.env.example`.
