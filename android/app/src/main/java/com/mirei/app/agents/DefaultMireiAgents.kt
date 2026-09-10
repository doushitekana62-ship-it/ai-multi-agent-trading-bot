package com.mirei.app.agents

import com.mirei.app.core.MarketSnapshot
import kotlin.math.abs

/** Deterministic paper agents driven by the live market snapshot. */
class CandleTheoryAgent : MireiAgent {
    override val type: AgentType = AgentType.CANDLE

    override fun evaluate(snapshot: MarketSnapshot): AgentObservation {
        val signal = (snapshot.change1mPercent * 35.0 + snapshot.change5mPercent * 12.0 + snapshot.change15mPercent * 4.0)
            .coerceIn(-100.0, 100.0)
        val confidence = (0.55 + abs(signal) / 220.0).coerceIn(0.55, 0.95)
        return if (signal > 2.0) {
            AgentObservation(type, AgentAction.BUY, confidence, "short_term_price_action_bullish")
        } else {
            AgentObservation(type, AgentAction.HOLD, confidence, "short_term_candle_confirmation_weak")
        }
    }
}

class MomentumAgent : MireiAgent {
    override val type: AgentType = AgentType.MARKET

    override fun evaluate(snapshot: MarketSnapshot): AgentObservation {
        val signal = snapshot.trendScorePercent
        val confidence = (0.55 + abs(signal) / 220.0).coerceIn(0.55, 0.95)
        return if (signal > 2.0) {
            AgentObservation(type, AgentAction.BUY, confidence, "market_trend_positive")
        } else {
            AgentObservation(type, AgentAction.HOLD, confidence, "market_trend_not_confirmed")
        }
    }
}

class SentimentAgent : MireiAgent {
    override val type: AgentType = AgentType.SENTIMENT

    override fun evaluate(snapshot: MarketSnapshot): AgentObservation {
        val score = snapshot.sentimentScore
        val confidence = (0.55 + abs(score) / 220.0).coerceIn(0.55, 0.95)
        return when {
            score <= -30.0 -> AgentObservation(type, AgentAction.HOLD, confidence, "trade_flow_and_price_sentiment_negative")
            score >= 8.0 -> AgentObservation(type, AgentAction.BUY, confidence, "trade_flow_and_price_sentiment_positive")
            else -> AgentObservation(type, AgentAction.HOLD, confidence, "trade_flow_sentiment_neutral")
        }
    }
}

class ForecastAgent : MireiAgent {
    override val type: AgentType = AgentType.FORECAST

    override fun evaluate(snapshot: MarketSnapshot): AgentObservation {
        val confidence = snapshot.forecastConfidence.coerceIn(0.50, 0.95)
        val action = if (snapshot.trendScorePercent >= 2.0 && confidence >= 0.65) AgentAction.BUY else AgentAction.HOLD
        val reason = if (action == AgentAction.BUY) {
            "price_momentum_flow_forecast_bullish"
        } else {
            "forecast_direction_or_confidence_weak"
        }
        return AgentObservation(type, action, confidence, reason)
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
