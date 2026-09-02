# AI Multi-Agent Trading Bot — Architecture Contract

# COMPOUNDING SCALPING

> **Architecture v0.4 — COMPOUNDING SCALPING**
>
> **Status:** CANONICAL STRATEGIC DIRECTION / IMPLEMENTATION SOURCE OF TRUTH — 2026-09-02
>
> **Implementation rule:** This architecture update defines the strategic direction and contracts. Implementation changes require explicit project-owner instruction.
>
> **Previous version:** The complete v0.3 baseline is preserved unchanged in `ARCHITECTURE_v0.3.md` and in Git history.

## 1. Strategic Mission — COMPOUNDING SCALPING

The project's intended trading direction is **COMPOUNDING SCALPING**.

Compounding scalping means the system seeks small, repeatable, risk-controlled opportunities and automatically carries the resulting account capital/equity into the sizing reference of subsequent trades.

The objective is not maximum profit per trade. The objective is a sustainable short-horizon trading loop:

```text
CURRENT CAPITAL / EQUITY
        ↓
MARKET OBSERVATION
        ↓
SMALL VALID EDGE
        ↓
DETERMINISTIC RISK
        ↓
POSITION SIZING
        ↓
ENTRY
        ↓
POSITION MANAGEMENT
        ↓
PROFIT / LOSS / EXIT
        ↓
REALIZED RESULT + COSTS
        ↓
UPDATED CAPITAL / EQUITY
        ↓
NEXT POSITION SIZING
        ↓
NEXT SCALP
```

A profitable trade may increase the capital base available to subsequent sizing. A losing trade decreases it. The system must never increase risk merely to recover a previous loss.

The intended behavior is **small risk, small profit, repeated only when a valid edge exists**. `HOLD` / `NO_EDGE` remains a valid outcome when conditions are insufficient.

The historical architecture rule remains explicit: **Data failure is never represented as normal HOLD.**

## 2. Compounding Capital Principle

Starting capital is an initial condition, not a permanent sizing base.

For each new position, sizing should ultimately derive from the authoritative current account state, subject to deterministic risk controls and exchange constraints.

```text
trade closes
    ↓
actual fill/result reconciled
    ↓
fees/costs recorded
    ↓
realized PnL updated
    ↓
account state updated
    ↓
current capital/equity becomes the next sizing reference
```

Compounding must not become martingale behavior.

```text
LOSS → lower/equal controlled risk
WIN  → proportionally larger opportunity only when limits permit
```

The exact risk percentage, sizing formula, exposure cap, and compounding parameters remain strategy controls to be calibrated and tested. This version intentionally does not prescribe final numerical values.

## 3. Scalping Entry Principle

The system must not require an oversized predicted price movement merely to permit trading. Excessively strict thresholds can create a technically safe but practically inactive bot.

Entry evaluation should consider, where available:

- short-horizon movement;
- market regime;
- momentum and structure;
- volume/liquidity;
- spread;
- expected movement;
- estimated fees;
- estimated slippage/execution cost;
- current account state;
- deterministic risk limits.

The key question is not simply `"Will price move 1%?"` but whether the expected net edge is sufficient for a controlled-risk scalp under current execution conditions.

Cost-awareness must not be implemented as an arbitrary gate that makes the bot unable to operate. Thresholds must be calibrated empirically in realistic paper trading.

## 4. Profit Activation Instead of a Hard Profit Ceiling

A configured initial TP percentage is not automatically a mandatory full-position liquidation point.

For the intended compounding-scalping model, a configurable profit threshold may act as **PROFIT ACTIVATION**:

```text
ENTRY
  ↓
INITIAL SL / RISK
  ↓
PROFIT ACTIVATION
  ↓
+----------------------------------+
| Momentum still valid             |
| → keep participating             |
| → protect accumulated profit     |
|                                  |
| Momentum weakens / reverses      |
| → exit                            |
+----------------------------------+
```

This allows an initial target such as +1% to activate profit protection while still allowing an unusually strong market move to continue beyond that level.

The exact dynamic/trailing mechanism must be deterministic, observable, testable, and constrained by the risk engine. AI may provide context but cannot be the execution trigger or guarantee a fill.

## 5. Dynamic Position Lifecycle

Position management is part of the automated trading lifecycle rather than a manual operator step repeated after every entry.

```text
NO POSITION
    ↓
ENTRY
    ↓
INITIAL SL + PROFIT MANAGEMENT
    ↓
PRICE MOVEMENT
    ↓
PROTECTION / TRAILING ADJUSTMENT
    ↓
EXIT
    ↓
ACCOUNT RECONCILIATION
    ↓
NEXT OPPORTUNITY
```

A rapid favorable movement must not be discarded solely because an initial profit activation threshold was reached.

A rapid adverse movement remains subject to the hard risk boundary.

High volatility may require wider deterministic protection; low volatility may permit tighter protection. Any such adaptation must be explicit and testable rather than hidden in an AI prompt.

