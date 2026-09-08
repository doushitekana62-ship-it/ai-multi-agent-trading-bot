package com.mirei.app.runtime

import com.mirei.app.core.MarketSnapshot
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
}
