# Architecture Amendment — 2026-08-29 — Research-Informed AI Trading Architecture

Status: APPROVED FOR IMPLEMENTATION.

This amendment extends `ARCHITECTURE.md`. It is based on a review of open-source multi-agent trading systems and is specifically intended to correct the current failure mode where the paper engine records repeated HOLD decisions without usable short-horizon market movement data.

## 1. Research references reviewed

The implementation patterns reviewed were:

- Tauric Research `TradingAgents`: specialized analyst team -> bull/bear research debate -> trader -> risk management -> portfolio manager. The project also emphasizes verified market-data grounding, structured decision output, persistent decision logs, and checkpoint/resume behavior.
- `VerumTrade`: evidence-first pipeline -> evidence graph -> bull/bear debate -> trader plan -> risk review -> structured decision guard -> paper/live execution. It explicitly separates evidence from the final decision and exposes decision traces.
- `crypto-trading-arena`: one exchange connector owns the live market stream and fans the same market updates out to every agent and the tools/dashboard. Agents react to current ticker/candle updates instead of independently fetching divergent market state.
- `ATLAS`: Commander orchestration, Guardian hard-rule risk validation, Trader execution, Sage learning from outcomes, and Architect strategy generation/backtesting. Paper mode is the default.
- `LLM-Auto-Trader`: LLM proposes the trade while a deterministic risk layer constrains execution.

These references are behavioral and architectural references only. Their code is not copied into this project.

## 2. Core lesson for this project

The project must not interpret `HOLD` as the universal safe fallback for every failure, missing-data condition, weak-data condition, and genuinely neutral market condition.

These states are different and must be represented differently:

```text
DATA_UNAVAILABLE
DATA_STALE
AI_DEGRADED
NO_DIRECTIONAL_EDGE
HOLD_EXISTING_POSITION
BUY_CANDIDATE
SELL_CANDIDATE
RISK_REJECTED
EXECUTED
```

A failed AI engine must never masquerade as a normal HOLD.

A missing 1-minute movement must never masquerade as a flat market.

A genuine flat market may legitimately produce HOLD.

## 3. New canonical trading pipeline

The canonical runtime flow becomes:

```text
INDODAX exchange connector
        |
        v
Unified Market Stream / Snapshot
        |
        +--> current price
        +--> bid / ask when available
        +--> recent trades
        +--> 1m OHLCV
        +--> 5m / 15m / 30m derived movement
        +--> volume
        +--> volatility
        +--> market structure
        |
        v
Data Quality Gate
        |
        +--> fresh?
        +--> complete enough?
        +--> source consistent?
        +--> timestamp valid?
        |
        +---- FAIL --> DATA_UNAVAILABLE / DATA_STALE
        |
        v
Specialist Analyst Layer
        |
        +--> Technical / Structure
        +--> Momentum / Scalping
        +--> Forecast
        +--> Sentiment / Context
        +--> Mimic Trader
        |
        v
Evidence / Signal Bus
        |
        +--> normalized directional scores [-1, +1]
        +--> confidence
        +--> evidence
        +--> freshness
        +--> timeframe
        |
        v
Bull / Bear Conflict Review
        |
        +--> bullish thesis
        +--> bearish thesis
        +--> contradictions
        +--> missing confirmation
        |
        v
Trader / Decision Synthesizer
        |
        +--> BUY candidate
        +--> SELL candidate
        +--> HOLD candidate
        +--> NO-EDGE
        |
        v
Deterministic Risk / Execution Gate
        |
        +--> size
        +--> max positions
        +--> exposure
        +--> loss limits
        +--> liquidity / spread
        +--> stop / target validity
        +--> paper/live mode
        |
        +---- reject --> RISK_REJECTED
        |
        v
Paper Execution
        |
        v
Supabase Decision + Trade + History
        |
        v
Outcome / Reflection / Learning
```

## 4. One market-data owner

The exchange connector owns the authoritative Indodax market-data connection.

All of the following must derive from the same snapshot/stream:

- Market Pulse;
- Technical Agent;
- Forecast Agent;
- Scalping Engine;
- Decision Agent;
- Paper execution mark price;
- Supabase market snapshot;
- dashboard price display.

Agents must not independently fetch a second price source for the same cycle.

The current Market Pulse visual implementation remains unchanged by this amendment. This amendment changes its data contract, not its visual design.

