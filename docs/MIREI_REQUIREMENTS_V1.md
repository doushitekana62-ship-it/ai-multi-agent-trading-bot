# Mirei ミレイ — Requirements v1

Status: baseline from customer requirements session

## Product

Mirei is a private Android-first automated compounding scalping application. The primary objective is small, consistent profit with healthy risk/reward, not maximum trade count or maximum return.

## Trading

- Crypto only; exchange-agnostic architecture.
- Multiple exchanges must be supported (for example Indodax and Bybit).
- Maximum 3 simultaneous positions by default.
- Default total capital: Rp150,000.
- Default position allocation: Rp50,000 each; configurable from the app.
- Use all realized profit for compounding.
- If a position slot cannot be funded, keep it idle and notify the user.
- No fixed daily trade-count limit.
- Re-entry is allowed when capital and risk conditions permit.
- Market and limit orders are required.
- TP and SL are mandatory on every position.
- Baseline SL: 0.5% from entry price.
- Baseline TP: 1% from entry price.
- TP/SL may adapt to market conditions, forecast and selected scalping mode.
- Position sizing and trailing distance must adapt to extreme volatility without simply increasing acceptable loss.
- Partial close and breakeven are allowed.
- Trailing may use 1R activation, breakout/first-target behavior, ATR and swing high/low.

## Scalping modes

- Aggressive
- Balanced
- Safety

## Agents

Mirei is the orchestrator. Supporting agents include:

- Market/data agent
- Candle/technical analysis agent
- Forecast agent
- Sentiment agent
- Risk agent
- Learning agent

Forecasting is subordinate to Mirei and is used primarily for momentum/candlestick-based forecasting.

Sentiment may range from -100 to +100. A value at or below -30 is considered materially negative, but negative sentiment alone must not forcibly stop the bot. The sentiment agent may recommend HOLD. Prolonged deterioration may cause position exit consideration.

The theory library provides theory/reference only and must not inject its own opinion.

## Decision modes

### Suggestion (default)

Mirei provides analysis and recommendations. Conflicting important agent decisions require human approval.

### Mirei Take Over

Explicit opt-in mode. Mirei may automatically change parameters and make decisions that normally require approval. The app must display a warning before activation and audit important automatic changes.

## Runtime states

- START/RUNNING
- HOLD
- STOP/SLEEP
- CLOSE ALL / AUTO SELL
- ERROR
- RECOVERY

HOLD means no new positions while active positions continue to be managed by the risk/execution rules.

STOP puts Mirei to sleep and prevents trading. CLOSE ALL closes active positions. Android reboot must not automatically restart trading.

## Android runtime

Mirei must continue operating with screen off, app backgrounded and device locked using an Android foreground service. The service is allowed to be permanent.

Network loss causes immediate stop/HOLD and notification. Network recovery does not automatically resume trading; the user must reopen/restart Mirei.

## Paper trading

Paper trading is required and uses the same strategy/risk behavior as live trading, with a separate execution layer. It uses realtime market data and simulates fees, slippage and configurable virtual capital.

## Storage

Local-first Android storage is the primary data store. Keep data until the user deletes it.

Persist at minimum:

- trade history
- bot settings
- performance statistics
- logs
- AI suggestions
- learning data
- audit records
- exchange configuration

Google Drive is for manual backup only. Supabase is not required as the operational database under this Android-first requirement.

## Security

- Single private user; no login required.
- Exchange keys must be trade-only and must not have withdrawal permission.
- Credentials should use Android secure storage/Keystore-backed encryption.
- Provide delete-key functionality.
- Never intentionally expose secrets in logs.

## Notifications

Notify for trade open/close, TP, SL, errors, bot stop/recovery, insufficient capital, market-data failure, exchange failure, important risk/sentiment events and agent conflicts requiring approval.

## Success criteria

Initial evaluation period: 7 days.

Success means automatic open/close, adaptive TP/SL, realtime market data, useful AI suggestions, healthy risk/reward, learning from wins and losses, and stable long-running operation. Mirei may choose NO TRADE when conditions are unhealthy.
