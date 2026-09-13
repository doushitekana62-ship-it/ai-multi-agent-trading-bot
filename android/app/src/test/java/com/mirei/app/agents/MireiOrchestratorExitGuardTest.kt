package com.mirei.app.agents

import com.mirei.app.core.DecisionMode
import com.mirei.app.core.MarketSnapshot
import kotlin.test.Test
import kotlin.test.assertEquals

class MireiOrchestratorExitGuardTest {
    @Test
    fun weakBearishVoteBecomesHoldInsteadOfImmediateClose() {
        val snapshot = MarketSnapshot(
            symbol = "BTC/IDR",
            price = 10_000.0,
            bidPrice = 9_999.0,
            askPrice = 10_001.0,
            high24h = 10_500.0,
            low24h = 9_500.0,
            volume24h = 1_000.0,
            momentumPercent = -0.20,
            volatilityPercent = 0.20,
            sentimentScore = -5.0,
            forecastConfidence = 0.60,
            spreadPercent = 0.02,
            changeSinceLastTickPercent = -0.20,
            change1mPercent = -0.20,
            change5mPercent = -0.10,
            change15mPercent = -0.10,
            tradeFlowPercent = -2.0,
            trendScorePercent = 0.20,
            dataFresh = true,
        )
        val decision = MireiOrchestrator(DefaultMireiAgents.create(), DecisionMode.SUGGESTION).evaluate(snapshot)
        assertEquals(AgentAction.HOLD, decision.action)
        assertEquals("close_suppressed_insufficient_bearish_confirmation", decision.rationale)
    }

    @Test
    fun strongBearishConfirmationCanStillProduceClose() {
        val snapshot = MarketSnapshot(
            symbol = "BTC/IDR",
            price = 10_000.0,
            bidPrice = 9_999.0,
            askPrice = 10_001.0,
            high24h = 10_500.0,
            low24h = 9_500.0,
            volume24h = 1_000.0,
            momentumPercent = -5.0,
            volatilityPercent = 0.20,
            sentimentScore = -40.0,
            forecastConfidence = 0.90,
            spreadPercent = 0.02,
            changeSinceLastTickPercent = -0.50,
            change1mPercent = -0.50,
            change5mPercent = -0.50,
            change15mPercent = -0.50,
            tradeFlowPercent = -40.0,
            trendScorePercent = -5.0,
            dataFresh = true,
        )
        val decision = MireiOrchestrator(DefaultMireiAgents.create(), DecisionMode.SUGGESTION).evaluate(snapshot)
        assertEquals(AgentAction.CLOSE, decision.action)
    }
}
