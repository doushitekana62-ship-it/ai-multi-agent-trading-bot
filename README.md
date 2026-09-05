# Compound Scalping

Architecture:

Cloudflare Workers dashboard -> FastAPI -> Freqtrade -> Exchange
                                      -> Supabase Auth / Postgres / Realtime

Cloudflare serves the dashboard and proxies `/api/*` to FastAPI. Browser authentication uses Supabase Auth with the publishable/anon key. FastAPI validates the Supabase access token and uses the user's token for RLS-protected database reads. The service-role key is backend-only.

## Cloudflare

Connect this repository to Cloudflare Workers. Build command: leave empty. Deploy command: `npx wrangler deploy`.

Configure these Worker variables:
- `FASTAPI_URL`: public HTTPS URL of FastAPI
- `SUPABASE_URL`: Supabase project URL
- `SUPABASE_ANON_KEY`: Supabase publishable/anon key

The dashboard is in `public/` and the Worker proxy is `cloudflare/worker.js`.

## FastAPI / Docker

Copy `.env.example` to `.env`, fill the values, then run `docker compose up --build`.

API: `http://localhost:8000`
Health: `http://localhost:8000/api/health`

## Supabase

Run `supabase/schema.sql` in the Supabase SQL Editor. It creates the initial settings, positions, signal decisions, trade logs, bot health tables and RLS policies.

Never put `SUPABASE_SERVICE_ROLE_KEY` in Cloudflare or browser code.

## Freqtrade

Freqtrade remains the trading engine. Run it from the separate Freqtrade repository or another server and set `FREQTRADE_URL`, username and password in the FastAPI environment.
