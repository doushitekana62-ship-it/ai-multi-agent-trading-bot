# Cloudflare Build & Deploy Incident Log

Repository: `doushitekana62-ship-it/ai-multi-agent-trading-bot`
Purpose: persistent troubleshooting record for Cloudflare Pages/Workers deployment. Read this file before changing the build/deploy architecture so previous failures are not repeated.

## Current status — 2026-08-31

The latest supplied Cloudflare run has successfully completed dependency installation, the Vite production build, and the initial Wrangler/Pywrangler deployment phase. The supplied log ends while Wrangler is attaching Python modules. No failure is present in the supplied tail after that point.

Important verified facts from the latest run:
- Cloudflare build environment: Node.js `22.23.2`, npm `10.8.2`.
- `npm run build` executes `vite build`.
- Vite successfully transformed `11,635` modules.
- Production assets were generated under `build/`.
- Vite build completed successfully in about `3.34s`.
- The deployment command is `uvx --from workers-py pywrangler deploy`.
- Pywrangler successfully created the Workers Python environments and installed requirements from `pylock.toml`.
- Wrangler `4.127.1` started successfully.
- The latest log reaches `Attaching additional modules` and is truncated in the supplied message.

Do NOT treat the long `Attaching additional modules` output as an error by itself. Wait for the subsequent Wrangler result before changing deployment code.

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
- Current direct pins/overrides preserve the known working graph.

## Incident 3 — Vite parsed JSX as plain JavaScript

Observed Cloudflare failure:

`[builtin:vite-transform] Unexpected JSX expression`

Location:

`src/index.js:16:3`

The failing code contained JSX beginning with:

`<React.StrictMode>`

The project had been moved to Vite, but JSX remained in a `.js` entry file that Vite/Rolldown parsed without JSX enabled for that file.

Lesson:
- Vite must receive JSX through a supported `.jsx`/`.tsx` entry path or an explicitly configured JSX transform.
- Do not merely change the build command from CRA to Vite while leaving an incompatible source extension/configuration.

Result:
- This was fixed. The subsequent Vite build transformed 11,635 modules and completed successfully.

## Incident 4 — Node.js 20 incompatible with current Wrangler

Observed Cloudflare deployment failure:

`Wrangler requires at least Node.js v22.0.0. You are using v20.20.2.`

The build itself had already succeeded, but deployment failed when Pywrangler invoked:

`npx --yes wrangler deploy`

The dependency install also emitted EBADENGINE warnings because the resolved packages required Node `>=22.0.0`, including:
- `wrangler@4.127.1`
- `miniflare@5.20260828.0-alpha`
- `@cloudflare/kv-asset-handler@0.5.0`

Lesson:
- Cloudflare's configured Node version must be at least 22 for the currently pinned Wrangler stack.
- The earlier build-contract check claiming Node 20 was valid was stale and had to be corrected.
- Do not downgrade Wrangler merely to preserve Node 20.

Result:
- Cloudflare was changed to Node.js `22.23.2`.
- The latest run confirms Node 22 is active and Wrangler starts successfully.

## Incident 5 — misleading/stalled-looking deployment log

Observed behavior:
- Cloudflare UI/log output appeared to stop during the very large `Attaching additional modules` table.
- The output contained many Python/pyodide/Workers SDK files.

Interpretation:
- This stage is part of Python Worker packaging/deployment, not automatically a failure.
- The correct diagnostic action is to wait for the final Wrangler output or obtain the lines after the table.
- Do not modify the architecture solely because the UI appears inactive during this attachment phase.

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
5. Change the smallest relevant layer: dependency graph, frontend parser/build, Node runtime, or Python Worker deployment.
6. Record every new failure and the verified fix in this file after resolution.

This file is an operational memory for the repository. It is intentionally separate from `ARCHITECTURE.md`: `ARCHITECTURE.md` defines what the system is supposed to be; this file records what Cloudflare deployment has actually failed on and what has been verified to work.
