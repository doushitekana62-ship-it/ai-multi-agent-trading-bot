# Trial v0.2 — Realistic Paper Trading Foundation

Status: ACTIVE IMPLEMENTATION BASELINE — 2026-09-01

## Purpose

Trial v0.2 treats PAPER trading as the realistic training environment for the eventual REAL trading system. The objective is not maximum paper profit. Priority is capital preservation, correct trading behavior, decision quality, realistic execution/accounting, and useful learning data.

The same core market-observation, evidence, decision, risk, position-lifecycle and accounting semantics should be reusable when the execution/account adapter is later changed from paper to real.

## v0.2 foundations

- Explicit agent runtime health: `OFF`, `ARMED`, `ON`, `DEGRADED`, `BROKE`, `RECOVERING`.
- `ARMED` means configured/enabled; it does not mean healthy or recently executed.
- Specialist evidence exposes status/freshness instead of silently becoming a HOLD vote.
- Dashboard decision API exposes `cycle_status`, `hold_reason`, `execution_reason`, conflict review and signal evidence where available.
- Paper history is forensic: 1m/5m/15m/30m movement, pulse status/segments, agent votes/details, confidence components, execution gate, account/PnL snapshot, market snapshot, reasoning and persistence identifiers.
- Supabase remains the persistence source for the Paper History Library; runtime/browser history is not substituted into it.
- Market Pulse remains an observation layer, not a second trading brain.
- Existing INDODAX market-data path and Trial v0.1 behavior are protected from regression.

## Existing realistic execution foundations

The repository already contains paper execution controls for fee and slippage and a single paper-account model. Trial v0.2 must extend these foundations rather than create a competing paper engine.

Future realistic execution work may add, where justified by available data:

- bid/ask spread;
- latency-aware execution timestamps;
- partial fills;
- rejected/cancelled orders;
- timeout and unknown execution state;
- order-intent/idempotency semantics;
- paper-versus-real execution parity tests.

## Learning / validation layer

The two-to-three-month training period is an empirical runtime experiment, not a coding task. The system should record decision -> market state -> evidence -> action -> subsequent outcome so that decision quality can be measured independently from closed-trade PnL.

Required future measurements include:

- HOLD quality;
- false positives and missed opportunities;
- confidence calibration;
- 1m/5m/15m/30m forward outcomes;
- MFE/MAE;
- regime-specific decision quality;
- forecast error and systematic bias.

## Thesis / Trading Librarian

Thesis is separate from actual paper-trade outcome. The Trading Librarian is an advisory/judicial validation layer only. It may retrieve trading knowledge, compare bullish/bearish theses, identify contradictions and validate evidence, but it cannot issue BUY/SELL/HOLD or bypass the Trader/Decision Synthesizer and Risk Gate.

Thesis review is periodic/configurable rather than every cycle. Weekly is an initial default; the operator may choose another period.

## Forecast

Forecast must be falsifiable. Every forecast should have reference timestamp/price, horizon, target variable, predicted value or return, uncertainty/range, confidence, and later actual/error. A forecast is not considered useful merely because it is visually close to price.

## Non-regression rule

Trial v0.1 remains the baseline. The following must continue to work:

- real INDODAX public market data;
- unified market observation;
- intraminute movement;
- Market Pulse GREEN/RED/GRAY behavior;
- paper persistence;
- valid HOLD behavior;
- deterministic risk gate;
- one authoritative paper ledger;
- CI/build/Cloudflare bundle validation.

No Cloudflare deployment is required for this scope checkpoint.

## Definition of done for v0.2 foundation

A change is complete only when its source contract, failure states, persistence behavior, dashboard representation, tests and CI validation agree. A green CI run alone is not sufficient evidence of runtime health.
