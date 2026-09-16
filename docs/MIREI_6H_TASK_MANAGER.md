# Mirei — 6 Hour Readiness Task Manager

Baseline: `e8e2b10002eb012b7100fa63c2f024dc3abfca9e`.

Rule: preserve existing runtime behavior unless the roadmap explicitly changes it. No UI cleanup may remove an existing control. Every phase must be checked against the previous phase before the final APK is promoted.

## Phase 0 — Architecture lock
- [x] Android `MireiDecisionEngine` + `MireiPaperTradingRuntime` remain the active paper-trading brain.
- [x] Python/Freqtrade is not part of the Android session lifecycle.
- [x] TP/SL contract is exactly AUTO or MANUAL; MANUAL may use percentage or net-IDR target.
- [x] Manual net-IDR is a net target after configured execution costs.
- [x] Live order execution remains disabled.

## Phase 1 — TP/SL brain and re-entry
- [x] Resolve TP/SL per instrument through `PositionTradeConfig`.
- [x] Manual TP/SL cannot be overridden by AUTO mode logic.
- [x] Persist per-instrument profiles with the paper session.
- [x] Persist original entry price per instrument for re-entry anchoring.
- [x] Re-entry waits for a later market tick and respects cooldown.
- [x] Re-entry must be within configurable price tolerance of the original entry price.
- [x] Add unit tests for manual-net and price-gated re-entry.

## Phase 4 — Runtime controls
- [x] `MULAI` starts a new paper session.
- [x] `LANJUTKAN` resumes a persisted paper session.
- [x] `JEDA / HOLD` pauses runtime.
- [x] `BERHENTI` stops runtime without deleting persisted state.
- [x] Risk changes are applied through the runtime, not UI-only state.
- [x] Exchange/pair selection is passed into the runtime.

## Phase 3 — Dashboard consolidation
- [x] Four primary tabs: Ringkasan, Posisi, Pasar, Log Audit.
- [x] Settings remain reachable from Ringkasan.
- [x] Existing controls are retained.
- [x] Audit view uses fixed columns: Waktu | Simbol | Event | Harga/PnL | Alasan.

## Phase 2 — Market branching
- [x] Explicit exchange branch: Indodax, Bybit, Stockbit.
- [x] Only Indodax is functionally enabled for this 6-hour test.
- [x] Pair list is filtered by the selected provider/exchange.
- [x] Instrument-specific TP/SL configuration is available before start.
- [x] Unsupported exchanges are visible as disabled, never silently mapped to another provider.

## Phase 5 — Market data / live-trading boundary
- [x] Indodax public REST remains the live paper-market source.
- [x] Bid/ask, spread, slippage and fees are retained in paper execution.
- [x] Live trading adapter remains disabled.
- [x] No API secret is required for paper market data.

## Phase 6 — Definition of Done
- [ ] CI unit tests pass.
- [ ] Debug APK builds successfully.
- [ ] Device smoke test confirms controls and persistence.
- [ ] Device smoke test confirms at least 3 instruments can run concurrently.
- [ ] Device smoke test confirms per-instrument TP/SL differences.
- [ ] Device smoke test confirms OPEN → CLOSE → RE-ENTRY audit sequence.
- [ ] Six-hour background run completes without crash or stale market data.
