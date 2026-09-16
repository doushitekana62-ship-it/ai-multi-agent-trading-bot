package com.mirei.app.runtime

import com.mirei.app.core.ManualRiskMode
import com.mirei.app.core.ScalpingMode
import com.mirei.app.core.TradingConfig
import com.mirei.app.execution.PaperPosition
import com.mirei.app.execution.TradeLedger
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ManualTakeProfitAuthorityTest {
    @Test fun manualNetTargetIsTheOnlyTpSourceForThePosition() {
        val market = ManualTpMarket(10_000.0)
        val ledger = CountingLedger()
        val config = TradingConfig(mode = ScalpingMode.BALANCED, manualRiskMode = ManualRiskMode.MANUAL, manualStopLossPercent = 0.50, manualNetProfitTargetIdr = 113.0, positionSizeIdr = 50_000.0, maxOpenPositions = 1)
        val runtime = MireiPaperTradingRuntime(config = config, marketData = market, symbol = "BTC/IDR", tradeLedger = ledger)
        val first = runtime.tick(1_000L)
        val opened = first.activePositions.single()
        assertEquals(com.mirei.app.core.TakeProfitMode.MANUAL_NET_IDR, opened.takeProfitMode)
        assertEquals(113.0, opened.manualNetProfitTargetIdr!!, 0.0001)
        val targetNet = runtime.paperEngine().unrealizedNetPnl(opened.id, opened.takeProfitPrice)!!
        assertTrue("manual TP price must realize at least the configured net target", targetNet >= 112.99)
        market.price = opened.takeProfitPrice - 0.01
        val below = runtime.tick(2_000L)
        assertEquals(1, below.activePositions.size)
        assertEquals(0, ledger.closedCount)
        market.price = opened.takeProfitPrice
        val hit = runtime.tick(3_000L)
        assertEquals(0, hit.activePositions.size)
        assertEquals(1, ledger.closedCount)
        assertTrue(hit.recentExecutions.any { it.reason == "take_profit" })
        val blocked = runtime.tick(4_000L)
        assertEquals(0, blocked.activePositions.size)
        market.price = opened.entryPrice
        val reentry = runtime.tick(5_000L)
        assertEquals(1, reentry.activePositions.size)
        assertEquals(5_000L, reentry.activePositions.single().openedAtEpochMs)
        assertEquals(com.mirei.app.core.TakeProfitMode.MANUAL_NET_IDR, reentry.activePositions.single().takeProfitMode)
        assertEquals(113.0, reentry.activePositions.single().manualNetProfitTargetIdr!!, 0.0001)
    }
}

private class ManualTpMarket(var price: Double) : PaperMarketDataSource { override fun snapshot(symbol: String) = MarketSnapshotFactory.bullish(symbol, price) }
private object MarketSnapshotFactory { fun bullish(symbol: String, price: Double) = com.mirei.app.core.MarketSnapshot(symbol = symbol, price = price, momentumPercent = 1.0, volatilityPercent = 0.5, sentimentScore = 10.0, forecastConfidence = 0.90, dataFresh = true, changeSinceLastTickPercent = 0.20, change1mPercent = 0.20, change5mPercent = 0.40, change15mPercent = 0.60, tradeFlowPercent = 20.0, trendScorePercent = 5.0) }
private class CountingLedger : TradeLedger { var closedCount = 0; override fun recordOpened(position: PaperPosition, entryFeeIdr: Double) = Unit; override fun recordClosed(position: PaperPosition, exitPrice: Double, feeIdr: Double, pnlIdr: Double, closedAtEpochMs: Long, exitReason: String) { closedCount++ } }