## 6. Net Result and Execution Reality

For compounding purposes, the authoritative result of a trade is the reconciled execution result, not an idealized price movement.

```text
GROSS PRICE RESULT
    - FEES
    - SLIPPAGE / EXECUTION EFFECT
    - OTHER APPLICABLE COSTS
    = REALIZED NET RESULT
```

The system must distinguish price movement, gross trade PnL, fees, execution effect, realized PnL, balance, and equity.

The bot must not become inactive merely because a nominal target is smaller than a conservative theoretical cost estimate. Realistic costs must be modeled, measured, and calibrated against actual exchange behavior.

## 7. Indodax Compatibility Direction

The system remains **Indodax-focused**.

Compounding scalping must use the existing exchange-adapter boundary rather than embedding Indodax-specific execution logic into agents or the frontend.

```text
AI / ANALYSIS
      ↓
CANDIDATE
      ↓
DETERMINISTIC RISK
      ↓
POSITION / ORDER INTENT
      ↓
EXCHANGE ADAPTER
      ↓
INDODAX
```

Exchange constraints that affect compounding must be treated as execution inputs, including where applicable:

- available balance;
- minimum order size;
- price/quantity precision;
- fees;
- order type;
- liquidity/spread;
- fill status;
- partial/failed/unknown execution;
- account reconciliation.

The core strategy remains exchange-independent at the domain level.

## 8. AI Responsibility

AI remains advisory.

AI may estimate direction, confidence, short-horizon opportunity, momentum/regime, expected movement, evidence quality, and whether a position appears to be strengthening or weakening.

AI does not own final risk approval, authoritative account balance, authoritative position quantity, order execution, or exchange reconciliation.

Dynamic position management must remain deterministic even when external AI is unavailable.

Missing/degraded evidence is excluded from directional scoring; it is not silently converted into BUY/SELL/HOLD evidence.

## 9. Risk Principle

Compounding is permitted only inside hard risk boundaries.

The system must prevent:

```text
LOSS
 ↓
INCREASE RISK TO RECOVER
 ↓
LARGER LOSS
```

The intended behavior is:

```text
LOSS
 ↓
UPDATED LOWER CAPITAL / EQUITY
 ↓
RISK ENGINE RE-CALCULATES
 ↓
CONTROLLED NEXT POSITION
```

A winning streak must not bypass maximum exposure, daily/weekly loss limits, or other safety controls.

The risk engine remains the single authoritative deterministic control plane.

## 10. Paper Trading as the Compounding Laboratory

Paper trading remains the primary validation environment.

Before live execution is considered, paper must demonstrate an observable and reconcilable lifecycle:

```text
ENTRY
→ POSITION
→ PROFIT ACTIVATION / SL / EXIT
→ FEES + SLIPPAGE
→ REALIZED PnL
→ UPDATED BALANCE / EQUITY
→ NEXT SIZING
→ NEXT ENTRY
```

Paper execution must model relevant real-world friction rather than perfect fills. Compounding is not considered validated if it works only because costs, slippage, order failures, or execution uncertainty are ignored.

## 11. Architecture Preservation

All v0.3 responsibility boundaries remain in force unless explicitly superseded by a later approved architecture revision.

In particular:

- AI advises; deterministic trading core controls.
- Risk is a hard boundary.
- Paper trading is the default development path.
- Exchange integration is an adapter.
- One authoritative account/position state exists per environment.
- No direct agent-to-exchange execution.
- No duplicate risk engine.
- Frontend does not own authoritative trading rules.
- Persistence is an audit/state layer, not a competing trading engine.
- Cloudflare/deployment must not change trading-domain semantics.

This version adds the **COMPOUNDING SCALPING** strategic direction; implementation now proceeds under the explicit project-owner instruction.

## 12. Preserved v0.3 Operational Semantics

The following v0.3 runtime semantics remain authoritative unless explicitly superseded:

- `HOLD_EXISTING_POSITION` is a distinct position-management state.
- `AI_DEGRADED` is an explicit runtime/degradation state, not a normal HOLD reason.
- `RISK_REJECTED` is an explicit deterministic risk outcome.
- **Data failure is never represented as normal HOLD.**
- **Missing/degraded evidence is excluded from directional scoring.**

Compatibility action values may remain `BUY | SELL | HOLD`, while explicit cycle status explains why an action did or did not execute.

## 13. Change-Control for Compounding Scalping

Before implementation of any compounding-scalping behavior, explicitly identify:

1. the existing component that should own it;
2. whether it changes account state, risk, sizing, position lifecycle, execution, or observation;
3. the smallest compatible implementation path;
4. the tests needed to prove accounting and risk correctness;
5. compatibility with Indodax execution constraints;
6. preservation of paper/real behavioral parity.

## 14. Version History

- **v0.4 — COMPOUNDING SCALPING:** strategic direction established on 2026-09-02.
- **v0.3:** previous canonical baseline, preserved unchanged in `ARCHITECTURE_v0.3.md` and Git history.
