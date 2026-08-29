# AI Multi-Agent Trading Bot — Architecture Contract

Status: CANONICAL / IMPLEMENTATION BASELINE — 2026-08-29

This document is the source of truth for the trading system. The repository must implement this contract; code must not silently redefine it.

## 1. Mission

Build an auditable Indodax-focused multi-agent paper-trading system that identifies short-horizon opportunities without turning missing data, unavailable AI, or agent disagreement into unexplained HOLD decisions.

Safety remains mandatory: AI proposes evidence and a candidate; deterministic risk controls decide whether execution is allowed. Live trading is not the default and is not enabled by this document.

## 2. Non-negotiable architecture

```text
INDODAX ADAPTER
    -> ONE UNIFIED MARKET SNAPSHOT
    -> DATA QUALITY GATE
    -> SPECIALIST EVIDENCE
    -> EVIDENCE / SIGNAL BUS
    -> BULL/BEAR CONFLICT REVIEW
    -> ONE TRADER / DECISION SYNTHESIZER
    -> DETERMINISTIC RISK GATE
    -> ONE PAPER EXECUTION LEDGER
    -> PERSISTENCE / OBSERVABILITY
    -> REFLECTION / LEARNING
```

There must be one authoritative path from market data to execution. Alternative implementations may exist only as tests, adapters, or explicitly disabled experiments.

## 3. Responsibility boundaries

### Market-data adapter
Owns exchange I/O and normalization. It is the only component allowed to obtain the authoritative market snapshot for a cycle. Agents must not fetch a second price source.

### Data-quality gate
Determines whether the snapshot is usable. It produces `OK`, `STALE`, or `UNAVAILABLE` plus explicit reasons. Data failure is never represented as normal HOLD.

### Technical / Structure Agent
Owns price structure: OHLCV, candle geometry, support/resistance, trend structure, breakout/rejection, RSI/MACD/MA as supporting evidence. It does not own final action, portfolio risk, or execution.

RSI overbought is not automatically bearish. Momentum direction and structure have priority over oscillator contrarian interpretation for scalping.

### Forecast Agent
Owns probabilistic short-horizon outlook. For scalping, horizons are expressed in market bars/minutes, not days. It may be unavailable when insufficient history exists. Unavailable forecast is not a HOLD vote.

### Sentiment / Context Agent
Owns external/contextual bias. It is advisory only. Missing news/social data is explicitly `UNAVAILABLE` rather than fabricated neutral evidence. It cannot veto technical/momentum evidence.

### Trading Librarian
Owns shared trading knowledge retrieval and context. It informs analysts but never creates an execution order.

### Bull/Bear Conflict Review
Constructs explicit bullish thesis, bearish thesis, contradictions, confirmation requirements, and invalidation conditions. It is a debate/review layer, not another execution engine.

### Trader / Decision Synthesizer
This is the only AI component allowed to convert evidence into a candidate action: `BUY`, `SELL`, `HOLD`, or `NO_EDGE`. It does not perform deterministic risk approval.

### Risk Gate
Pure deterministic control plane. It can approve or reject a candidate. It must never convert BUY into SELL or invent a directional signal. Required checks include mode, symbol, position limit, exposure, balance, daily loss, size, liquidity/spread, and stop/target validity.

### Paper Execution Ledger
There is one authoritative paper-account ledger. No agent, dashboard, or second paper engine may maintain a competing balance/position state.

### Reflector
Evaluates completed decisions and outcomes. It may produce learning/evaluation data but cannot rewrite historical decisions or bypass risk.

## 4. Canonical signal contract

Every specialist output must expose:

- `direction`: `BULLISH | BEARISH | NEUTRAL`;
- `score`: `-1..+1`;
- `confidence`: `0..1`;
- `timeframe`;
- `evidence`;
- `data_timestamp`;
- `data_age_seconds`;
- `status`: `OK | DEGRADED | UNAVAILABLE`.

`HOLD` is an action, not an analyst failure state.

The common contract is implemented in `core/signal_contract.py`.

## 5. Canonical scalping context

A valid scalping snapshot should contain, where source data permits:

- current price;
- bid/ask or spread when available;
- recent trades;
- 1m OHLCV;
- derived 5m, 15m, and 30m movement;
- volume;
- volatility;
- timestamp and age;
- source;
- data-quality status.

When native candles are unavailable, bounded trade buckets may derive candles. A single trade is never a candle.

## 6. Agent conflict policy

Agents do not vote equally and do not repeatedly make final decisions.

Evidence is combined using reliability-aware scoring:

```text
usable evidence
  -> directional strength
  -> confidence-weighted evidence
  -> timeframe alignment
  -> conflict review
  -> trader candidate
```

Missing/degraded evidence is excluded from directional scoring and recorded separately. It must not be treated as a bearish, bullish, or HOLD vote.

Strong conflict reduces confidence and can produce `NO_EDGE`; it does not manufacture an arbitrary opposite direction.

A candidate BUY/SELL with confidence >= 0.75 may enter risk evaluation without unanimous agent agreement, provided minimum independent confirmations and opportunity criteria are satisfied.

## 7. Opportunity-first scalping policy

The system is not required to trade every cycle. It is required to detect valid opportunities when the evidence exists.

Preferred short-horizon evidence:

- 1m momentum;
- 5m momentum;
- 15m alignment;
- 30m regime;
- volume expansion;
- breakout/rejection;
- market structure;
- spread/liquidity.

Suggested initial candidate policy:

