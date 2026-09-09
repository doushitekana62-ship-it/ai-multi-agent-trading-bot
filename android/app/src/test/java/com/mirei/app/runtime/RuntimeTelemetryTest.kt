package com.mirei.app.runtime

import com.mirei.app.core.MarketSnapshot
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class RuntimeTelemetryTest {
    @Test
    fun healthySnapshotIsReflectedInStatus() {
        val runtime = MireiPaperTradingRuntime(
            marketData = object : PaperMarketDataSource {
                override fun snapshot(symbol: String) = MarketSnapshot(symbol, 12_345.0, 1.0, 0.5, 0.0, 0.65, true)
            },
            symbol = "BTC/IDR",
        )
        val status = runtime.tick(1234L, RuntimeEnvironment(internetAvailable = true, exchangeHealthy = true))
        assertEquals(12_345.0, status.marketPrice, 0.0)
        assertEquals(1234L, status.lastTickEpochMs)
        assertTrue(status.marketDataFresh)
        assertTrue(status.internetAvailable)
        assertTrue(status.exchangeHealthy)
        assertEquals(150_000.0, status.availableBalanceIdr, 0.0)
        assertEquals(150_000.0, status.equityIdr, 0.0)
    }
}
