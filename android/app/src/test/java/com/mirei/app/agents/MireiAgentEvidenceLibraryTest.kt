package com.mirei.app.agents

import com.mirei.app.core.MarketSnapshot
import org.junit.Assert.assertTrue
import org.junit.Test

class MireiAgentEvidenceLibraryTest {
    @Test
    fun forecastUsesSharedEvidenceAgreement() {
        val evidence = MireiAgentEvidenceLibrary.analyze(
            MarketSnapshot(
                symbol = "TEST/IDR",
                price = 100_000.0,
                momentumPercent = 1.5,
                volatilityPercent = 0.5,
                sentimentScore = 20.0,
                forecastConfidence = 0.80,
                dataFresh = true,
                high24h = 110_000.0,
                low24h = 90_000.0,
                change1mPercent = 0.10,
                change5mPercent = 0.20,
                change15mPercent = 0.30,
                tradeFlowPercent = 30.0,
                trendScorePercent = 8.0,
            )
        )

        val confidence = MireiAgentEvidenceLibrary.forecastConfidence(
            MarketSnapshot("TEST/IDR", 100_000.0, 1.5, 0.5, 20.0, 0.80, true),
            evidence,
        )

        assertTrue(evidence.demandScore > 0.0)
        assertTrue(evidence.forecastDirectionScore > 0.0)
        assertTrue(confidence >= 0.50)
        assertTrue(confidence <= 0.95)
    }
}
