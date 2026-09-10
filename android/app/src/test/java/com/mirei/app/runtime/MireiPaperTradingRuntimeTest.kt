package com.mirei.app.runtime

import com.mirei.app.core.MarketSnapshot
import com.mirei.app.core.TradingConfig
import com.mirei.app.execution.PaperPosition
import com.mirei.app.execution.TradeLedger
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class MireiPaperTradingRuntimeTest {
    @Test
    fun healthyPaperTickCreatesPositionThroughAgentsAndDecisionEngine() {
        val market = MutableMarket(10_000.0)
        val runtime = MireiPaperTradingRuntime(
            marketData = market,
            symbol = "BTC/IDR",
            tradeLedger = RecordingLedger(),
        )

        val status = runtime.tick(1_000L)

        assertEquals(1, status.activePositions.size)
        assertNotNull(status.lastDecision)
        assertNotNull(status.lastExecution)
        assertTrue(status.lastExecution!!.success)
    }

    @Test
    fun takeProfitClosesPositionAndReleasesCapitalForNextEntry() {
        val market = MutableMarket(10_000.0)
        val ledger = RecordingLedger()
        val runtime = MireiPaperTradingRuntime(
            config = TradingConfig(positionSizeIdr = 50_000.0),
            marketData = market,
            symbol = "BTC/IDR",
            tradeLedger = ledger,
        )

        val first = runtime.tick(1_000L)
        val position = first.activePositions.single()
        market.price = position.takeProfitPrice
        val second = runtime.tick(2_000L)

        assertEquals(1, second.activePositions.size)
        assertTrue(second.dailyPnlIdr > 0.0)
        assertEquals(1, ledger.closedCount)
        assertTrue(second.activePositions.single().openedAtEpochMs == 2_000L)
    }

    @Test
    fun runtimeUsesAllThreePositionSlotsAndReentersAfterOnePositionCloses() {
        val market = MutableMarket(10_000.0)
        val ledger = RecordingLedger()
        val runtime = MireiPaperTradingRuntime(
            config = TradingConfig(positionSizeIdr = 50_000.0, maxOpenPositions = 3),
            marketData = market,
            symbol = "BTC/IDR",
            tradeLedger = ledger,
        )

        runtime.tick(1_000L)
        market.price = 10_020.0
        runtime.tick(2_000L)
        market.price = 10_040.0
        val third = runtime.tick(3_000L)

        assertEquals(3, third.activePositions.size)
        assertEquals(3, ledger.openedCount)

        market.price = 10_110.0
        val reentry = runtime.tick(4_000L)

        assertEquals(3, reentry.activePositions.size)
        assertEquals(4, ledger.openedCount)
        assertEquals(1, ledger.closedCount)
        assertTrue(reentry.dailyPnlIdr > 0.0)
        assertTrue(reentry.activePositions.any { it.openedAtEpochMs == 4_000L })
    }

    @Test
    fun positionCapPreventsFourthConcurrentEntry() {
        val market = MutableMarket(10_000.0)
        val ledger = RecordingLedger()
        val runtime = MireiPaperTradingRuntime(
            config = TradingConfig(positionSizeIdr = 30_000.0, maxOpenPositions = 3),
            marketData = market,
            symbol = "BTC/IDR",
            tradeLedger = ledger,
        )

        runtime.tick(1_000L)
        runtime.tick(2_000L)
        val third = runtime.tick(3_000L)
        val capped = runtime.tick(4_000L)

        assertEquals(3, third.activePositions.size)
        assertEquals(3, capped.activePositions.size)
        assertEquals(3, ledger.openedCount)
    }

    @Test
    fun staleMarketDataDoesNotOpenPosition() {
        val runtime = MireiPaperTradingRuntime(
            marketData = MutableMarket(10_000.0, fresh = false),
            symbol = "BTC/IDR",
        )

        val status = runtime.tick(1_000L)

        assertTrue(status.activePositions.isEmpty())
        assertEquals(null, status.lastExecution)
        assertEquals(listOf("market_snapshot_stale"), status.entryPlanReasons)
    }

    @Test
    fun conflictingAgentsExposeDecisionAndEntryReasons() {
        val market = object : PaperMarketDataSource {
            override fun snapshot(symbol: String) = MarketSnapshot(
                symbol = symbol,
                price = 10_000.0,
                momentumPercent = -0.10,
                volatilityPercent = 0.5,
                sentimentScore = 10.0,
                forecastConfidence = 0.65,
                dataFresh = true,
                changeSinceLastTickPercent = -0.10,
                change1mPercent = -0.10,
                change5mPercent = -0.10,
                change15mPercent = -0.10,
                tradeFlowPercent = 0.0,
                trendScorePercent = 0.0,
            )
        }
        val runtime = MireiPaperTradingRuntime(marketData = market, symbol = "BTC/IDR")

        val status = runtime.tick(1_000L)

        assertTrue(status.activePositions.isEmpty())
        assertTrue(status.lastDecision!!.requiresHumanDecision)
        assertEquals("agent_conflict_requires_human_decision", status.lastDecision!!.rationale)
        assertTrue(status.lastDecision!!.observations.any { it.rationale == "market_trend_not_confirmed" })
        assertTrue(status.lastDecision!!.observations.any { it.rationale == "forecast_direction_or_confidence_weak" })
        assertEquals(listOf("momentum_not_positive"), status.entryPlanReasons)
    }

    private class MutableMarket(
        var price: Double,
        private val fresh: Boolean = true,
    ) : PaperMarketDataSource {
        override fun snapshot(symbol: String) = MarketSnapshot(
            symbol = symbol,
            price = price,
            momentumPercent = 1.0,
            volatilityPercent = 0.5,
            sentimentScore = 10.0,
            forecastConfidence = 0.90,
            dataFresh = fresh,
            changeSinceLastTickPercent = 0.20,
            change1mPercent = 0.20,
            change5mPercent = 0.40,
            change15mPercent = 0.60,
            tradeFlowPercent = 20.0,
            trendScorePercent = 5.0,
        )
    }

    private class RecordingLedger : TradeLedger {
        var openedCount = 0
        var closedCount = 0

        override fun recordOpened(position: PaperPosition, entryFeeIdr: Double) {
            openedCount++
        }

        override fun recordClosed(
            position: PaperPosition,
            exitPrice: Double,
            feeIdr: Double,
            pnlIdr: Double,
            closedAtEpochMs: Long,
            exitReason: String,
        ) {
            closedCount++
        }
    }
}
