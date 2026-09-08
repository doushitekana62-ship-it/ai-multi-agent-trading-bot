package com.mirei.app.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MireiDecisionEngineTest {
    private val config = TradingConfig()

    private fun healthyRisk(
        dailyPnlIdr: Double = 0.0,
        openPositions: Int = 0,
        consecutiveLosses: Int = 0,
    ) = RiskSnapshot(
        dailyPnlIdr = dailyPnlIdr,
        dailyStartBalanceIdr = 150_000.0,
        equityIdr = 150_000.0 + dailyPnlIdr,
        openPositions = openPositions,
        consecutiveLosses = consecutiveLosses,
        marketDataFresh = true,
        exchangeHealthy = true,
        internetAvailable = true,
    )

    private fun bullishSnapshot(
        sentimentScore: Double = 20.0,
        dataFresh: Boolean = true,
    ) = MarketSnapshot(
        symbol = "BTC/IDR",
        price = 1_000_000.0,
        momentumPercent = 0.4,
        volatilityPercent = 0.5,
        sentimentScore = sentimentScore,
        forecastConfidence = 0.9,
        dataFresh = dataFresh,
    )

    @Test
    fun healthySignalIsAllowed() {
        val plan = MireiDecisionEngine(config).buildEntryPlan(bullishSnapshot(), healthyRisk())

        assertTrue(plan.allowed)
        assertEquals(50_000.0 * 0.85, plan.stakeIdr, 0.001)
        assertEquals(995_000.0, plan.stopLossPrice, 0.001)
        assertEquals(1_010_000.0, plan.takeProfitPrice, 0.001)
    }

    @Test
    fun dailyLossLimitBlocksEntry() {
        val plan = MireiDecisionEngine(config).buildEntryPlan(
            bullishSnapshot(),
            healthyRisk(dailyPnlIdr = -4_500.0),
        )

        assertFalse(plan.allowed)
        assertTrue(plan.reasons.contains("daily_loss_limit"))
    }

    @Test
    fun staleMarketDataBlocksEntry() {
        val plan = MireiDecisionEngine(config).buildEntryPlan(
            bullishSnapshot(dataFresh = false),
            healthyRisk(),
        )

        assertFalse(plan.allowed)
        assertTrue(plan.reasons.contains("market_snapshot_stale"))
    }

    @Test
    fun negativeSentimentBlocksEntry() {
        val plan = MireiDecisionEngine(config).buildEntryPlan(
            bullishSnapshot(sentimentScore = -30.0),
            healthyRisk(),
        )

        assertFalse(plan.allowed)
        assertTrue(plan.reasons.contains("negative_sentiment_hold"))
    }

    @Test
    fun positionLimitBlocksEntry() {
        val plan = MireiDecisionEngine(config).buildEntryPlan(
            bullishSnapshot(),
            healthyRisk(openPositions = 3),
        )

        assertFalse(plan.allowed)
        assertTrue(plan.reasons.contains("position_limit"))
    }
}