```text
BUY/SELL candidate requires:
- valid data;
- at least 2 independent directional confirmations;
- opportunity score >= 0.55;
- candidate confidence >= 0.60;
- no severe conflict;
- valid stop/target geometry.

Risk execution eligibility requires:
- candidate confidence >= 0.75;
- deterministic risk gate PASS.
```

These are strategy controls, not excuses to force trades. They may be calibrated with replay tests.

## 8. Position lifecycle — spot paper scope

```text
NO POSITION + BUY  -> OPEN LONG
OPEN LONG + SELL    -> CLOSE/REDUCE LONG
OPEN LONG + BUY     -> MANAGE / NO NEW DUPLICATE POSITION
NO POSITION + SELL  -> NO ACTION (shorting is not enabled)
```

## 9. Explicit state taxonomy

A cycle must distinguish:

`DATA_UNAVAILABLE`
`DATA_STALE`
`AI_DEGRADED`
`ANALYZED`
`NO_EDGE`
`HOLD_EXISTING_POSITION`
`RISK_REJECTED`
`EXECUTED`

Compatibility `action` may remain `BUY | SELL | HOLD`, but `cycle_status` explains why the action did or did not execute.

## 10. Anti-HOLD diagnostics

Persist and expose:

- consecutive HOLD count;
- consecutive no-edge count;
- missing movement count;
- degraded-AI count;
- repeated-score detection;
- dominant and opposing evidence;
- conflict reason;
- risk rejection reason.

Ten consecutive ordinary HOLD cycles must create a diagnostic event. Ten consecutive cycles caused by missing/stale data must flag the data pipeline, not the strategy.

A repeated HOLD pattern must be classifiable as one of:

`GENUINE_NO_EDGE`, `DATA_PROBLEM`, `AI_DEGRADED`, `CONFLICT`, `RISK_REJECTION`, `POSITION_MANAGEMENT`.

## 11. AI degradation

External AI is optional compute. If unavailable:

1. record `AI_DEGRADED`;
2. continue deterministic market-data-derived technical/momentum analysis;
3. require stronger confirmation;
4. reduce confidence/size according to configuration;
5. never fabricate an AI vote;
6. never turn the degraded state into normal HOLD.

If market data itself is unusable, stop analysis with `DATA_UNAVAILABLE` or `DATA_STALE`.

## 12. Paper trading

Paper mode is the default. Maximum simultaneous paper positions is user-selectable but hard-capped at 3 and must be server-authoritative.

Paper balance, positions, realized/unrealized PnL, fills, and lifecycle state must come from one ledger. Mark-to-market uses the same cycle snapshot used by analysis.

## 13. Execution boundary

No AI agent may call an exchange order endpoint. Every candidate must pass:

`candidate -> deterministic risk gate -> execution adapter -> ledger -> persistence`.

Execution status must distinguish approved, rejected, filled, partially filled, cancelled, and failed.

## 14. Persistence / observability

Each cycle must be reconstructable from stored data. Persist the market snapshot or normalized evidence used by the decision, agent evidence, conflict review, candidate, risk result, execution result, and cycle status.

Never persist raw API secrets, tokens, or private credentials.

## 15. Canonical runtime

`core/orchestrator.py` is the authoritative AI coordination entry point.

`core/scalping_controller.py` is the authoritative short-horizon strategy helper. `core/adaptive_scalping.py` must not become a second decision brain; it may only expose compatibility behavior or delegate to the canonical signal pipeline.

`core/risk_engine.py` and `core/execution_gate.py` are mandatory before execution.

`core/live_paper_cycle.py` must use the same orchestrator, risk gate, and paper ledger as other application entry points.

The Cloudflare worker is an API/runtime adapter, not a separate trading brain.

## 16. Testing contract

Tests must prove both safety and liveness:

- deterministic unit tests for indicators, signal normalization, risk, sizing, and lifecycle;
- integration tests for data -> agents -> trader -> risk -> execution;
- replay fixtures for bullish trend, bearish trend, breakout, reversal, range, high volatility, and degraded data;
- explicit tests proving a valid directional opportunity can reach the risk gate;
- explicit tests proving missing data is not HOLD;
- explicit tests proving degraded AI is not HOLD;
- 10+ consecutive HOLD anomaly detection;
- cycle idempotency and no double-counting.

A test that directly calls a low-level scalping engine is not sufficient evidence that the production AI pipeline works.

## 17. Change-control rules

Before changing trading behavior, answer:

1. Which boundary owns it?
2. Is another component already doing this?
3. Does it create another BUY/SELL/HOLD generator?
4. Does it introduce another market-data source?
5. Can it bypass risk?
6. Can failure become indistinguishable from HOLD?
7. Does it require a schema/test update?

If any answer is unclear, stop and resolve the architecture first.

## 18. Definition of done

A trading feature is complete only when:

- it belongs to one boundary;
- it uses the canonical signal contract;
- it has explicit failure states;
- it cannot bypass risk;
- it does not duplicate an existing decision engine;
- it is observable;
- replay tests cover both directional opportunities and neutral markets;
- paper accounting remains coherent;
- the result is reproducible from persisted state.

## 19. Source-of-truth hierarchy

1. Explicit project-owner requirements.
2. This `ARCHITECTURE.md`.
3. Core/domain contracts.
4. Orchestrator/application services.
5. Specialist agents.
6. Adapters/UI/infrastructure.
7. Temporary experiments.

## 20. Final rule

Do not add a new brain when an existing brain can own the responsibility. Do not make missing information look like HOLD. Do not allow an analyst to become an execution controller. Prefer one clear pipeline, explicit evidence, explicit conflict, deterministic risk, and one paper ledger.
