# Compound Scalping

Architecture:

GitHub Pages (static dashboard) -> FastAPI -> embedded Freqtrade Worker -> CCXT -> Indodax
                                      -> Supabase Auth / Data API
                                      -> Supabase PostgreSQL

The repository contains the Freqtrade source under `vendor/freqtrade`. FastAPI starts the Freqtrade Worker directly in a child process. There is no separate Freqtrade HTTP/API service and the application does not call `FREQTRADE_URL`.

## Static website

The frontend lives in `public/` and is compatible with GitHub Pages. Configure `public/config.js` with only:

- `supabaseUrl`: Supabase project URL
- `supabaseAnonKey`: publishable/legacy anon key
- `apiBaseUrl`: public HTTPS base URL of FastAPI, ending in `/api`

No Indodax secret, database password, or Supabase service-role key belongs in `public/`.

## FastAPI / Docker

Copy `.env.example` to `.env` on the server that runs FastAPI. Run:

`docker compose up --build`

The container installs Freqtrade from `vendor/freqtrade` and exposes FastAPI on port 8000. Use one Uvicorn worker because the embedded trading runtime is process-owned by the FastAPI instance.

Health: `http://localhost:8000/api/health`
Engine status: `GET /api/engine/status` (authenticated owner only)
Engine start: `POST /api/engine/start` (authenticated owner only)
Engine stop: `POST /api/engine/stop` (authenticated owner only)

## Supabase

The application data tables remain in `public` with RLS. Freqtrade persistence is placed in a separate `freqtrade` PostgreSQL schema. That schema is revoked from `anon` and `authenticated`, while the server database connection can use it.

The connected Supabase project is PostgreSQL 17. The repository's `supabase/schema.sql` documents the schema separation; the actual project contains the expanded application tables used by the scalping dashboard.

## Secrets

Keep `.env` only on the FastAPI host. Never commit it.

Server-only secrets:

- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_DB_URL` (contains the database password)
- `INDODAX_API_KEY`
- `INDODAX_API_SECRET`

Browser-safe values:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY` / publishable key
- public FastAPI URL

See `DEPLOYMENT_SECRETS.md` for the complete setup order and safety checks.

## Freqtrade source pin

The source vendor workflow pins the project-owned Freqtrade repository to commit:

`29186a9a0e62af7e52a0f0d386c8b02a0d4b2206`

The Freqtrade package itself is GPLv3 licensed. Keep the vendored `LICENSE` file with the source.
