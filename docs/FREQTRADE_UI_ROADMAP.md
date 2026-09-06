# FreqUI / Freqtrade Function Roadmap

## Source of truth

The frontend is built from the official Freqtrade FreqUI repository, pinned to commit `5cade05d3fef32dee505609eff1a374d80939083`, corresponding to FreqUI 3.1.2.

The build workflow clones that upstream source and only applies the minimum integration changes required for this deployment:

1. GitHub Pages base path: `/ai-multi-agent-trading-bot/`.
2. Default API URL: the FastAPI Cloud application URL.
3. Default FreqUI username: `doushitekana`.

The FreqUI application code is not reimplemented as a custom dashboard.

## Architecture boundary

```text
GitHub Pages
  -> official FreqUI 3.1.2
  -> FastAPI Cloud /api/v1/* bridge
  -> embedded Freqtrade native REST API /api/v1/*
  -> embedded Freqtrade engine
  -> Indodax through CCXT
```

FastAPI is a transport/authentication boundary for the remote browser. FreqUI remains the source of dashboard behavior and calls the native Freqtrade API.

## Main navigation room tour

| Menu | Official FreqUI route | Function | Native Freqtrade dependency | Status in this project |
|---|---|---|---|---|
| Trade | `/trade` | Bot controls, pair summary, bot status, performance, balance, time breakdown, live pairlist, pair locks, open trades, closed trades, trade detail, live candle chart | `/status`, `/count`, `/profit`, `/balance`, `/daily`, `/performance`, `/whitelist`, `/locks`, `/trades`, `/pair_candles`, `/trade/<id>` and related endpoints | Integrated through official FreqUI + bridge |
| Dashboard | `/dashboard` | Profit over time, bot comparison, all open trades, cumulative profit, wallet history, closed trades, profit distribution, trades log | `/daily`, `/profit`, `/trades`, `/status`, `/balance` and related data endpoints | Integrated through official FreqUI + bridge |
| Chart | `/graph` | Interactive market chart using pair candles, timeframe, strategy plot configuration and trade information | `/pair_candles`, `/plot_config`, `/trades` | Integrated through official FreqUI + bridge |
| Logs | `/logs` | Live/recent Freqtrade log viewer | `/logs` and websocket messages | Integrated through official FreqUI + bridge |
| Settings | `/settings` | UI-only preferences: layout lock/reset, open-trade header display, timezone, background sync, exit confirmation, multipane labels, chart settings, notifications, backtest metric selection | Mostly browser/local UI state; notification behavior uses websocket messages | Integrated through official FreqUI |
| Backtest | `/backtest` | Load historic results, run backtest, analyze result, compare results, visualize summary, visualize result | Backtest/webserver API capabilities | Available only when Freqtrade webserver mode exposes the required features |
| Analysis / Recursive | `/recursive_analysis` | Recursive analysis of strategy indicator calculations | Freqtrade recursive-analysis API | Available only when native bot feature is enabled |
| Analysis / Lookahead | `/lookahead_analysis` | Lookahead-analysis checks for strategy bias | Freqtrade lookahead-analysis API | Available only when native bot feature is enabled |
| Download Data | `/download_data` | Download historical market data supported by Freqtrade | Download-data/webserver API | Available only when native bot feature is enabled |
| Pairlist Config | `/pairlist_config` | Configure/test pairlist configuration through Freqtrade's pairlist configurator | Pairlist configuration API | Available only when native bot feature is enabled |

The official navigation source controls visibility of these menus according to bot mode and reported bot features. This means a missing menu in a particular runtime is not automatically a frontend bug.

## Trade page room tour

The official Trade page contains:

- Multi Pane with Bot Controls.
- Pairs combined / pair summary.
- General / bot status.
- Performance.
- Balance.
- Time Breakdown.
- Pairlist.
- Pair Locks.
- Open Trades.
- Closed Trades with filtering.
- Trade Detail when a trade is selected.
- Candle Chart with pair/timeframe refresh.

The source is `src/pages/trade.vue` in FreqUI 3.1.2.

## Dashboard page room tour

The official Dashboard page contains these dashboard widgets:

1. Profit over time.
2. Bot comparison.
3. Open Trades.
4. Cumulative Profit.
5. Wallet History.
6. Closed Trades with filtering.
7. Profit Distribution.
8. Trades Log.

The dashboard uses a draggable/resizable grid and stores the layout through the FreqUI layout store. The source is `src/pages/dashboard.vue` in FreqUI 3.1.2.

## Native Freqtrade API coverage

The pinned Freqtrade source exposes the native `/api/v1/*` API. The relevant endpoint families include:

### Readiness and bot state

