# AI Multi-Agent Trading Bot — Architecture Contract

Status: CANONICAL / IMPLEMENTATION BASELINE — 2026-09-01

This document is the source of truth for the trading system. The repository must implement this contract; code must not silently redefine it.

## 1. Mission

Build an auditable Indodax-focused multi-agent trading system whose PAPER environment is a realistic digital twin of the future REAL execution environment. The system identifies short-horizon opportunities without turning missing data, unavailable AI, agent disagreement, or execution uncertainty into unexplained HOLD decisions.

Paper trading is not a simplified demo. It is the primary 2–3 month training and validation environment. The eventual real-trading path must reuse the same market observation, evidence, decision, risk, position-lifecycle, accounting, and execution-contract boundaries wherever possible. Only the execution/account adapter changes between paper and real.

The training objective prioritizes capital preservation, decision quality, realistic execution behavior, and learning correct trading behavior over maximizing paper profit. Small profit is acceptable; large avoidable loss is not.

Safety remains mandatory: AI proposes evidence and a candidate; deterministic risk controls decide whether execution is allowed. Live trading is not enabled by this document.

## 2. Non-negotiable architecture

```text
INDODAX ADAPTER
    -> ONE UNIFIED MARKET SNAPSHOT
    -> DATA QUALITY GATE
    -> MARKET OBSERVATION / REGIME
    -> SPECIALIST EVIDENCE
    -> EVIDENCE / SIGNAL BUS
    -> BULL/BEAR CONFLICT REVIEW
    -> PERIODIC THESIS REVIEW / TRADING LIBRARIAN
    -> ONE TRADER / DECISION SYNTHESIZER
    -> DETERMINISTIC RISK GATE
    -> EXECUTION ADAPTER
         -> PAPER EXECUTION / REAL EXCHANGE EXECUTION
    -> ONE AUTHORITATIVE LEDGER / ACCOUNT STATE
    -> PERSISTENCE / OBSERVABILITY
    -> REFLECTION / DECISION-QUALITY LEARNING
```

There must be one authoritative path from market data to candidate decision and one authoritative account/position state. Alternative implementations may exist only as tests, adapters, or explicitly disabled experiments.

Paper and real trading must share the same core decision/risk/position lifecycle semantics. The execution adapter is the boundary where paper simulation and real exchange behavior diverge.

## 3. Responsibility boundaries

### Market-data adapter
Owns exchange I/O and normalization. It is the only component allowed to obtain the authoritative market snapshot for a cycle. Agents must not fetch a second price source.

### Data-quality gate
Determines whether the snapshot is usable. It produces `OK`, `STALE`, or `UNAVAILABLE` plus explicit reasons. Data failure is never represented as normal HOLD.

### Market observation / regime layer
Owns short-horizon observation state, intraminute movement, data freshness, observation quality, and market-regime classification. Market Pulse is an observation/evidence surface, not a trading brain.

Where source data permits, the observation layer tracks current price, bid/ask, trades, 1m OHLCV, 5m/15m/30m movement, volume, volatility, timestamp, source, and quality. A five-second observation cadence may feed a separate sixty-second decision cadence. Intraminute movement must not disappear merely because open equals close.

### Technical / Structure Agent
Owns price structure: OHLCV, candle geometry, support/resistance, trend structure, breakout/rejection, RSI/MACD/MA as supporting evidence. It does not own final action, portfolio risk, or execution.

RSI overbought is not automatically bearish. Momentum direction and structure have priority over oscillator contrarian interpretation for scalping.

### Forecast Agent
Owns probabilistic short-horizon outlook. For scalping, horizons are expressed in market bars/minutes, not days. It may be unavailable when insufficient history exists. Unavailable forecast is not a HOLD vote.

Forecast output must be falsifiable and auditable: forecast timestamp, reference price, horizon, target variable, predicted value/return, uncertainty/range, confidence, method/context, later actual value, and forecast error. Forecast quality is evaluated statistically; it is never forced toward the current price simply to look accurate.

