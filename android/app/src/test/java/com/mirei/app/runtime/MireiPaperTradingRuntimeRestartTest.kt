package com.mirei.app.runtime

import com.mirei.app.core.MarketSnapshot
import com.mirei.app.core.TradingConfig
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MireiPaperTradingRuntimeRestartTest {
    @Test
    fun restoredPortfolioSurvivesStopAndStart() {
        val market = RestartMarket()
        val first = MireiPaperTradingRuntime(
            config = TradingConfig(positionSizeIdr = 50_000.0),
            marketData = market,
            symbol = "BTC/IDR",
        )
        val started = first.tick(1_000L)
        assertEquals(1, started.activePositions.size)

        val persisted = first.persistenceState()
        val resumed = MireiPaperTradingRuntime(
            config = TradingConfig(positionSizeIdr = 50_000.0),
            marketData = market,
            symbol = "BTC/IDR",
        )
        resumed.restoreState(persisted)

        val afterRestart = resumed.tick(2_000L)
        assertEquals("STOP/START must preserve the open paper position", 1, afterRestart.activePositions.size)
        assertEquals(started.activePositions.single().id, afterRestart.activePositions.single().id)
    }

    @Test
    fun restartedEmptyPortfolioCanOpenWhenBuyGateIsValid() {
        val market = RestartMarket()
        val first = MireiPaperTradingRuntime(
            config = TradingConfig(positionSizeIdr = 50_000.0),
            marketData = market,
            symbol = "BTC/IDR",
        )
        val started = first.tick(1_000L)
        val original = started.activePositions.single()
        val closed = first.paperEngine().close(original.id, 9_900.0, "stop_loss", 1_500L)
        assertTrue(closed.success)

        val persistedEmpty = first.persistenceState()
        assertTrue(persistedEmpty.engineState.positions.isEmpty())

        val resumed = MireiPaperTradingRuntime(
            config = TradingConfig(positionSizeIdr = 50_000.0),
            marketData = market,
            symbol = "BTC/IDR",
        )
        resumed.restoreState(persistedEmpty)
        val afterRestart = resumed.tick(2_000L)

        assertTrue("A valid BUY after STOP/START must be allowed to create a new paper position", afterRestart.activePositions.isNotEmpty())
        assertTrue(afterRestart.lastExecution?.success == true)
    }
}

private class RestartMarket : PaperMarketDataSource {
    override fun snapshot(symbol: String): MarketSnapshot = MarketSnapshot(
        symbol = symbol,
        price = 10_000.0,
        momentumPercent = 5.0,
        volatilityPercent = 0.5,
        sentimentScore = 20.0,
        forecastConfidence = 0.90,
        dataFresh = true,
        changeSinceLastTickPercent = 0.5,
        change1mPercent = 0.5,
        change5mPercent = 0.5,
        change15mPercent = 0.5,
        tradeFlowPercent = 40.0,
        trendScorePercent = 5.0,
    )
}