## 5. Short-horizon market data is mandatory for scalping

For a scalping cycle, a valid market context must contain, where the exchange/source permits:

- current price;
- recent trades or equivalent tick stream;
- 1-minute OHLCV;
- 1-minute price movement;
- 5-minute movement;
- 15-minute movement;
- 30-minute movement;
- volume;
- volatility;
- timestamp and age;
- data source.

If these fields cannot be produced, the cycle must be marked `DATA_UNAVAILABLE` or `DATA_STALE`, not `HOLD`.

## 6. Derived OHLCV contract

When Indodax public trades are the available short-horizon source:

```text
public trades
    -> bounded time buckets
    -> 1m OHLCV
    -> 5m/15m/30m aggregates
    -> movement + structure
    -> agent context
```

The system must preserve whether a candle is exchange-native or locally derived.

A single trade must never be presented as a complete candle.

## 7. Agents must express directional evidence

Every specialist agent must return a structured result with:

- `direction`: BULLISH / BEARISH / NEUTRAL;
- `score`: -1 to +1;
- `confidence`: 0 to 1;
- `timeframe`;
- `evidence`;
- `data_timestamp`;
- `data_age_seconds`;
- `status`: OK / DEGRADED / UNAVAILABLE.

`HOLD` is a portfolio/action decision, not a substitute for an analyst's inability to calculate a signal.

For example:

```text
Technical Agent:
  direction = BEARISH
  score = -0.42
  confidence = 0.71

Forecast Agent:
  direction = BEARISH
  score = -0.31
  confidence = 0.63

Sentiment Agent:
  direction = NEUTRAL
  score = +0.02
  confidence = 0.48
```

This allows the trader layer to distinguish neutral evidence from broken evidence.

## 8. Bull/Bear review replaces blind majority voting

The current simple weighted vote is not sufficient as the final reasoning layer.

The project will adapt the research/debate behavior used by TradingAgents and VerumTrade without copying their implementation.

The review stage must explicitly construct:

```text
BULL CASE
- strongest bullish evidence
- confirmation still required
- invalidation condition

BEAR CASE
- strongest bearish evidence
- confirmation still required
- invalidation condition

CONFLICT
- which signals disagree
- which timeframe disagrees
- whether the disagreement is material
```

A single agent should not be able to force a trade.

A five-agent unanimous HOLD caused by a degraded fallback path must not be treated as genuine consensus.

## 9. Opportunity-first scalping behavior

The scalping engine must evaluate opportunity, not merely reject everything below a generic confidence threshold.

The engine should classify the market into:

- TREND_UP;
- TREND_DOWN;
- RANGE;
- BREAKOUT_UP;
- BREAKOUT_DOWN;
- HIGH_VOLATILITY;
- LOW_LIQUIDITY;
- DATA_UNAVAILABLE.

Candidate generation should use short-horizon evidence such as:

- 1m momentum;
- 5m momentum;
- 15m alignment;
- 30m regime;
- volume expansion;
- breakout/rejection;
- spread/liquidity where available;
- technical structure.

A BUY/SELL candidate is generated only when the opportunity score passes the configured strategy threshold and required confirmations exist.

There is no requirement to create a trade every cycle.

There is, however, a requirement that a valid directional opportunity must not be silently converted to HOLD merely because an optional AI service is unavailable.

## 10. AI engine degradation policy

The external AI engine is optional compute infrastructure, not the only source of trading intelligence.

If the external AI engine is unavailable:

1. record `AI_DEGRADED`;
2. continue using deterministic market-data-derived technical/momentum analysis;
3. reduce confidence and position size as configured;
4. require stronger market confirmation;
5. never fabricate an AI vote;
6. never label the degraded state as normal HOLD.

If deterministic market data is also unavailable, stop the trading decision and record `DATA_UNAVAILABLE`.

This prevents the exact failure observed in the 54-cycle paper trial.

## 11. Risk gate remains hard

Research-inspired behavior must never weaken the existing risk boundary.

The flow remains:

```text
candidate
  -> risk validation
  -> position sizing
  -> execution
```

The AI/strategy layer can propose BUY/SELL, but it cannot bypass:

- maximum position size;
- maximum open positions;
- daily loss limit;
- sufficient balance;
- liquidity constraints;
- stop-loss validity;
- paper/live mode;
- exchange constraints.