### Sentiment / Context Agent
Owns external/contextual bias. It is advisory only. Missing news/social data is explicitly `UNAVAILABLE` rather than fabricated neutral evidence. It cannot veto technical/momentum evidence.

### Trading Librarian
Owns shared trading knowledge retrieval and context. It informs analysts and, when explicitly invoked for thesis review, acts as a judicial/validation layer. It never creates an execution order and never has BUY/SELL/HOLD authority.

The Librarian may use technical analysis, market structure, trend/range, momentum, mean reversion, support/resistance, volatility, volume/context, candle interpretation, forecasting principles, risk/reward logic, and behavioral-finance knowledge. Behavioral concepts such as confirmation bias, loss aversion, anchoring, recency bias, FOMO, panic selling, revenge trading, disposition effect, and herding are hypotheses/context unless supported by observable evidence.

### Bull/Bear Conflict Review
Constructs explicit bullish thesis, bearish thesis, contradictions, confirmation requirements, and invalidation conditions. It is a debate/review layer, not another execution engine.

### Thesis Review
Thesis is separate from paper/real trade outcome. A thesis records what the agents believe, why, confidence, supporting evidence, opposing evidence, invalidation conditions, age, and state. It follows a lifecycle such as `CREATED -> VALID -> WEAKENING -> INVALIDATED -> CLOSED`.

Thesis review is periodic/configurable rather than every market cycle. Initial default may be weekly, but the operator may select the period. A thesis review can return `BULLISH_SUPPORTED`, `BEARISH_SUPPORTED`, or `INCONCLUSIVE`; it must not manufacture a winner when evidence is insufficient.

### Trader / Decision Synthesizer
This is the only AI component allowed to convert evidence into a candidate action: `BUY`, `SELL`, `HOLD`, or `NO_EDGE`. It does not perform deterministic risk approval.

### Risk Gate
Pure deterministic control plane. It can approve or reject a candidate. It must never convert BUY into SELL or invent a directional signal. Required checks include mode, symbol, position limit, exposure, balance, daily loss, size, liquidity/spread, and stop/target validity.

For real trading, additional controls must include exchange-account reconciliation, idempotent order handling, unknown-order-state handling, kill switch, decision freeze, maximum exposure, daily/weekly loss limits, and server-authoritative live-mode configuration.

### Execution Adapter
Separates paper execution from real exchange execution while preserving the same candidate, risk, order-intent, lifecycle, and accounting semantics.

Paper execution must model relevant real-world conditions where source data permits: bid/ask spread, fees, slippage, latency, partial fills, rejected orders, cancelled orders, timeout, and unknown execution state. Paper must not provide perfect fills that would teach behavior unavailable in real trading.

Real execution must reconcile order intent, exchange order ID/status, fills, and account state. An unknown exchange order state must never be treated as a clean failure because the exchange may have executed the order.

### Paper / Real Account Ledger
There is one authoritative account-state model per environment. No agent, dashboard, or second paper engine may maintain a competing balance/position state.

Paper balance, positions, realized/unrealized PnL, fills, fees, and lifecycle state come from one ledger. In real trading, the exchange account is the external financial source of truth; the internal ledger mirrors and reconciles it. Supabase is persistence/audit, not proof that real assets exist.

Mark-to-market uses the same market snapshot used by analysis.

### Reflector / Decision Quality
Evaluates completed decisions and outcomes. It may produce learning/evaluation data but cannot rewrite historical decisions or bypass risk.

Decision quality must be measurable even before a trade closes, using defined forward horizons such as 1m/5m/15m/30m where appropriate, plus favorable/adverse excursion, confidence calibration, false positives, missed opportunities, HOLD quality, and regime-specific performance.

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

## 6. Agent health and operational status

The dashboard must expose actual agent health rather than configuration-only state. Minimum states are:

`OFF`
`ARMED`
`STARTING`
`ON`
`DEGRADED`
`BROKE`
`RECOVERING`

