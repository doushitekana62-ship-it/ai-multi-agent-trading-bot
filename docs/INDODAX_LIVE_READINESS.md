# Indodax LIVE readiness audit — staged rollout

Status: **Stage 1 only — read-only account connectivity. LIVE order execution remains locked.**

## Current implementation audit

- `IndodaxAccountClient` calls the Indodax private `getInfo` method and reads available/held balances. This is account-read access; it does not place orders.
- `LocalExchangeCredentialStore` encrypts the API key and secret using Android Keystore + AES-GCM and stores ciphertext in app-private preferences.
- `LiveBroker.executionEnabled` is false and every broker operation fails closed. `LiveBrokerSafetyTest` asserts this lock.
- `MireiForegroundService` remains the PAPER runtime. No LIVE execution path is wired to the strategy engine.
- This branch migrates account reads to the documented Trade API V2 `GET https://tapi.indodax.com/api/v2/account` endpoint, signs the query string with HMAC-SHA512, and reads available (`free`) plus locked balances. The account response does not provide exchange server time, so the snapshot timestamp is the local request timestamp.
- The account screen must not treat malformed or missing IDR balance fields as zero. This branch makes balance parsing fail closed instead.

## Stages

### Stage 1 — read-only (this branch)
- Use an Indodax API key with **Reading / View Only** permission.
- Use the documented TAPI V2 account endpoint and signing contract; validate credentials, request success, required balance fields, numeric format, finite values, non-negative balances, and duplicate/missing asset rows.
- Never log API key, secret, request signature, or full credential payload.
- Report connection success only after a valid account snapshot is returned.
- No order creation/cancellation, withdrawal, or automatic trading.

### Stage 2 — reconciliation design (not implemented)
Before order support, design and test:
- Current balances and held funds vs open orders and recent order/trade history.
- Unique client order IDs / idempotency and duplicate-submit prevention.
- Durable states for submit-sent, acknowledgement, partial fill, full fill, cancel pending, rejected, timeout/unknown, and reconciliation.
- On timeout/restart, query the exchange before any retry. Never blindly resubmit an uncertain order.
- Real executed quantity, average fill price, exchange fees, and asset denomination must drive position/PnL.
- Distinguish exchange-owned assets from Mirei-managed positions; do not assume every account holding belongs to the bot.
- Per-symbol close failures must leave the position visible and block false “closed” state.

### Stage 3 — risk and operations gate (not implemented)
- Hard cap on IDR per order, total exposure, position count, daily loss, and repeated API failures.
- Enforce minimum notional/lot/precision per pair and fresh-price checks.
- Validate SL/TP feasibility against real fills and current fees; SPEC_RUMUS rules must be explicitly reconciled with exchange execution semantics.
- Emergency stop must stop new entries; position exit behavior must be explicit and independently tested.
- Foreground service/background restrictions, connectivity recovery, process death, and restart reconciliation must be tested on real devices.
- Separate PAPER and LIVE state/ledger/session namespaces and show the mode persistently.
- API key must have only the minimum permissions needed. **Never enable withdrawal permission.**

### Stage 4 — controlled LIVE pilot (not authorized yet)
- Separate account/subaccount with a small amount explicitly chosen by the owner.
- Initially use human confirmation or a tightly limited pilot; expand to fully automatic operation only after evidence from repeated end-to-end tests.
- Enable LIVE only after code review, CI, integration tests, and device-level tests all pass and a deliberate release gate is approved.

## Acceptance criteria before LIVE can be enabled

- [ ] Read-only API test succeeds with a View Only key.
- [ ] Missing/malformed balances fail closed; errors do not misreport a zero balance.
- [ ] Credentials never appear in logs, UI errors, crash reports, or repository history.
- [ ] TAPI V2 API contract is reviewed and integration tests cover signed requests, account response parsing, and exchange error responses.
- [ ] Order idempotency and timeout reconciliation are tested, including process restart.
- [ ] Partial fills, rejected orders, cancellation races, and stale prices are handled.
- [ ] Fees and realized PnL reconcile with Indodax trade history.
- [ ] Position limits, per-order limits, daily loss limits, and emergency stop are enforced in code, not only UI.
- [ ] LIVE cannot share PAPER state or accidentally start the PAPER engine.
- [ ] Device/background/network recovery tests pass.
- [ ] Explicit human release approval recorded.

**Do not remove the LiveBroker lock or enable LIVE while any required criterion is unchecked.**

## References
- Indodax Help Center, API permissions and setup: https://help.indodax.com/hc/id/articles/5315217255833-Bagaimana-Cara-Mengintegrasikan-API-INDODAX
- Official Indodax Trade API 2 documentation: https://github.com/btcid/indodax-official-api-docs/blob/master/INDODAX-TradeAPI-2.md
