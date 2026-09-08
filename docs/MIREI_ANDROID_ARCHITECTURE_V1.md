# Mirei ミレイ — Android-First Architecture v1

Status: implementation baseline

## 1. Target architecture

```text
Android App
  ├─ UI / Dashboard
  ├─ Mirei Foreground Service
  ├─ Mirei Orchestrator
  │    ├─ Market/Data Agent
  │    ├─ Candle/Technical Agent
  │    ├─ Forecast Agent
  │    ├─ Sentiment Agent
  │    ├─ Risk Agent
  │    └─ Learning Agent
  ├─ Decision Engine
  ├─ Risk Policy
  ├─ Exchange Adapter Layer
  │    ├─ Indodax adapter
  │    ├─ Bybit adapter
  │    └─ future adapters
  ├─ Paper Execution Engine
  ├─ Live Execution Engine
  ├─ Local persistence
  └─ Android Keystore-backed credential store
```

## 2. Runtime ownership

Mirei is the orchestrator and decision owner. Freqtrade is not the application brain.

Freqtrade remains in the repository as a compatibility/execution candidate while Android feasibility is validated. The new Android execution interface must not depend on Freqtrade-specific APIs.

## 3. Runtime states

`STOP` = no new trading and runtime may sleep.

`RUNNING` = market analysis and eligible execution are active.

`HOLD` = no new positions; existing positions continue to be managed.

`CLOSE_ALL` = request closure of active positions, then return to a non-trading state.

`ERROR` = critical runtime failure requiring recovery handling.

`RECOVERY` = transitional state after an error or connectivity event.

Android reboot does not auto-start trading. Network recovery places Mirei in HOLD; the user must reopen/restart the application.

## 4. Risk invariants

- Maximum 3 simultaneous positions by default.
- Default capital Rp150,000.
- Default position size Rp50,000.
- Baseline SL 0.5% and TP 1.0%.
- TP/SL can adapt, but volatility adaptation must not silently expand the intended loss boundary.
- Extreme volatility reduces position exposure and/or changes trailing behavior.
- Daily loss limit and consecutive-loss protection are mandatory gates.
- No new entries when market data is stale, the exchange is unhealthy, or internet connectivity is unavailable.

## 5. Decision modes

### Suggestion

Mirei explains the recommendation. Important agent conflicts require human approval.

### Mirei Take Over

Explicit opt-in. Automatic parameter changes must be auditable.

## 6. Paper/live separation

Paper and live execution use the same decision and risk contracts. They differ only at the execution boundary.

Paper execution simulates fees and slippage and uses a configurable virtual balance.

Live execution must require an explicit user action and verified trade-only exchange credentials.

## 7. Security boundary

Exchange API credentials are local-only and stored with Android Keystore-backed AES-GCM encryption. Secrets are never required by the UI layer after successful storage and must not be emitted into logs.

Exchange keys must not have withdrawal permission.

## 8. Why Freqtrade is optional

Freqtrade currently assumes a Python/server-oriented runtime in this repository, while Mirei's target runtime is Android-first. Freqtrade's current exchange documentation supports Bybit, but exchange feature differences mean Mirei still needs a generic execution contract rather than coupling trading behavior to a single Freqtrade strategy implementation.

Python on Android is technically feasible using Chaquopy, which integrates Python into standard Android/Gradle projects. That is a feasibility path, not a decision to embed the full Freqtrade stack without compatibility testing.

## 9. Implementation order

1. Android runtime/state machine.
2. Local persistence and secure credentials.
3. Generic market-data contract.
4. Generic paper execution and trade ledger.
5. Mirei agents and decision orchestration.
6. Indodax adapter.
7. Bybit adapter.
8. Live trading safety gates.
9. Optional Freqtrade compatibility adapter if its Android packaging and runtime constraints pass testing.
