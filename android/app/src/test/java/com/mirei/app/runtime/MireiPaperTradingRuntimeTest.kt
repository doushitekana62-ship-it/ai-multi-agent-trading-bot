package com.mirei.app.runtime

import com.mirei.app.core.MarketSnapshot
import com.mirei.app.core.MireiDecisionEngine
import com.mirei.app.core.ManualRiskMode
import com.mirei.app.core.RiskSnapshot
import com.mirei.app.core.ScalpingMode
import com.mirei.app.core.TradingConfig
import com.mirei.app.execution.PaperPosition
import com.mirei.app.execution.TradeLedger
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class MireiPaperTradingRuntimeTest {
    @Test fun healthyPaperTickCreatesPositionThroughAgentsAndDecisionEngine() {
        val runtime = MireiPaperTradingRuntime(marketData = MutableMarket(10_000.0), symbol = "BTC/IDR", tradeLedger = RecordingLedger())
        val status = runtime.tick(1_000L)
        assertEquals(1, status.activePositions.size); assertNotNull(status.lastDecision); assertNotNull(status.lastExecution); assertTrue(status.lastExecution!!.success)
    }

    @Test fun takeProfitClosesPositionAndReleasesCapitalForNextEntry() {
        val market = MutableMarket(10_000.0); val ledger = RecordingLedger(); val runtime = MireiPaperTradingRuntime(config = TradingConfig(positionSizeIdr = 50_000.0), marketData = market, symbol = "BTC/IDR", tradeLedger = ledger)
        val first = runtime.tick(1_000L); val position = first.activePositions.single(); market.price = position.takeProfitPrice * 1.01; val second = runtime.tick(2_000L)
        assertEquals(1, second.activePositions.size); assertEquals(1, ledger.closedCount); assertEquals(2_000L, second.activePositions.single().openedAtEpochMs); assertTrue(second.recentExecutions.any { it.reason == "take_profit" }); assertTrue(second.dailyPnlIdr != 0.0)
    }

    @Test fun runtimeUsesAllThreePositionSlotsAndReentersAfterOnePositionCloses() {
        val market = MutableMarket(10_000.0); val ledger = RecordingLedger(); val runtime = MireiPaperTradingRuntime(config = TradingConfig(positionSizeIdr = 50_000.0, maxOpenPositions = 3), marketData = market, symbol = "BTC/IDR", tradeLedger = ledger)
        runtime.tick(1_000L); market.price = 10_020.0; runtime.tick(2_000L); market.price = 10_040.0; val third = runtime.tick(3_000L); market.price = 10_060.0; val reentry = runtime.tick(4_000L)
        assertEquals(3, third.activePositions.size); assertEquals(4, ledger.openedCount); assertEquals(1, ledger.closedCount); assertEquals(1, reentry.recentExecutions.count { it.reason == "take_profit" }); assertTrue(reentry.activePositions.any { it.openedAtEpochMs == 4_000L })
    }

    @Test fun stopLossReleasesCapitalAndNextValidSignalIsMarkedReEntry() {
        val market = ScenarioMarket()
        val ledger = RecordingLedger()
        val runtime = MireiPaperTradingRuntime(config = TradingConfig(positionSizeIdr = 50_000.0), marketData = market, symbol = "BTC/IDR", tradeLedger = ledger)
        val seeded = runtime.seedInitialHoldings(mapOf("BTC/IDR" to 50_000.0), 1_000L).single()
        assertTrue(seeded.success)

        market.bearish = true
        val close = runtime.tick(2_000L)
        assertTrue(close.activePositions.isEmpty())
        assertTrue(close.recentExecutions.any { it.reason == "stop_loss" })
        assertEquals(1, ledger.closedCount)
        assertTrue(runtime.paperEngine().availableBalanceIdr() > 0.0)

        market.bearish = false
        val reentry = runtime.tick(3_000L)
        assertEquals(1, reentry.activePositions.size)
        assertEquals("re_entry", reentry.activePositions.single().entryReason)
        assertTrue(reentry.recentExecutions.any { it.reason == "re_entry" })
        assertTrue(reentry.activePositions.single().openedAtEpochMs == 3_000L)
    }

    @Test fun positionCapPreventsFourthConcurrentEntry() {
        val market = MutableMarket(10_000.0); val ledger = RecordingLedger(); val runtime = MireiPaperTradingRuntime(config = TradingConfig(positionSizeIdr = 30_000.0, maxOpenPositions = 3), marketData = market, symbol = "BTC/IDR", tradeLedger = ledger)
        runtime.tick(1_000L); runtime.tick(2_000L); val third = runtime.tick(3_000L); val capped = runtime.tick(4_000L)
        assertEquals(3, third.activePositions.size); assertEquals(3, capped.activePositions.size); assertEquals(3, ledger.openedCount)
    }

    @Test fun initialHoldingsArePortfolioStateAndConsumeStartingCapitalWithoutAgentBuy() {
        val market = MutableMarket(10_000.0); val ledger = RecordingLedger(); val runtime = MireiPaperTradingRuntime(config = TradingConfig(maxOpenPositions = 3), marketData = market, symbol = "BTC/IDR", managedSymbols = listOf("BTC/IDR", "ETH/IDR", "SOL/IDR"), tradeLedger = ledger)
        val seeded = runtime.seedInitialHoldings(mapOf("BTC/IDR" to 60_000.0, "ETH/IDR" to 50_000.0, "SOL/IDR" to 40_000.0), 1_000L)
        assertEquals(3, seeded.count { it.success }); assertEquals(3, runtime.paperEngine().positionCount()); assertEquals(0.0, runtime.paperEngine().availableBalanceIdr(), 0.001); assertTrue(seeded.all { it.reason == "initial_holding_seeded" })
    }

    @Test fun takeProfitAfterSeedKeepsRuntimeAvailableForReentry() {
        val market = MutableMarket(10_000.0); val ledger = RecordingLedger(); val runtime = MireiPaperTradingRuntime(config = TradingConfig(maxOpenPositions = 3), marketData = market, symbol = "BTC/IDR", managedSymbols = listOf("BTC/IDR"), tradeLedger = ledger)
        val seed = runtime.seedInitialHoldings(mapOf("BTC/IDR" to 150_000.0), 1_000L).single(); assertTrue(seed.success); val position = runtime.paperEngine().positions().single(); market.price = position.takeProfitPrice * 1.01
        val status = runtime.tick(2_000L)
        assertEquals(1, status.activePositions.size); assertEquals(1, ledger.closedCount); assertEquals(2_000L, status.activePositions.single().openedAtEpochMs); assertTrue(status.dailyPnlIdr != 0.0)
    }

    @Test fun riskProfilesProduceDifferentTargetsAndManualOverridesWin() {
        val snapshot = sampleBullishSnapshot(); val risk = RiskSnapshot(0.0, 150_000.0, 150_000.0, 0, 0, true, true, true)
        val aggressive = MireiDecisionEngine(TradingConfig(mode = ScalpingMode.AGGRESSIVE)).buildEntryPlan(snapshot, risk)
        val balanced = MireiDecisionEngine(TradingConfig(mode = ScalpingMode.BALANCED)).buildEntryPlan(snapshot, risk)
        val safety = MireiDecisionEngine(TradingConfig(mode = ScalpingMode.SAFETY)).buildEntryPlan(snapshot, risk)
        assertTrue(aggressive.allowed); assertTrue(balanced.allowed); assertTrue(safety.allowed)
        assertTrue(aggressive.takeProfitPrice < balanced.takeProfitPrice); assertTrue(balanced.takeProfitPrice < safety.takeProfitPrice)
        val manual = MireiDecisionEngine(TradingConfig(manualRiskMode = ManualRiskMode.MANUAL, manualStopLossPercent = 0.30, manualTakeProfitPercent = 0.90)).buildEntryPlan(snapshot, risk)
        assertEquals(0.30, (snapshot.price - manual.stopLossPrice) / snapshot.price * 100.0, 0.0001)
        assertEquals(0.90, (manual.takeProfitPrice - snapshot.price) / snapshot.price * 100.0, 0.0001)
    }

    @Test fun staleMarketDoesNotOpenPosition() {
        val runtime = MireiPaperTradingRuntime(marketData = MutableMarket(10_000.0, fresh = false), symbol = "BTC/IDR")
        val status = runtime.tick(1_000L)
        assertTrue(status.activePositions.isEmpty())
        assertTrue(status.entryPlanReasons.contains("market_snapshot_stale"))
    }

    @Test fun suggestionConflictRequiresHumanDecision() {
        val runtime = MireiPaperTradingRuntime(marketData = ConflictingMarket(), symbol = "BTC/IDR")
        val status = runtime.tick(1_000L)
        assertTrue(status.humanVerificationRequired)
        assertTrue(status.activePositions.isEmpty())
    }

    @Test fun manualRiskModeChangesTargets() {
        val runtime = MireiPaperTradingRuntime(config = TradingConfig(manualRiskMode = ManualRiskMode.MANUAL, manualStopLossPercent = 0.40, manualTakeProfitPercent = 0.80), marketData = MutableMarket(10_000.0), symbol = "BTC/IDR")
        val status = runtime.tick(1_000L)
        val position = status.activePositions.single()
        assertTrue(position.takeProfitPrice > position.entryPrice)
        assertTrue(position.stopLossPrice < position.entryPrice)
    }

    private fun sampleBullishSnapshot() = MarketSnapshot("BTC/IDR", 1_000_000.0, 0.8, 0.5, 20.0, 0.9, true)

    private class MutableMarket(var price: Double, private val fresh: Boolean = true) : PaperMarketDataSource {
        override fun snapshot(symbol: String): MarketSnapshot = MarketSnapshot(symbol, price, 0.8, 0.5, 20.0, 0.9, fresh)
    }

    private class ScenarioMarket : PaperMarketDataSource {
        var bearish = false
        override fun snapshot(symbol: String): MarketSnapshot = if (bearish) MarketSnapshot(symbol, 9_940.0, -1.2, 0.5, -10.0, 0.9, true) else MarketSnapshot(symbol, 10_020.0, 1.2, 0.5, 30.0, 0.9, true)
    }

    private class ConflictingMarket : PaperMarketDataSource {
        override fun snapshot(symbol: String): MarketSnapshot = MarketSnapshot(symbol, 10_000.0, 0.8, 0.5, 0.0, 0.9, true)
    }

    private class RecordingLedger : TradeLedger {
        var openedCount = 0
        var closedCount = 0
        override fun recordOpened(position: PaperPosition, entryFeeIdr: Double) { openedCount++ }
        override fun recordClosed(position: PaperPosition, exitPrice: Double, totalFeeIdr: Double, pnlIdr: Double, closedAtEpochMs: Long, reason: String) { closedCount++ }
    }
}