`ARMED` means configured/enabled; it does not prove that the agent is currently available or executing.

Each agent health record should expose, where available:

- current state;
- last successful analysis;
- last failure;
- last heartbeat;
- data freshness;
- latency;
- error count;
- fallback mode;
- reason for degraded/broken state.

The dashboard must distinguish `ARMED`, `AVAILABLE`, `RUNNING`, and `HEALTHY` rather than collapsing them into one badge.

## 7. Agent conflict policy

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

Conflict Analyzer should support a forensic mode showing each agent's direction, confidence, evidence/reason, data status, opposing evidence, conflict strength, and final synthesis.

## 8. Opportunity-first scalping policy

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

## 9. Position lifecycle — spot paper and real scope

```text
NO POSITION + BUY  -> OPEN LONG
OPEN LONG + SELL    -> CLOSE/REDUCE LONG
OPEN LONG + BUY     -> MANAGE / NO NEW DUPLICATE POSITION
NO POSITION + SELL  -> NO ACTION (shorting is not enabled)
```

Paper and real environments must use the same lifecycle semantics.

## 10. Explicit state taxonomy

A cycle must distinguish:

`DATA_UNAVAILABLE`
`DATA_STALE`
`AI_DEGRADED`
`ANALYZED`
`NO_EDGE`
`HOLD_EXISTING_POSITION`
`RISK_REJECTED`
`EXECUTED`
`EXECUTION_UNKNOWN`
`ACCOUNT_MISMATCH`
`TRADING_HALTED`
`DECISION_FROZEN`

Compatibility `action` may remain `BUY | SELL | HOLD`, but `cycle_status` explains why the action did or did not execute.

HOLD reason codes should distinguish at least:

`NO_NEW_EDGE`
`EXISTING_THESIS_RETAINED`
`RETRACEMENT_NOT_INVALIDATION`
`LOW_CONFIDENCE`
`AGENT_CONFLICT`
`RISK_REJECTED`
`AI_DEGRADED`
`MARKET_FLAT`
`POSITION_MANAGEMENT`

## 11. Anti-HOLD diagnostics

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

## 12. AI degradation

External AI is optional compute. If unavailable:

1. record `AI_DEGRADED`;
2. continue deterministic market-data-derived technical/momentum analysis;
3. require stronger confirmation;
4. reduce confidence/size according to configuration;
5. never fabricate an AI vote;
6. never turn the degraded state into normal HOLD.

If market data itself is unusable, stop analysis with `DATA_UNAVAILABLE` or `DATA_STALE`.

For real-money execution, policy may be stricter: AI degradation may permit observation and position-risk monitoring but must not automatically authorize new exposure.

## 13. Realistic paper trading contract

Paper trading is the training environment and must approximate real execution rather than idealized execution.

Paper must model, where data permits:

- actual market price;
- bid/ask spread;
- fees;
- slippage;
- execution latency;
- partial fills;
- rejected/cancelled orders;
- timeout/unknown order state;
- position lifecycle;
- realized and unrealized PnL;
- mark-to-market;
- account balance/equity;
- maximum exposure and loss limits.

The same decision candidate and risk result should feed either the paper adapter or the eventual real exchange adapter. The bot's core reasoning must not know whether capital is virtual or real.

Training objective:

`capital preservation > decision quality > realistic behavior > paper profit maximization`.

A paper strategy that earns money only because it receives perfect fills, ignores fees, or avoids execution failures is not considered validated.

## 14. PnL and accounting contract

The account model must distinguish:

- cash/balance;
- position quantity;
- entry price;
- current mark price;
- position market value;
- realized PnL;
- unrealized PnL;
- total PnL;
- fees;
- equity.

At minimum, accounting must remain internally reconcilable. The mark price must use the same cycle snapshot used by analysis.

Real trading must treat the exchange account as external financial truth and reconcile it against internal state. Any mismatch must be explicit and may freeze new trading until resolved.

