package com.mirei.app.runtime

import com.mirei.app.core.MarketSnapshot
import com.mirei.app.core.TradingConfig
import com.mirei.app.execution.PaperPosition
import com.mirei.app.execution.TradeLedger
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MireiPaperTradingRuntimeSub50kTest {
    @Test
    fun capitalBelowNormalStake_canSeedAndContinueAfterTakeProfit() {
        val market = SingleMarket(10_000.0)
        val ledger = CountingLedger()
        val runtime = MireiPaperTradingRuntime(
            config = TradingConfig(positionSizeIdr = 50_000.0, maxOpenPositions = 1),
            marketData = market,
            symbol = "BTC/IDR",
            tradeLedger = ledger,
        )

        val seed = runtime.seedInitialHoldings(mapOf("BTC/IDR" to 30_000.0), 1_000L).single()
        assertTrue(seed.success)
        assertEquals(30_000.0, runtime.paperEngine().positions().single().stakeIdr, 0.001)
        assertEquals(120_000.0, runtime.paperEngine().availableBalanceIdr(), 0.001)

        val firstPosition = runtime.paperEngine().positions().single()
        market.price = firstPosition.takeProfitPrice * 1.01
        val afterTp = runtime.tick(2_000L)

        assertEquals(1, ledger.closedCount)
        assertEquals(1, afterTp.activePositions.size)
        assertEquals(2_000L, afterTp.activePositions.single().openedAtEpochMs)
        assertTrue(afterTp.activePositions.single().stakeIdr < 50_000.0)
        assertTrue(afterTp.activePositions.single().stakeIdr > 30_000.0)
        assertTrue(afterTp.availableBalanceIdr >= 0.0)
    }

    private class SingleMarket(var price: Double) : PaperMarketDataSource {
        override fun snapshot(symbol: String): MarketSnapshot = MarketSnapshot(
            symbol = symbol,
            price = price,
            momentumPercent = 1.0,
            volatilityPercent = 0.5,
            sentimentScore = 10.0,
            forecastConfidence = 0.90,
            dataFresh = true,
            changeSinceLastTickPercent = 0.20,
            change1mPercent = 0.20,
            change5mPercent = 0.40,
            change15mPercent = 0.60,
            tradeFlowPercent = 20.0,
            trendScorePercent = 5.0,
        )
    }

    private class CountingLedger : TradeLedger {
        var closedCount = 0
        override fun recordOpened(position: PaperPosition, entryFeeIdr: Double) = Unit
        override fun recordClosed(position: PaperPosition, exitPrice: Double, feeIdr: Double, pnlIdr: Double, closedAtEpochMs: Long, exitReason: String) { closedCount++ }
    }
}
