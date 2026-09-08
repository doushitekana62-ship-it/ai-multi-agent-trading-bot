package com.mirei.app.agents

import com.mirei.app.core.MarketSnapshot

/** Deterministic baseline agents used by paper runtime until richer models are plugged in. */
class CandleTheoryAgent : MireiAgent {
    override val type: AgentType = AgentType.CANDLE

    override fun evaluate(snapshot: MarketSnapshot): AgentObservation =
        if (snapshot.momentumPercent > 0.0) {
            AgentObservation(type, AgentAction.BUY, 0.70, "positive_momentum_supports_candle_entry")
        } else {
            AgentObservation(type, AgentAction.HOLD, 0.70, "candle_entry_not_confirmed")
        }
}

class MomentumAgent : MireiAgent {
    override val type: AgentType = AgentType.MARKET

    override fun evaluate(snapshot: MarketSnapshot): AgentObservation {
        val confidence = (0.60 + (snapshot.momentumPercent.coerceIn(0.0, 2.0) / 2.0) * 0.30).coerceIn(0.0, 1.0)
        return if (snapshot.momentumPercent > 0.0) {
            AgentObservation(type, AgentAction.BUY, confidence, "momentum_positive")
        } else {
            AgentObservation(type, AgentAction.HOLD, 0.70, "momentum_non_positive")
        }
    }
}

class SentimentAgent : MireiAgent {
    override val type: AgentType = AgentType.SENTIMENT

    override fun evaluate(snapshot: MarketSnapshot): AgentObservation =
        if (snapshot.sentimentScore <= -30.0) {
            AgentObservation(type, AgentAction.HOLD, 0.90, "sentiment_below_hold_threshold")
        } else {
            AgentObservation(type, AgentAction.BUY, 0.65, "sentiment_not_blocking_entry")
        }
}

class ForecastAgent : MireiAgent {
    override val type: AgentType = AgentType.FORECAST

    override fun evaluate(snapshot: MarketSnapshot): AgentObservation {
        val action = if (snapshot.forecastConfidence >= 0.65) AgentAction.BUY else AgentAction.HOLD
        return AgentObservation(
            type,
            action,
            snapshot.forecastConfidence.coerceIn(0.0, 1.0),
            if (action == AgentAction.BUY) "forecast_confidence_supports_entry" else "forecast_confidence_low",
        )
    }
}

object DefaultMireiAgents {
    fun create(): List<MireiAgent> = listOf(
        CandleTheoryAgent(),
        MomentumAgent(),
        SentimentAgent(),
        ForecastAgent(),
    )
}
