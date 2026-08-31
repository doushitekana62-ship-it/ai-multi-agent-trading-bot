# Cloudflare Build & Deploy Incident Log

Repository: `doushitekana62-ship-it/ai-multi-agent-trading-bot`
Purpose: persistent troubleshooting record for Cloudflare Pages/Workers deployment. Read this file before changing the build/deploy architecture so previous failures are not repeated.

## Current status — 2026-08-31

The latest supplied Cloudflare run successfully completed dependency installation, the Vite production build, and the Wrangler/Pywrangler deployment startup. Node.js `22.23.2` is active and Wrangler `4.127.1` starts successfully.

A live dashboard run then exposed two application-level problems after deployment:
1. `decision_persistence_failed` because the production `public.decisions` schema was missing fields already being sent by the paper-cycle writer.
2. Market Pulse displayed its container but no green/red/gray blocks because the UI received no trade points and therefore produced an empty segment array.

The decision persistence schema has now been repaired directly in the production Supabase project and the matching migration has been committed to GitHub. The Market Pulse component has also been updated so it always renders a 30-minute block timeline and falls back to observing the public ticker every 5 seconds when the public trade stream is unavailable.

## Incident 1 — CRA/MUI build failure

Observed Cloudflare failure:

`Attempted import error: 'elementAcceptingRef' is not exported from '@mui/utils'`

Context:
- Cloudflare Node.js was `20.20.2`.
- The frontend was using `react-scripts build` / Create React App.
- MUI packages were pinned/overridden around version `5.14.x`.
- The failure occurred during `react-scripts build`.

Lesson:
- The MUI/CRA dependency graph was incompatible with the resolved `@mui/utils` export surface.
- Do not reintroduce the old CRA build path.
- The project was subsequently migrated to Vite.

## Incident 2 — Invalid MUI dependency pin

Observed Cloudflare dependency installation failure:

`error: No version matching "5.14.0" found for specifier "@mui/utils" (but package exists)`

and similar errors for:
- `@mui/styled-engine@5.14.0`
- `@mui/private-theming@5.14.0`

The log showed that the actually resolved published versions included:
- `@mui/utils@5.14.1`
- `@mui/styled-engine@5.13.2`
- `@mui/private-theming@5.13.7`

Lesson:
- Do not force every MUI internal package to `5.14.0`.
- Keep the published compatibility graph rather than inventing nonexistent package versions.

## Incident 3 — Vite parsed JSX as plain JavaScript

Observed Cloudflare failure:

`[builtin:vite-transform] Unexpected JSX expression`

Location:

`src/index.js:16:3`

Lesson:
- JSX must use a supported `.jsx`/`.tsx` entry path or an explicit JSX transform.
- Do not merely change the build command from CRA to Vite while leaving incompatible source extensions.

Result:
- Fixed. The subsequent Vite build transformed 11,635 modules and completed successfully.

## Incident 4 — Node.js 20 incompatible with current Wrangler

Observed Cloudflare deployment failure:

`Wrangler requires at least Node.js v22.0.0. You are using v20.20.2.`

The build had succeeded, but deployment failed when Pywrangler invoked `npx --yes wrangler deploy`.

Lesson:
- Current Wrangler stack requires Node `>=22.0.0`.
- Do not downgrade Wrangler just to preserve Node 20.

Result:
- Cloudflare was changed to Node.js `22.23.2`.
- Latest deployment logs confirm Node 22 and Wrangler startup succeed.

## Incident 5 — misleading/stalled-looking deployment log

Observed behavior:
- Cloudflare UI appeared to stop during the very large `Attaching additional modules` table.
- Output contained Python/pyodide/Workers SDK files.

Interpretation:
- This stage is Python Worker packaging, not automatically an error.
- Wait for the final Wrangler result before changing deployment architecture.

## Incident 6 — `decision_persistence_failed` / Supabase HTTP 400

Observed dashboard state:

`decision_persistence_failed`

Supabase API logs confirmed repeated:

`POST | 400 | https://opclkckfdlkqzunzmwym.supabase.co/rest/v1/decisions`

The production `public.decisions` schema was inspected directly. It contained the newer observability fields such as `cycle_id`, `session_id`, `pulse_status`, `current_pulse_status`, `pulse_net_move_30m_pct`, `agent_details`, `hold_analysis`, `execution_gate`, `market_snapshot`, `persistence_status`, `market_regime`, `data_quality_status`, and execution diagnostics.

However, two fields expected by the current cycle contract were missing:
- `raw_action`
- `pulse_segments`