## 15. Execution boundary and real-trading safety

No AI agent may call an exchange order endpoint. Every candidate must pass:

`candidate -> deterministic risk gate -> execution adapter -> ledger -> persistence`.

Execution status must distinguish approved, rejected, filled, partially filled, cancelled, failed, and unknown.

Real trading requires:

- idempotent order intent;
- exchange order ID tracking;
- fill reconciliation;
- unknown-order-state handling;
- account reconciliation;
- kill switch;
- decision freeze;
- maximum exposure;
- daily/weekly loss limits;
- server-authoritative live-mode controls.

If order state or account state is unknown, the system must not assume the safest-looking state; it must reconcile before opening additional exposure.

## 16. Persistence / observability

Each cycle must be reconstructable from stored data. Persist the market snapshot or normalized evidence used by the decision, agent evidence, conflict review, thesis state when invoked, candidate, risk result, execution result, account state, and cycle status.

Never persist raw API secrets, tokens, or private credentials.

Supabase is the persistence/audit layer. It must not become a competing decision engine or competing account ledger.

Market observations should expose evidence quality, including observation count, source, trade/ticker fallback, missing observations, freshness, movement, and quality state.

## 17. Trading Journal / history presentation

Paper History is an operational audit surface, not merely a raw log.

The dashboard should eventually present readable action, reason, market context, confidence, position state, PnL impact, persistence state, and severity.

Severity colors represent evidence/urgency, not automatically BUY/SELL:

`GRAY` = neutral/no meaningful change
`GREEN` = favorable/confirmed
`YELLOW/AMBER` = watch/warning
`ORANGE` = material deterioration/attention
`RED` = serious/critical concern

The system may use operator-readable concepts such as `concern`, `urgency`, `confidence`, and `thesis weakening`. These are telemetry semantics, not claims that the AI has literal human emotions.

## 18. Thesis and Trading Librarian

Thesis is separate from actual trade outcome.

A thesis contains:

- thesis direction;
- supporting evidence;
- opposing evidence;
- assumptions;
- confidence;
- market regime;
- creation time;
- age;
- invalidation conditions;
- current thesis state;
- later reality/outcome reference.

The Trading Librarian is invoked for thesis review rather than every cycle. It can compare competing agent arguments, validate or challenge assumptions, rank evidence, identify historical analogues, and return uncertainty/inconclusive verdicts.

It has no execution authority and cannot create BUY/SELL/HOLD orders.

The thesis review period is configurable by the operator; weekly is the initial default proposal.

## 19. Forecast audit and calibration

A forecast must always specify:

- reference/current price;
- horizon;
- target variable;
- predicted value or expected return;
- confidence;
- uncertainty/range where available;
- data timestamp;
- methodology/context.

Later, the system records the actual value at the forecast horizon and computes forecast error and directional accuracy.

Forecast evaluation must detect systematic bias, including persistent bullish or bearish drift. A forecast is not improved by cosmetically moving it toward the current price.

The Trading Library may inform forecasting methodology and evaluation, but it must not become a forecast execution controller.

## 20. Decision-quality learning

Performance evaluation must not depend only on closed trades.

The system should evaluate decisions using:

- BUY/SELL/HOLD distribution;
- signal follow-through;
- outcomes after defined forward horizons;
- favorable/adverse excursion;
- confidence calibration;
- false positives;
- missed opportunities;
- HOLD quality;
- risk-gate rejection quality;
- market-regime-specific performance;
- forecast error.

The objective of the 2–3 month paper period is to learn whether the system behaves correctly and preserves capital under realistic conditions, not merely whether the account balance increases.

## 21. Canonical runtime

`core/orchestrator.py` is the authoritative AI coordination entry point.

`core/scalping_controller.py` is the authoritative short-horizon strategy helper. `core/adaptive_scalping.py` must not become a second decision brain; it may only expose compatibility behavior or delegate to the canonical signal pipeline.