- `GET /ping`
- `GET /version`
- `GET /health`
- `GET /show_config`
- `GET /sysinfo`
- `GET /count`
- `GET /status`

### Trading and trade management

- `GET /trades`
- `GET /trade/<tradeid>`
- `DELETE /trades/<tradeid>`
- `DELETE /trades/<tradeid>/open-order`
- `POST /trades/<tradeid>/reload`
- `POST /forceexit`
- `POST /forceenter`
- `POST /start`
- `POST /pause`
- `POST /stop`
- `POST /stopbuy`
- `POST /reload_config`

### Performance and balances

- `GET /profit`
- `GET /performance`
- `GET /balance`
- `GET /daily`
- `GET /weekly`
- `GET /monthly`
- `GET /stats`
- `GET /entries`
- `GET /exits`
- `GET /mix_tags`

### Pair and market data

- `GET /whitelist`
- `GET /blacklist`
- `POST /blacklist`
- `DELETE /blacklist`
- `GET /locks`
- `POST /locks`
- `DELETE /locks/<lockid>`
- `GET/POST /pair_candles`
- `GET/POST /pair_history`
- `GET /plot_config`
- `GET /strategies`
- `GET /strategy/<strategy>`

### Data and analysis

- `GET /available_pairs`
- Backtest endpoints used by the official FreqUI webserver mode.
- Recursive analysis endpoints used by the official Recursive Analysis view.
- Lookahead analysis endpoints used by the official Lookahead Analysis view.
- Download-data endpoints used by the official Download Data view.
- Pairlist configuration endpoints used by the official Pairlist Configurator.

### Realtime channel

- WebSocket `/api/v1/message/ws`

Freqtrade uses this websocket for realtime bot/RPC messages, including trade and other bot events. The project FastAPI layer proxies this websocket instead of replacing it with a custom dashboard event system.

## Authentication contract

FreqUI 3.1.2 logs in using HTTP Basic authentication against:

`POST /api/v1/token/login`

The project contract is:

- Username: `doushitekana`
- Password: the existing `DASHBOARD_TOKEN` environment variable in FastAPI Cloud.
- Freqtrade generates access and refresh JWT tokens using its native authentication implementation.
- FreqUI stores and refreshes those tokens using its own login store.

The dashboard token is never committed to this repository.

## Verification roadmap

The implementation must be verified in this order. Do not mark a later item complete when an earlier dependency is broken.

### Phase 1 - Source parity

- [x] Build from official FreqUI 3.1.2 source.
- [x] Pin the upstream FreqUI source commit.
- [x] Do not maintain a parallel custom dashboard implementation.
- [x] Keep only deployment-specific integration patches.

### Phase 2 - Authentication

- [x] Enable native Freqtrade API inside the embedded worker.
- [x] Proxy `/api/v1/*` through FastAPI.
- [x] Proxy `/api/v1/message/ws` through FastAPI.
- [x] Use `doushitekana` as Freqtrade API username.
- [x] Use `DASHBOARD_TOKEN` as the Freqtrade API password.
- [ ] Verify login from the deployed GitHub Pages UI against the live FastAPI deployment.

### Phase 3 - Core live UI

- [ ] Trade page loads bot state.
- [ ] Dashboard widgets receive real data.
- [ ] Chart loads candles and trades.
- [ ] Logs load through the native API.
- [ ] WebSocket connects and realtime updates arrive.
- [ ] Start/pause/stop controls operate through native Freqtrade endpoints.
- [ ] Open/closed trade operations work through native Freqtrade endpoints.

### Phase 4 - Webserver-only functions

- [ ] Backtest run and result analysis.
- [ ] Backtest result comparison and visualization.
- [ ] Download Data.
- [ ] Pairlist Config.
- [ ] Recursive Analysis.
- [ ] Lookahead Analysis.

These functions are dependent on the corresponding Freqtrade webserver capabilities. They must not be replaced with custom mock implementations.

### Phase 5 - Regression verification

For every FreqUI menu/function above:

1. Identify the FreqUI component/composable responsible for the action.
2. Identify the native Freqtrade endpoint(s) it calls.
3. Confirm the FastAPI bridge forwards the same HTTP method, path, query parameters, body, and relevant headers.
4. Confirm the embedded Freqtrade process exposes the endpoint.
5. Test the function from the deployed UI.
6. Record failures against the native Freqtrade dependency instead of silently changing FreqUI behavior.

## Explicit non-goals for this phase

This roadmap does not introduce new trading strategy logic, compounding rules, signal scoring, risk rules, or other bot ideas. The immediate objective is Freqtrade/FreqUI functional parity and a working transport bridge.
