package com.mirei.app.agents

import com.mirei.app.core.DecisionMode
import com.mirei.app.core.MarketSnapshot
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class MireiOrchestratorVoteTest {
    private val snapshot = MarketSnapshot(
        symbol = "TEST/IDR",
        price = 100_000.0,
        momentumPercent = 0.5,
        volatilityPercent = 0.5,
        sentimentScore = 10.0,
        forecastConfidence = 0.80,
        dataFresh = true,
    )

    private fun agent(type: AgentType, action: AgentAction, confidence: Double = 0.80) = object : MireiAgent {
        override val type = type
        override fun evaluate(snapshot: MarketSnapshot) = AgentObservation(type, action, confidence, "test")
    }

    @Test
    fun majorityVoteWinsConflictWithoutHumanConfirmation() {
        val decision = MireiOrchestrator(
            listOf(
                agent(AgentType.CANDLE, AgentAction.BUY),
                agent(AgentType.MARKET, AgentAction.BUY),
                agent(AgentType.SENTIMENT, AgentAction.HOLD),
                agent(AgentType.FORECAST, AgentAction.CLOSE),
            ),
            DecisionMode.SUGGESTION,
        ).evaluate(snapshot)

        assertEquals(AgentAction.BUY, decision.action)
        assertFalse(decision.requiresHumanDecision)
        assertEquals("agent_majority_vote", decision.rationale)
    }

    @Test
    fun tiedVoteWithEqualConfidenceStillHolds() {
        val decision = MireiOrchestrator(
            listOf(
                agent(AgentType.CANDLE, AgentAction.BUY),
                agent(AgentType.MARKET, AgentAction.CLOSE),
            ),
            DecisionMode.SUGGESTION,
        ).evaluate(snapshot)

        assertEquals(AgentAction.HOLD, decision.action)
        assertFalse(decision.requiresHumanDecision)
        assertEquals("agent_vote_tie_hold", decision.rationale)
    }

    @Test
    fun tiedVoteUsesConfidenceWhenDirectionalEvidenceIsStronger() {
        val decision = MireiOrchestrator(
            listOf(
                agent(AgentType.CANDLE, AgentAction.BUY, 0.95),
                agent(AgentType.MARKET, AgentAction.CLOSE, 0.80),
            ),
            DecisionMode.SUGGESTION,
        ).evaluate(snapshot)

        assertEquals(AgentAction.BUY, decision.action)
        assertFalse(decision.requiresHumanDecision)
        assertEquals("agent_confidence_weighted_tie_resolved", decision.rationale)
    }
}
