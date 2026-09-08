package com.mirei.app.core

import com.mirei.app.execution.ExchangeAdapter
import com.mirei.app.execution.ExchangeHandle
import com.mirei.app.execution.ExchangeRegistry
import com.mirei.app.execution.ExecutionResult
import com.mirei.app.execution.PaperExecutionEngine
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

    private fun paperPlan(
        stake: Double = 50_000.0,
        entry: Double = 1_000_000.0,
        stop: Double = 995_000.0,
        target: Double = 1_010_000.0,
    ) = EntryPlan(
        allowed = true,
        entryPrice = entry,
        stopLossPrice = stop,
        takeProfitPrice = target,
        trailingActivationPrice = 1_005_000.0,
        stakeIdr = stake,
        reasons = listOf("test"),
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
        val plan = MireiDecisionEngine(config).buildEntryPlan(bullishSnapshot(), healthyRisk(dailyPnlIdr = -4_500.0))
        assertFalse(plan.allowed)
        assertTrue(plan.reasons.contains("daily_loss_limit"))
    }

    @Test
    fun staleMarketDataBlocksEntry() {
        val plan = MireiDecisionEngine(config).buildEntryPlan(bullishSnapshot(dataFresh = false), healthyRisk())
        assertFalse(plan.allowed)
        assertTrue(plan.reasons.contains("market_snapshot_stale"))
    }

    @Test
    fun negativeSentimentBlocksEntry() {
        val plan = MireiDecisionEngine(config).buildEntryPlan(bullishSnapshot(sentimentScore = -30.0), healthyRisk())
        assertFalse(plan.allowed)
        assertTrue(plan.reasons.contains("negative_sentiment_hold"))
    }

    @Test
    fun positionLimitBlocksEntry() {
        val plan = MireiDecisionEngine(config).buildEntryPlan(bullishSnapshot(), healthyRisk(openPositions = 3))
        assertFalse(plan.allowed)
        assertTrue(plan.reasons.contains("position_limit"))
    }

    @Test
    fun paperEntryChargesFeeAndUsesActualFillForProtection() {
        val engine = PaperExecutionEngine(initialBalanceIdr = 150_000.0, feePercent = 0.3, slippagePercent = 0.05)
        val result = engine.open("paper", "BTC/IDR", paperPlan(), 1L)
        assertTrue(result.success)
        assertEquals(99_850.0, result.remainingBalanceIdr, 0.001)
        val position = engine.positions().single()
        assertEquals(1_000_500.0, position.entryPrice, 0.001)
        assertEquals(995_497.5, position.stopLossPrice, 0.001)
        assertEquals(1_010_505.0, position.takeProfitPrice, 0.001)
    }

    @Test
    fun paperFourthEntryIsRejected() {
        val engine = PaperExecutionEngine(initialBalanceIdr = 200_000.0, feePercent = 0.0, slippagePercent = 0.0)
        repeat(3) { index ->
            assertTrue(engine.open("paper", "BTC$index/IDR", paperPlan(), index.toLong()).success)
        }
        val rejected = engine.open("paper", "BTC/IDR", paperPlan(stake = 10_000.0), 4L)
        assertFalse(rejected.success)
        assertEquals("paper_position_limit", rejected.error)
    }

    @Test
    fun paperInsufficientBalanceIsRejected() {
        val engine = PaperExecutionEngine(initialBalanceIdr = 50_000.0, feePercent = 0.3, slippagePercent = 0.0)
        val rejected = engine.open("paper", "BTC/IDR", paperPlan(), 1L)
        assertFalse(rejected.success)
        assertEquals("insufficient_paper_balance", rejected.error)
        assertEquals(50_000.0, engine.availableBalanceIdr(), 0.001)
    }

    @Test
    fun paperCloseReturnsCapitalAndNetPnl() {
        val engine = PaperExecutionEngine(initialBalanceIdr = 150_000.0, feePercent = 0.3, slippagePercent = 0.05)
        val opened = engine.open("paper", "BTC/IDR", paperPlan(), 1L)
        val closed = engine.close(opened.orderId!!, 1_010_000.0, "take_profit")
        assertTrue(closed.success)
        assertEquals(148.17666, closed.pnlIdr, 0.01)
        assertEquals(150_148.17666, engine.availableBalanceIdr(), 0.01)
        assertEquals("take_profit", closed.reason)
        assertEquals(0, engine.positionCount())
    }

    @Test
    fun exchangeRegistryReturnsOnlyEnabledAdapters() {
        val paper = TestExchangeAdapter("paper")
        val bybit = TestExchangeAdapter("bybit")
        val registry = ExchangeRegistry()
        registry.register(ExchangeHandle("paper", "Paper", paper, tradingEnabled = false))
        registry.register(ExchangeHandle("bybit", "Bybit", bybit, tradingEnabled = true))

        assertEquals(listOf("paper", "bybit"), registry.ids())
        assertEquals(listOf(bybit), registry.activeTradingAdapters())
        assertEquals("Bybit", registry.get("bybit")!!.displayName)
    }

    private class TestExchangeAdapter(override val exchangeId: String) : ExchangeAdapter {
        override suspend fun fetchPrice(symbol: String): Double = 1_000_000.0
        override suspend fun placeMarketBuy(symbol: String, quoteAmount: Double): ExecutionResult = ExecutionResult(true)
        override suspend fun placeLimitBuy(symbol: String, quoteAmount: Double, limitPrice: Double): ExecutionResult = ExecutionResult(true)
        override suspend fun closePosition(positionId: String, reason: String): ExecutionResult = ExecutionResult(true, reason = reason)
    }
}
