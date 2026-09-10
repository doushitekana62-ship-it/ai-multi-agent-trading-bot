package com.mirei.app.agents

import com.mirei.app.core.MarketSnapshot
import kotlin.math.abs

/** Deterministic paper agents driven by the same shared semantic evidence. */
class CandleTheoryAgent : MireiAgent {
    override val type: AgentType = AgentType.CANDLE

    override fun evaluate(snapshot: MarketSnapshot): AgentObservation {
        val evidence = MireiAgentEvidenceLibrary.analyze(snapshot)
        val signal = evidence.candleScore
        val confidence = (0.55 + abs(signal) / 220.0).coerceIn(0.55, 0.95)
        return when {
            signal > 2.0 -> AgentObservation(type, AgentAction.BUY, confidence, "short_term_price_action_bullish")
            signal < -2.0 -> AgentObservation(type, AgentAction.CLOSE, confidence, "short_term_price_action_bearish")
            else -> AgentObservation(type, AgentAction.HOLD, confidence, "short_term_candle_confirmation_weak")
        }
    }
}

class MomentumAgent : MireiAgent {
    override val type: AgentType = AgentType.MARKET

    override fun evaluate(snapshot: MarketSnapshot): AgentObservation {
        val evidence = MireiAgentEvidenceLibrary.analyze(snapshot)
        val signal = evidence.momentumScore
        val confidence = (0.55 + abs(signal) / 220.0).coerceIn(0.55, 0.95)
        return when {
            signal > 2.0 -> AgentObservation(type, AgentAction.BUY, confidence, "shared_market_momentum_positive")
            signal < -2.0 -> AgentObservation(type, AgentAction.CLOSE, confidence, "shared_market_momentum_negative")
            else -> AgentObservation(type, AgentAction.HOLD, confidence, "shared_market_momentum_not_confirmed")
        }
    }
}

class SentimentAgent : MireiAgent {
    override val type: AgentType = AgentType.SENTIMENT

    override fun evaluate(snapshot: MarketSnapshot): AgentObservation {
        val evidence = MireiAgentEvidenceLibrary.analyze(snapshot)
        val demand = evidence.demandScore
        val forecastSupport = evidence.forecastDirectionScore
        val confidence = (0.55 + abs(demand) / 220.0 + evidence.forecastAgreement * 0.10).coerceIn(0.55, 0.95)
        return when {
            demand <= -12.0 && forecastSupport < -1.0 -> AgentObservation(type, AgentAction.CLOSE, confidence, "demand_negative_with_forecast_support")
            demand >= 7.0 && forecastSupport > 1.0 -> AgentObservation(type, AgentAction.BUY, confidence, "demand_positive_with_forecast_support")
            else -> AgentObservation(type, AgentAction.HOLD, confidence, "demand_not_confirmed_by_forecast")
        }
    }
}

class ForecastAgent : MireiAgent {
    override val type: AgentType = AgentType.FORECAST

    override fun evaluate(snapshot: MarketSnapshot): AgentObservation {
        val evidence = MireiAgentEvidenceLibrary.analyze(snapshot)
        val direction = evidence.forecastDirectionScore
        val confidence = MireiAgentEvidenceLibrary.forecastConfidence(snapshot, evidence)
        val action = when {
            direction <= -2.5 && confidence >= 0.55 -> AgentAction.CLOSE
            direction >= 2.5 && confidence >= 0.55 -> AgentAction.BUY
            else -> AgentAction.HOLD
        }
        val reason = when (action) {
            AgentAction.BUY -> "forecast_supported_by_shared_agent_evidence"
            AgentAction.CLOSE -> "forecast_bearish_supported_by_shared_agent_evidence"
            AgentAction.HOLD -> "forecast_direction_or_shared_evidence_weak"
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
