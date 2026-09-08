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
    fun staleMarketDataDoesNotOpenPosition() {
        val runtime = MireiPaperTradingRuntime(
            marketData = MutableMarket(10_000.0, fresh = false),
            symbol = "BTC/IDR",
        )

        val status = runtime.tick(1_000L)

        assertTrue(status.activePositions.isEmpty())
        assertEquals(null, status.lastExecution)
    }

    @Test
    fun conflictingAgentsRequireHumanDecisionAndDoNotExecute() {
        val market = object : PaperMarketDataSource {
            override fun snapshot(symbol: String) = MarketSnapshot(
                symbol = symbol,
                price = 10_000.0,
                momentumPercent = 1.0,
                volatilityPercent = 0.5,
                sentimentScore = -40.0,
                forecastConfidence = 0.90,
                dataFresh = true,
            )
        }
        val runtime = MireiPaperTradingRuntime(marketData = market, symbol = "BTC/IDR")

        val status = runtime.tick(1_000L)

        assertTrue(status.activePositions.isEmpty())
        assertTrue(status.lastDecision!!.requiresHumanDecision)
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
