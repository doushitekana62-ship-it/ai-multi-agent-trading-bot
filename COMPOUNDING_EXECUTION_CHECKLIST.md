# Compounding Scalping Execution Checklist

This checklist is subordinate to `ARCHITECTURE.md`. A task is complete only when code, persistence, and tests agree.

## Gate 1 — Market data
- [x] Indodax public market data is the declared source.
- [x] Market observations are persisted through the canonical Supabase RPC.
- [x] Minute idempotency is enforced by `(symbol, minute_bucket)`.
- [x] Intraminute price changes remain directional; a reversal cannot silently become GRAY.
- [ ] Dashboard Market Pulse must consume the persisted observation surface as its authoritative history.

## Gate 2 — Agent pipeline
- [x] Technical, Forecast, Sentiment, Librarian, Decision and Reflection responsibilities are represented in the architecture.
- [x] AI degradation is explicit and never masquerades as a normal HOLD.
- [x] The Cloudflare adapter preserves net edge, expected move, friction, confidence, position size and exit-plan data.
- [ ] Verify the external FastAPI response contains every agent output required by the Cloudflare ledger contract.
- [ ] Verify the Reflection Agent is executed after every completed trade and its result is persisted.

## Gate 3 — Risk
- [x] Risk is deterministic and downstream from AI.
- [x] Entry is rejected when confidence, net edge, exposure, balance or position limits fail.
- [x] Dynamic stop, take-profit, trailing and break-even protection are available.
- [x] Time exit is bounded by runtime observation timestamps rather than stale fixture timestamps.
- [ ] Add explicit risk-gate tests for every rejection reason.

## Gate 4 — Execution lifecycle
- [x] BUY creates an authoritative Durable Object position.
- [x] SELL closes only an existing position.
- [x] Fees and slippage are included in paper execution.
- [x] A successful execution is represented as an explicit trade object.
- [x] Execution status is persisted with the decision.
- [x] Trade persistence failure creates a visible integrity event instead of being swallowed.
- [ ] Verify partial/duplicate execution reconciliation against production schema.

## Gate 5 — Supabase ledger
- [x] `decisions.trade_id` and `trades.exit_decision_id` exist in production.
- [x] The execution-ledger reconciliation migration exists under the authoritative migration history.
- [x] Paper history carries decision/trade linkage and execution metadata.
- [ ] Run a production paper cycle and verify decision -> trade -> paper_history IDs are identical where applicable.
- [ ] Verify zero orphan trades, orphan decisions and mismatched closed positions after a full paper session.

## Gate 6 — Compounding
- [x] Position allocation is a percentage of current equity rather than a fixed nominal amount.
- [ ] Demonstrate at least three consecutive closed paper trades where the next allocation is calculated from the updated equity.
- [ ] Demonstrate automatic entry and automatic exit without a manual action.
- [ ] Demonstrate the loop continuing after a profitable close.

## Gate 7 — Runtime proof
- [x] Durable Object alarm runs market observation every 5 seconds.
- [x] Decision cycles run every 15 seconds.
- [x] Cloudflare has no duplicate cron scheduler.
- [ ] Capture a real runtime session with non-zero observations, at least one BUY, one SELL, a closed trade and non-zero PnL.
- [ ] Reconcile that session against Supabase and the dashboard.

## Completion rule
The bot is not considered 100% paper-certified until Gates 1–7 have no unchecked runtime items. Passing unit tests alone is insufficient; the final proof must show a real paper session whose market observations, agent decision, risk gate, execution, trade ledger, PnL and compounded next position size reconcile end-to-end.
