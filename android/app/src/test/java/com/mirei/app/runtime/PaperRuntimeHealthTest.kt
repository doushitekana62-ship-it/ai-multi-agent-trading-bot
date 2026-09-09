package com.mirei.app.runtime

import com.mirei.app.core.EntryPlan
import com.mirei.app.core.MarketSnapshot
import com.mirei.app.execution.PaperExecutionEngine
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PaperRuntimeHealthTest {
    @Test
    fun staleSnapshotIsReportedAsDegradedWithoutOpening() {
        val runtime = MireiPaperTradingRuntime(
            marketData = object : PaperMarketDataSource {
                override fun snapshot(symbol: String) = MarketSnapshot(symbol, 10_000.0, 1.0, 0.5, 0.0, 0.65, false)
            },
            symbol = "BTC/IDR",
        )

        val status = runtime.tick(1_000L, RuntimeEnvironment(internetAvailable = true, exchangeHealthy = true))

        assertFalse(status.marketDataFresh)
        assertTrue(status.internetAvailable)
        assertTrue(status.exchangeHealthy)
        assertEquals(0, status.activePositions.size)
    }

    @Test
    fun unavailableExchangeIsReportedUnhealthyAndDoesNotOpen() {
        val runtime = MireiPaperTradingRuntime(
            marketData = object : PaperMarketDataSource {
                override fun snapshot(symbol: String) = MarketSnapshot(symbol, 10_000.0, 1.0, 0.5, 0.0, 0.65, true)
            },
            symbol = "BTC/IDR",
        )

        val status = runtime.tick(2_000L, RuntimeEnvironment(internetAvailable = true, exchangeHealthy = false))

        assertFalse(status.exchangeHealthy)
        assertTrue(status.internetAvailable)
        assertEquals(0, status.activePositions.size)
    }

    @Test
    fun missingMarketDataIsReportedUnhealthy() {
        val runtime = MireiPaperTradingRuntime(
            marketData = object : PaperMarketDataSource {
                override fun snapshot(symbol: String): MarketSnapshot? = null
            },
            symbol = "BTC/IDR",
        )

        val status = runtime.tick(3_000L, RuntimeEnvironment(internetAvailable = true, exchangeHealthy = true))

        assertFalse(status.exchangeHealthy)
        assertEquals("market_data_unavailable", status.lastError)
        assertEquals(0, status.activePositions.size)
    }

    @Test
    fun closeAllKeepsPositionsOpenWhenMarketDataCannotBeReconciled() {
        var snapshot: MarketSnapshot? = MarketSnapshot("BTC/IDR", 10_000.0, 1.0, 0.5, 0.0, 0.65, true)
        val engine = PaperExecutionEngine()
        val runtime = MireiPaperTradingRuntime(
            marketData = object : PaperMarketDataSource {
                override fun snapshot(symbol: String): MarketSnapshot? = snapshot
            },
            symbol = "BTC/IDR",
            engine = engine,
        )

        engine.open(
            "paper",
            "BTC/IDR",
            EntryPlan(true, 10_000.0, 9_900.0, 10_200.0, 10_100.0, 10_000.0, listOf("test")),
            4_000L,
        )
        snapshot = null

        val status = runtime.closeAll(5_000L, RuntimeEnvironment(internetAvailable = true, exchangeHealthy = true))

        assertEquals(1, status.activePositions.size)
        assertFalse(status.exchangeHealthy)
        assertEquals("close_all_market_data_unavailable", status.lastError)
    }
}
