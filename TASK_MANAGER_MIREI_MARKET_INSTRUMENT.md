# Mirei Market Instrument / Broker Simulation Task Manager

Baseline: `42ebee477ab9f6b1222789502ce6d965701173cc`

## Checkpoints

- [x] C0 — Baseline audited: foreground runtime, Indodax market source, existing TradingUniverse, execution engine, re-entry path.
- [x] C1 — Define `MarketInstrument`: asset class, provider, native quote, account currency, execution-cost profile, trading-session metadata.
- [ ] C2 — Market-provider routing: exchange/provider -> instrument catalog -> market-data adapter.
- [ ] C3 — Dynamic Indodax discovery from public market API; do not hardcode the available coin universe as the source of truth.
- [ ] C4 — Add paper market-data adapters for non-crypto instruments with explicit source labels and freshness state.
- [ ] C5 — Broker-like execution: bid/ask, spread, slippage, execution latency and position-size constraints.
- [ ] C6 — All-in fee model: separate buy/sell costs, taxes/CFX where applicable, and instrument-specific fee profiles.
- [ ] C7 — Manual TP becomes target net profit in IDR; TP price is solved from execution costs instead of a raw percentage.
- [ ] C8 — TP re-entry: preserve original cycle capital as the re-entry basis; do not automatically compound profit into the next stake; re-entry remains gate-controlled.
- [ ] C9 — Effective-settings UI: display the configuration actually used by the runtime; manual risk must not visually report an active BALANCED/AGGRESSIVE/SAFETY TP/SL policy.
- [ ] C10 — Dashboard market scanner: recommend the most suitable available instrument across asset classes, with provider/source/freshness visible.
- [ ] C11 — Unit tests for market instruments, fee math, net-profit TP, re-entry basis, and provider routing.
- [ ] C12 — Android build + tests + lint/error checks.
- [ ] C13 — CI completed successfully; APK artifact downloaded and inspected.
- [ ] C14 — Final APK delivered only after C12/C13 pass.

## Guardrails

1. Paper trading remains the default. No live order path is enabled by this task.
2. An exchange is not assumed to provide an asset class merely because another exchange does. The catalog must come from the provider/exchange capability data.
3. Non-crypto market data must show its actual provider and freshness. A delayed public feed must not be presented as a broker-real-time feed.
4. Re-entry is allowed only after the existing entry/risk/freshness gates pass.
5. A manual target such as `Rp30` means net realized PnL after configured execution costs, not gross price movement.
6. The first-cycle capital remains the reference for TP re-entry unless the user explicitly changes the capital policy.