This was not a generic Supabase connectivity failure: the same project successfully returned `GET /rest/v1/decisions?select=id&limit=1` with HTTP 200 while decision inserts returned HTTP 400.

The repository's Worker read contract also explicitly requested both `raw_action` and `pulse_segments`, confirming schema/code drift.

Fix applied directly to production Supabase:

`ALTER TABLE public.decisions ADD COLUMN IF NOT EXISTS raw_action text;`

`ALTER TABLE public.decisions ADD COLUMN IF NOT EXISTS pulse_segments jsonb NOT NULL DEFAULT '[]'::jsonb;`

The database was rechecked and both columns now exist with the expected types/default.

The same repair is committed to GitHub as:

`supabase/migrations/20260831070000_repair_decision_persistence_and_market_pulse.sql`

Rule:
- When a cycle reports persistence failure, inspect the actual production `decisions` schema and the cycle writer payload together. Do not assume credentials or RLS are the cause when the API probe is healthy.

## Incident 7 — Market Pulse container rendered but blocks were missing

Observed dashboard:
- `MARKET PULSE · ROLLING 30 MINUTES` container was visible.
- The labels `30 menit lalu`, `sekarang`, and price metrics were visible.
- The expected 30 green/red/gray blocks were absent.

Root cause in the UI path:
- `MarketPulseLegend` generated blocks only after receiving `market.points`.
- The deployed `/api/market/overview` response could contain a valid ticker (`last`, high, low, volume) while the public trade stream contained no usable points.
- With an empty `points` array, the component returned `segments: []`, so the block row had nothing to render.

The public INDODAX API documentation confirms the public trades endpoint provides trade rows with timestamp/date, price, amount, trade id, and type. The live endpoint can nevertheless be unavailable to a browser/Worker at a given moment, so the dashboard must not make the entire visual pulse disappear when trade observations are unavailable.

Fix applied to `fronted/src/components/MarketPulseLegend.jsx`:
- Always constructs a 30-minute timeline.
- Uses public trade points when available.
- Falls back to the public ticker's observed price every 5 seconds when trade points are unavailable.
- Buckets observations by minute.
- Any observed price change within a minute is marked as movement.
- Positive movement is GREEN/UP.
- Negative movement is RED/DOWN.
- No observed change is GRAY/FLAT.
- No observations for a minute remain GRAY with reduced opacity.
- The current minute is highlighted.
- The component retains the last valid pulse through transient request failures and never invents direction when the request itself fails.

Important design rule:
- The pulse is an observation layer for the trading engine, not merely decorative UI. It must remain populated from real public market observations and must not silently turn an unavailable data source into a fabricated market direction.

## Build/deployment contract that must be preserved

Frontend:
- Vite, not Create React App.
- `npm run build` -> `vite build`.
- Vite output directory: `build`.
- `vite.config.mjs` uses `@vitejs/plugin-react`.

Cloudflare Worker:
- Entry point: `./worker_entry_api.py`.
- Python Workers compatibility flag is enabled.
- Static assets are served from `./build` using the `ASSETS` binding.
- Deployment is performed through `pywrangler` because the Worker contains Python dependencies.

Current package/runtime facts verified in repository/logs:
- React `18.3.1`
- React DOM `18.3.1`
- Vite `8.2.2`
- `@vitejs/plugin-react` `6.1.1`
- Wrangler `4.127.1`
- Node.js required by current deployment stack: `>=22.0.0`
- `@mui/material` `5.14.0`
- `@mui/icons-material` `5.14.0`
- `@mui/system` `5.14.0`
- `@mui/utils` `5.14.1`
- `@mui/private-theming` `5.13.7`
- `@mui/styled-engine` `5.13.2`

## Diagnostic rule for future sessions

When a new Cloudflare error occurs:
1. Read this file first.
2. Compare the new log against the incidents above.
3. Do not repeat a previously disproven fix.
4. Identify the first actual `error`, not merely warnings or long progress output.
5. Inspect both the deployed code contract and the actual production database schema when persistence is involved.
6. Change the smallest relevant layer: dependency graph, frontend parser/build, Node runtime, data-source adapter, UI observation layer, or database schema.
7. Record every new failure and the verified fix in this file after resolution.

This file is an operational memory for the repository. It is intentionally separate from `ARCHITECTURE.md`: `ARCHITECTURE.md` defines what the system is supposed to be; this file records what Cloudflare deployment has actually failed on and what has been verified to work.
