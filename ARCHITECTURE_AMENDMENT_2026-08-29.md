# Architecture Amendment — 2026-08-29

This amendment is subordinate to `ARCHITECTURE.md` and records the approved implementation clarifications made during the current paper-trading trial. It must be read together with the A–L contract already recorded in `ARCHITECTURE.md`.

## 1. Market Pulse semantic legend

The dashboard must never rely on an unexplained line or color.

The Market Pulse presentation must expose these meanings:

- GREEN / UP — price increased during the rolling 30-minute dashboard window.
- RED / DOWN — price decreased during the rolling 30-minute dashboard window.
- GRAY / FLAT — movement remains below the configured flat threshold or there is insufficient directional evidence.

The rolling 30-minute dashboard window is presentation/observability state. It must not overwrite or redefine the exchange's 24-hour metrics.

The following metrics remain visible and authoritative as market context:

- 24H High;
- 24H Low;
- 24H Volume.

The 30-minute pulse may reset its rolling sample after the window expires or after a dashboard reload. The 24-hour metrics must not reset with it.

## 2. Cycle notification

When the dashboard observes a newly completed paper cycle, it may show the exact compact notification:

`1 cycle is update`

The notification is informational only. It must never start, stop, retry, or modify a trading cycle.

## 3. Trading Library alerts

The Trading Librarian may generate structured informational alerts from current OHLCV/trade-derived candle data.

Alerts may include:

- bullish/bearish engulfing;
- hammer/rejection;
- shooting-star/rejection;
- doji/indecision;
- strong candle body;
- volume confirmation;
- near-24H-high/near-24H-low context.

Every alert must include, where applicable:

- alert type;
- direction;
- confidence;
- evidence/message;
- whether confirmation is required;
- library version.

A library alert is not an execution instruction. It must not bypass the consensus layer, confidence gate, position limits, or deterministic risk controls.

The dashboard renders library alerts as popups on the LEFT side of the screen. The alert component must remain fail-silent if its endpoint is unavailable.

## 4. Candlestick data integrity

The system must not label a sequence as OHLC candles when every point is simply `open = high = low = close` from an individual trade.

When only public trades are available, the AI engine may aggregate bounded trades into real time buckets (currently 1-minute buckets) to produce derived OHLCV:

`trades -> time buckets -> OHLCV -> candlestick analysis -> agent context`

Derived candles must retain their source/derived nature. They are not equivalent to exchange-native historical candles unless the exchange explicitly provides those candles.

Insufficient data must be represented as unavailable/insufficient-data, not silently converted into a directional signal.

## 5. HOLD-conflict diagnostics

The AI engine must expose structured diagnostics when the ensemble remains HOLD or when directional agents disagree.

The diagnostic must identify:

- HOLD-voting agents;
- directional agents;
- opposing agents where applicable;
- configured influence weight of HOLD voters;
- dominant HOLD-weight agent;
- relevant technical/decision/forecast/sentiment scores.

The diagnostic identifies influence; it does not claim that an agent is objectively "wrong". The actual market outcome must be used to evaluate agent quality over time.

## 6. Knowledge-source contract

The Trading Librarian is the shared knowledge boundary for candlestick, momentum, volume, support/resistance, scalping, risk, and related trading principles.

External educational material may inform the library, but current market data remains authoritative for the current observation. Educational knowledge must not be treated as live market truth.

## 7. Defensive implementation rules

The following are mandatory safeguards for the current implementation:

1. Dashboard polling must have bounded request timeouts.
2. Polling must prevent overlapping requests.
3. Optional alert feeds must fail silently and never block the dashboard.
4. Duplicate alerts must be suppressed using a cycle/alert fingerprint.
5. Candle analysis must be bounded to a finite number of observations.
6. Invalid OHLC values must be rejected before pattern analysis.
7. Pattern detection must not directly execute an order.
8. AI-engine failure must fall back to a clearly marked local advisory path.
9. Live exchange execution remains locked.
10. Paper state remains the authoritative account ledger.
11. A frontend refresh must not create a paper cycle.
12. Any future change that alters these boundaries must update the architecture before implementation.

## 8. Current implementation note

The current dashboard uses a small frontend rolling sample for the 30-minute visual pulse so the presentation can remain responsive without changing the paper ledger. The AI engine separately aggregates bounded public trades into 1-minute OHLCV buckets for candle analysis.

The legacy paper-state schema does not yet expose every new structured field as a first-class database column. A bounded `LIBRARY_ALERTS_JSON=` compatibility bridge is therefore used in the persisted decision reasoning so the existing dashboard can surface alerts without replacing the authoritative paper-state contract. This bridge must be removed once the persistent schema is extended with a native structured alert field.
