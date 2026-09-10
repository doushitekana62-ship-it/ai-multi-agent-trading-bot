package com.mirei.app.agents

import com.mirei.app.core.DecisionMode
import com.mirei.app.core.MarketSnapshot
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
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
    fun conflictUsesMajorityVoteWithoutHumanConfirmation() {
        val decision = MireiOrchestrator(
            listOf(
                agent(AgentType.MARKET, AgentAction.BUY),
                agent(AgentType.SENTIMENT, AgentAction.HOLD),
                agent(AgentType.CANDLE, AgentAction.BUY),
                agent(AgentType.FORECAST, AgentAction.CLOSE),
            ),
            DecisionMode.SUGGESTION,
        ).evaluate(snapshot)

        assertEquals(AgentAction.BUY, decision.action)
        assertFalse(decision.requiresHumanDecision)
        assertEquals("agent_majority_vote", decision.rationale)
    }

    @Test
    fun exactTieMeansHoldWithoutHumanConfirmation() {
        val decision = MireiOrchestrator(
            listOf(agent(AgentType.MARKET, AgentAction.BUY), agent(AgentType.SENTIMENT, AgentAction.CLOSE)),
            DecisionMode.SUGGESTION,
        ).evaluate(snapshot)

        assertEquals(AgentAction.HOLD, decision.action)
        assertFalse(decision.requiresHumanDecision)
        assertEquals("agent_vote_tie_hold", decision.rationale)
    }

    @Test
    fun unanimousBuyRemainsBuy() {
        val decision = MireiOrchestrator(
            listOf(agent(AgentType.MARKET, AgentAction.BUY), agent(AgentType.CANDLE, AgentAction.BUY)),
            DecisionMode.SUGGESTION,
        ).evaluate(snapshot)

        assertEquals(AgentAction.BUY, decision.action)
        assertFalse(decision.requiresHumanDecision)
        assertEquals("agent_unanimous_vote", decision.rationale)
    }
}
