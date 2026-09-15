# Mirei Market Instrument / Broker Simulation Task Manager

Baseline: `42ebee477ab9f6b1222789502ce6d965701173cc`

## Checkpoints

- [x] C0 — Baseline audited: foreground runtime, Indodax market source, existing TradingUniverse, execution engine, re-entry path.
- [x] C1 — Define `MarketInstrument`: asset class, provider, native quote, account currency, execution-cost profile, trading-session metadata.
- [x] C2 — Market-provider routing: provider -> instrument metadata -> market-data adapter.
- [ ] C3 — Dynamic Indodax discovery is implemented as a catalog provider, but the runtime/UI still uses the curated paper universe as the primary selectable catalog. This remains open until live catalog discovery drives the selection UI.
- [x] C4 — Add paper market-data adapters for non-crypto instruments with explicit provider/source and freshness state.
- [x] C5 — Broker-like execution: bid/ask-aware price adjustment, spread, slippage, execution latency audit timestamp, minimum-order constraints and instrument-specific execution profiles.
- [x] C6 — All-in fee model: separate buy/sell costs with Indodax IDR taker paper profile and instrument-specific cost profiles.
- [x] C7 — Manual TP is now a target net profit in IDR; TP price is solved from configured execution costs instead of being treated as gross percentage profit.
- [x] C8 — TP/SL re-entry preserves the original cycle capital as the reference and does not automatically compound TP profit into the next stake; re-entry remains gate-controlled.
- [x] C9 — Effective-settings UI now shows the configuration actually used: MANUAL TP/SL is shown as the effective mode, with net target and SL basis visible.
- [x] C10 — Dashboard market scanner/recommendation now ranks available instruments across Crypto, Saham, Forex and Komoditas and exposes provider/freshness metadata.
- [x] C11 — Unit tests cover market catalog metadata, broker execution behavior, AI-close warmup, manual net-profit TP, risk profiles, and re-entry behavior.
- [x] C12 — Android unit tests and debug APK build passed in CI run #270.
- [x] C13 — CI artifact downloaded and APK checksum verified locally.
- [x] C14 — APK delivered only after the successful CI build and artifact inspection.

## Current implementation boundary

- Paper trading remains the default. No live order path was enabled by this task.
- Indodax is the native crypto execution/data source.
- Yahoo Finance is used only as a public delayed market-data source for paper observation of selected stocks, forex and commodities. It is not presented as live broker connectivity.
- The architecture supports additional exchange/broker adapters through `MarketInstrument`, provider routing and `ExchangeRegistry`; additional live connectors still require their own authenticated adapter implementations.
- Dynamic Indodax catalog discovery is intentionally left as the next checkpoint because the selection UI must consume discovered instruments safely rather than silently falling back to a hardcoded list.

## Guardrails

1. An exchange is not assumed to provide an asset class merely because another exchange does. The catalog must come from provider/exchange capability data.
2. Non-crypto market data must show its actual provider and freshness. Delayed public data must not be presented as broker-real-time data.
3. Re-entry is allowed only after existing entry/risk/freshness gates pass.
4. A manual target such as `Rp30` means net realized PnL after configured execution costs, not gross price movement.
5. The first-cycle capital remains the reference for TP re-entry unless the user explicitly changes the capital policy.