## 12. Position lifecycle behavior

The system must distinguish:

```text
NO POSITION + BUY candidate -> OPEN LONG
OPEN LONG + SELL candidate -> CLOSE / REDUCE
OPEN LONG + BUY candidate -> HOLD / MANAGE
NO POSITION + SELL candidate -> NO ACTION unless shorting is explicitly supported
```

For the current spot-paper scope, SELL without an owned position must not create a synthetic short.

## 13. Learning / reflection loop

After a completed trade, the system records:

- entry evidence;
- entry decision;
- risk decision;
- exit evidence;
- realized PnL;
- maximum favorable excursion where available;
- maximum adverse excursion where available;
- which agents agreed/disagreed;
- whether the prediction was directionally correct;
- whether the market regime classification was correct.

Reflection is for learning and evaluation. It must not rewrite historical decisions.

## 14. Supabase audit contract

Every cycle must make the following distinction visible:

```text
cycle_status
  DATA_UNAVAILABLE
  DATA_STALE
  AI_DEGRADED
  ANALYZED
  RISK_REJECTED
  EXECUTED
```

`action` remains one of BUY / SELL / HOLD for compatibility, but the status explains why an action did not execute.

The database record must contain the actual market snapshot used by the cycle. The dashboard must be able to reconstruct the decision without asking an external AI service again.

## 15. Anti-HOLD diagnostic

The system must trigger an observability warning when:

- 10 consecutive cycles are HOLD;
- 10 consecutive cycles have no directional agent votes;
- movement fields are missing for consecutive cycles;
- all agents report the same HOLD while `AI_DEGRADED` is active;
- the market-data source is stale;
- the same score repeats suspiciously across consecutive cycles.

The warning must identify the probable cause rather than merely saying `HOLD`.

Example:

```text
NO-TRADE ANOMALY
54 consecutive HOLD
54/54 cycles missing 1m movement
AI engine degraded
Market Pulse data not reaching decision context
Trading paused pending data repair
```

## 16. Cycle cadence

The dashboard may observe the runtime every few seconds, but strategy cadence must remain explicit.

For scalping:

- market data can update continuously;
- 1-minute evidence may update every minute or faster from trades;
- strategy evaluation may run on a controlled cadence;
- a new cycle must not be created by a dashboard refresh;
- overlapping cycles are prohibited.

## 17. Research-inspired observability

The dashboard should expose the same chain used by the decision engine:

```text
Market snapshot
  -> Agent evidence
  -> Bull case
  -> Bear case
  -> Trader proposal
  -> Risk review
  -> Execution result
```

This is preferable to showing only `BUY/SELL/HOLD`.

## 18. Implementation priority

The next implementation phase is ordered strictly:

1. repair the Indodax short-horizon market-data contract;
2. persist 1m/5m/15m/30m movement used by each cycle;
3. separate DATA_UNAVAILABLE / AI_DEGRADED from HOLD;
4. ensure specialist agents produce directional evidence from valid data;
5. add bull/bear conflict review;
6. adapt the scalping opportunity engine to the new signal bus;
7. keep the deterministic risk gate unchanged;
8. expand Supabase audit fields;
9. add consecutive-HOLD anomaly detection;
10. only then run another multi-hour paper test.

## 19. Acceptance criteria before the next 2-hour test

The bot is not ready for another long paper run until all of these are true:

- 1m movement is non-null when valid Indodax data exists;
- 5m/15m/30m movement is populated or explicitly unavailable;
- Market Pulse and AI cycle consume the same market snapshot;
- AI degradation is visible and does not masquerade as ordinary HOLD;
- at least one deterministic directional signal can be produced from valid market data;
- BUY/SELL candidates can reach the risk gate when their evidence satisfies configured thresholds;
- HOLD remains possible and valid;
- no forced trades are introduced merely to make the statistics look active;
- every cycle is reconstructable from Supabase;
- a repeated-HOLD anomaly stops or flags the runtime instead of wasting hours.

## 20. Scope rule

This amendment changes the trading brain's behavior and data contract. It does not authorize:

- live trading;
- removal of risk controls;
- changing the current Market Pulse visual design;
- adding unrelated AI features;
- copying source code from reference repositories.

The project adopts the useful behavioral patterns from the reviewed repositories while retaining its own Indodax, Supabase, Cloudflare, paper-trading, and multi-agent boundaries.
