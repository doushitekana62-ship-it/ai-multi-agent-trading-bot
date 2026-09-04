# Frontend dashboard

Static HTML/CSS/JS dashboard. FastAPI should serve `frontend/index.html` and `frontend/login.html`, expose `GET /config` with the public Supabase URL + anon key, and mount `/static` to this directory (or copy these assets into the FastAPI static directory).

Expected API contracts used by the UI:

- `GET /config`
- `GET /dashboard/summary?mode=paper|live`
- `GET /coins/allocated`
- `GET /coins/available`
- `POST /coins/allocate`
- `GET /positions/active?mode=paper|live`
- `GET /positions/history?limit=5&mode=paper|live`
- `GET /forecast/signals/latest`
- `POST /trading/mode` with `{ "mode": "paper" | "live" }`
- `POST /bot/toggle`

The browser sends the Supabase access token as `Authorization: Bearer <JWT>` to FastAPI. The realtime client subscribes to `positions` in live mode and `paper_positions` in paper mode, plus `forecast_signals` in both modes.
