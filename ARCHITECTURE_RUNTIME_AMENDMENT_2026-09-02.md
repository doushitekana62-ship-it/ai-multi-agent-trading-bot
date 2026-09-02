# Runtime Amendment — 2026-09-02

This amendment is binding for the production paper-scalping runtime.

## 1. One market-data source

Every analytical role must consume the same normalized market snapshot sourced from INDODAX public market data. The runtime must not mix exchanges, synthetic sentiment, stale browser samples, or independent ticker feeds into the decision.

The accepted source labels are `INDODAX public market data` and `INDODAX public ticker`. The ticker is an observation from the same exchange, not a second market source.

## 2. Fast observation cadence

The Durable Object alarm runs every 5 seconds. Market observations are persisted on every alarm. The decision cycle runs every 15 seconds. The dashboard polls every 2 seconds.

The 30-minute Market Pulse is exactly 30 one-minute segments. A segment is GREEN when the persisted Indodax observations inside that minute move upward, RED when they move downward, and GRAY when there are not enough observations to establish a move.

## 3. Prediction rules

Forecasting must estimate near-term directional edge from observed returns, persistence and volatility. It must not repeatedly extrapolate the same drift into a fictional future price path.

Confidence is an evidence score, not a calibrated probability of winning. Trade approval requires expected movement to exceed estimated round-trip friction and enough independent confirmations.

## 4. Sentiment rules

The Sentiment Agent is market sentiment derived from the shared Indodax tape: short-term price momentum, buy/sell trade imbalance and volume confirmation. It must not fabricate or silently substitute news/social/fear-greed data.

## 5. Persistence rules

Market observations are persisted through `upsert_market_observation(jsonb)`, a SECURITY DEFINER Supabase function. The function validates source, symbol, price and time bucket and updates the current one-minute record. `market_observations` is included in the Supabase Realtime publication.

Decision rows are written to `public.decisions` after the authoritative paper state is updated. Persistence failures are cycle failures; they are not silently ignored.

## 6. Dashboard rules

There is one Market Pulse presentation on the dashboard. It contains the 30 one-minute blocks, live price, net 30-minute movement and source label. No separate UP/DOWN/FLAT status overlay is allowed.

The dashboard market route reads persisted Supabase observations and supplements only the latest live INDODAX ticker when needed. The dashboard must not build its own independent market history as a trading signal.

## 7. Execution safety

Real trading remains locked. Risk controls remain downstream of the directional candidate. A rejected execution must remain auditable as a rejected candidate; it must never be represented as a filled trade.