`core/risk_engine.py` and `core/execution_gate.py` are mandatory before execution.

`core/live_paper_cycle.py` must use the same orchestrator, risk gate, and paper ledger as other application entry points.

The Cloudflare worker is an API/runtime adapter, not a separate trading brain.

## 22. Testing contract

Tests must prove both safety and liveness:

- deterministic unit tests for indicators, signal normalization, risk, sizing, lifecycle, accounting, and realistic execution simulation;
- integration tests for data -> agents -> trader -> risk -> execution;
- replay fixtures for bullish trend, bearish trend, breakout, reversal, range, high volatility, degraded data, spread/slippage, partial fill, timeout, and account mismatch;
- explicit tests proving a valid directional opportunity can reach the risk gate;
- explicit tests proving missing data is not HOLD;
- explicit tests proving degraded AI is not HOLD;
- 10+ consecutive HOLD anomaly detection;
- cycle idempotency and no double-counting;
- paper-vs-real execution contract compatibility;
- forecast horizon/outcome evaluation;
- PnL/accounting reconciliation;
- order unknown-state recovery;
- exchange account mismatch halts new exposure.

A test that directly calls a low-level scalping engine is not sufficient evidence that the production AI pipeline works.

## 23. GitHub / CI and deployment contract

CI is part of the trading safety system.

A change is not complete until the relevant compile, unit, integration, contract, frontend, Worker, and runtime validation layers pass.

CI failures must be classified as source failure, dependency failure, workflow/runner failure, or infrastructure failure before changing code. A failed workflow with no executed steps must not be treated as proof of a code defect.

Cloudflare deployment is permitted only after CI validation. Deployment success is not equivalent to runtime health; post-deploy smoke checks must verify market observation, decision cycle, persistence, and configuration health.

Supabase schema migrations/contract checks must be compatible with the deployed application payload before deployment.

## 24. Change-control rules

Before changing trading behavior, answer:

1. Which boundary owns it?
2. Is another component already doing this?
3. Does it create another BUY/SELL/HOLD generator?
4. Does it introduce another market-data source?
5. Can it bypass risk?
6. Can failure become indistinguishable from HOLD?
7. Does it change paper-vs-real behavioral parity?
8. Does it require a schema/test update?
9. Can it make historical outcomes unreproducible?

If any answer is unclear, stop and resolve the architecture first.

## 25. Definition of done

A trading feature is complete only when:

- it belongs to one boundary;
- it uses the canonical signal contract;
- it has explicit failure states;
- it cannot bypass risk;
- it does not duplicate an existing decision engine;
- it is observable;
- replay tests cover both directional opportunities and neutral markets;
- paper accounting remains coherent;
- paper execution includes relevant real-world frictions;
- paper and real execution contracts remain compatible;
- the result is reproducible from persisted state;
- CI and deployment validation pass.

## 26. Source-of-truth hierarchy

1. Explicit project-owner requirements.
2. This `ARCHITECTURE.md`.
3. Core/domain contracts.
4. Orchestrator/application services.
5. Specialist agents.
6. Adapters/UI/infrastructure.
7. Temporary experiments.

## 27. Final rules

Do not add a new brain when an existing brain can own the responsibility.

Do not make missing information look like HOLD.

Do not allow an analyst or Librarian to become an execution controller.

Do not allow paper trading to become an idealized simulator that teaches behavior unavailable in real trading.

Do not allow real execution uncertainty to be represented as a clean failure.

Prefer one clear pipeline, explicit evidence, explicit conflict, deterministic risk, realistic paper execution, one authoritative account model, auditable persistence, and measurable decision quality.

The ultimate design objective is:

`REAL MARKET DATA -> REALISTIC PAPER ENVIRONMENT -> 2–3 MONTH BEHAVIORAL/DECISION TRAINING -> VALIDATION -> SAME CORE SYSTEM -> REAL EXECUTION`

Paper mode is the foundation for real trading, not a separate toy system.
