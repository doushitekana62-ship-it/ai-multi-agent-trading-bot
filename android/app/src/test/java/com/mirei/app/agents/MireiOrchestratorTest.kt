package com.mirei.app.agents

import com.mirei.app.core.DecisionMode
import com.mirei.app.core.MarketSnapshot
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MireiOrchestratorTest {
    private val snapshot = MarketSnapshot(
        symbol = "BTC/IDR",
        price = 1_000_000.0,
        momentumPercent = 0.4,
        volatilityPercent = 0.5,
        sentimentScore = 10.0,
        forecastConfidence = 0.9,
        dataFresh = true,
    )

    private fun agent(type: AgentType, action: AgentAction) = object : MireiAgent {
        override val type = type
        override fun evaluate(snapshot: MarketSnapshot) = AgentObservation(type, action, 0.8, "test")
    }

    @Test
    fun suggestionModeHoldsOnConflict() {
        val decision = MireiOrchestrator(
            listOf(agent(AgentType.MARKET, AgentAction.BUY), agent(AgentType.SENTIMENT, AgentAction.HOLD)),
            DecisionMode.SUGGESTION,
        ).evaluate(snapshot)

        assertEquals(AgentAction.HOLD, decision.action)
        assertTrue(decision.requiresHumanDecision)
    }

    @Test
    fun consensusBuyDoesNotRequireHumanDecision() {
        val decision = MireiOrchestrator(
            listOf(agent(AgentType.MARKET, AgentAction.BUY), agent(AgentType.CANDLE, AgentAction.BUY)),
            DecisionMode.SUGGESTION,
        ).evaluate(snapshot)

        assertEquals(AgentAction.BUY, decision.action)
        assertEquals(false, decision.requiresHumanDecision)
    }
}
