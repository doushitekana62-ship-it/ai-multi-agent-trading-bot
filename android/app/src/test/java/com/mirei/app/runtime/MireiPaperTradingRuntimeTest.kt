package com.mirei.app.runtime

import com.mirei.app.agents.AgentAction
import com.mirei.app.core.MarketSnapshot
import com.mirei.app.core.MireiDecisionEngine
import com.mirei.app.core.ManualRiskMode
import com.mirei.app.core.RiskSnapshot
import com.mirei.app.core.ScalpingMode
import com.mirei.app.core.TradingConfig
import com.mirei.app.execution.PaperPosition
import com.mirei.app.execution.TradeLedger
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
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
        runtime.tick(1_000L); market.price = 10_020.0; runtime.tick(2_000L); market.price = 10_040.0; val third = runtime.tick(3_000L); market.price = 10_120.0; val reentry = runtime.tick(4_000L)
        assertEquals(3, third.activePositions.size); assertEquals(4, ledger.openedCount); assertEquals(1, ledger.closedCount); assertTrue(reentry.recentExecutions.any { it.reason == "take_profit" }); assertTrue(reentry.activePositions.any { it.openedAtEpochMs == 4_000L })
    }

    @Test fun stopLossReentersFromTheLastStopPriceAndKeepsInitialCapitalReference() {
        val market = ScenarioMarket(); val ledger = RecordingLedger()
        val runtime = MireiPaperTradingRuntime(config = TradingConfig(mode = ScalpingMode.AGGRESSIVE, manualRiskMode = ManualRiskMode.MANUAL, manualStopLossPercent = 0.35, manualTakeProfitPercent = 1.0, positionSizeIdr = 50_000.0, maxOpenPositions = 3), marketData = market, symbol = "BTC/IDR", managedSymbols = listOf("BTC/IDR", "ETH/IDR", "SOL/IDR"), tradeLedger = ledger)
        val seeded = runtime.seedInitialHoldings(mapOf("BTC/IDR" to 50_000.0, "ETH/IDR" to 50_000.0, "SOL/IDR" to 50_000.0), 1_000L)
        assertEquals(3, seeded.count { it.success })
        val originalStop = runtime.paperEngine().positions().single { it.symbol == "BTC/IDR" }.stopLossPrice
        market.bearishSymbol = "BTC/IDR"; market.bearishPrice = 9_900.0
        val closeAndReentry = runtime.tick(2_000L)
        assertTrue(closeAndReentry.recentExecutions.any { it.reason == "stop_loss" })
        val btc = closeAndReentry.activePositions.single { it.symbol == "BTC/IDR" }
        assertEquals(3, closeAndReentry.activePositions.size)
        assertEquals(4, ledger.openedCount)
        assertEquals("sl_re_entry", btc.entryReason)
        assertEquals(50_000.0, btc.riskReferenceCapitalIdr, 0.001)
        assertEquals(originalStop * 1.0005, btc.entryPrice, originalStop * 0.00001)
        assertTrue(closeAndReentry.recentExecutions.any { it.reason == "sl_re_entry" })
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

    @Test fun initialHoldingCannotBeClosedByTheFirstAiDecisionTick() {
        val market = MutableMarket(10_000.0); val ledger = RecordingLedger(); val runtime = MireiPaperTradingRuntime(config = TradingConfig(maxOpenPositions = 3), marketData = market, symbol = "BTC/IDR", tradeLedger = ledger)
        val seed = runtime.seedInitialHoldings(mapOf("BTC/IDR" to 50_000.0), 1_000L).single(); assertTrue(seed.success)
        val first = runtime.tick(9_999L)
        assertTrue(first.activePositions.any { it.entryReason == "initial_holding" })
        assertEquals(0, ledger.closedCount)
    }

    @Test fun initialHoldingAiCloseIsDeferredForProtectionAndExplained() {
        val market = ScenarioMarket(); val ledger = RecordingLedger(); val runtime = MireiPaperTradingRuntime(config = TradingConfig(maxOpenPositions = 3), marketData = market, symbol = "BTC/IDR", managedSymbols = listOf("BTC/IDR"), tradeLedger = ledger)
        val seed = runtime.seedInitialHoldings(mapOf("BTC/IDR" to 50_000.0), 1_000L).single(); assertTrue(seed.success)
        market.bearishSymbol = "BTC/IDR"
        val status = runtime.tick(2_000L)
        assertTrue(status.lastDecision!!.action == AgentAction.CLOSE)
        assertTrue(status.lastDecision!!.rationale.contains("initial_holding_protected_by_tp_sl"))
        assertTrue(status.entryPlanReasons.any { it == "ai_close_waiting_initial_holding_tp_sl" })
        assertTrue(status.activePositions.any { it.entryReason == "initial_holding" })
        assertEquals(0, ledger.closedCount)
    }

    @Test fun nonInitialAiCloseIsDeferredUntilMinimumHoldTimeAndExplained() {
        val market = ScenarioMarket(); val ledger = RecordingLedger(); val runtime = MireiPaperTradingRuntime(config = TradingConfig(maxOpenPositions = 3), marketData = market, symbol = "BTC/IDR", managedSymbols = listOf("BTC/IDR"), tradeLedger = ledger)
        val opened = runtime.tick(1_000L).activePositions.single()
        market.bearishSymbol = "BTC/IDR"
        val deferred = runtime.tick(opened.openedAtEpochMs + 30_000L)
        assertTrue(deferred.lastDecision!!.action == AgentAction.CLOSE)
        assertTrue(deferred.lastDecision!!.rationale.contains("ai_close_deferred_min_hold_60s"))
        assertTrue(deferred.entryPlanReasons.any { it == "ai_close_waiting_min_hold_60s" })
        assertTrue(deferred.activePositions.any { it.id == opened.id })
        assertEquals(0, ledger.closedCount)
    }

    @Test fun takeProfitAfterSeedKeepsRuntimeAvailableForReentry() {
        val market = MutableMarket(10_000.0); val ledger = RecordingLedger(); val runtime = MireiPaperTradingRuntime(config = TradingConfig(maxOpenPositions = 3), marketData = market, symbol = "BTC/IDR", managedSymbols = listOf("BTC/IDR"), tradeLedger = ledger)
        val seed = runtime.seedInitialHoldings(mapOf("BTC/IDR" to 150_000.0), 1_000L).single(); assertTrue(seed.success); val position = runtime.paperEngine().positions().single(); market.price = position.takeProfitPrice * 1.01
        val status = runtime.tick(2_000L)
        assertEquals(1, status.activePositions.size); assertEquals(1, ledger.closedCount); assertEquals(2_000L, status.activePositions.single().openedAtEpochMs); assertTrue(status.dailyPnlIdr != 0.0)
    }

    @Test fun riskProfilesProduceDifferentTargetsAndManualOverridesWin() {
        val snapshot = sampleBullishSnapshot(); val risk = RiskSnapshot(0.0, 150_000.0, 150_000.0, 0, 0, true, true, true)
        val aggressive = MireiDecisionEngine(TradingConfig(mode = ScalpingMode.AGGRESSIVE)).buildEntryPlan(snapshot, risk); val balanced = MireiDecisionEngine(TradingConfig(mode = ScalpingMode.BALANCED)).buildEntryPlan(snapshot, risk); val safety = MireiDecisionEngine(TradingConfig(mode = ScalpingMode.SAFETY)).buildEntryPlan(snapshot, risk)
        val manual = TradingConfig(manualRiskMode = ManualRiskMode.MANUAL, manualStopLossPercent = 0.80, manualTakeProfitPercent = 1.80); val manualPlan = MireiDecisionEngine(manual).buildEntryPlan(snapshot, risk)
        assertTrue(aggressive.stopLossPrice > 0.0); assertTrue(aggressive.stopLossPrice > balanced.stopLossPrice); assertTrue(balanced.stopLossPrice > safety.stopLossPrice); assertTrue(aggressive.takeProfitPrice == balanced.takeProfitPrice); assertTrue(balanced.takeProfitPrice < safety.takeProfitPrice)
        assertEquals(0.80, (snapshot.price - manualPlan.stopLossPrice) / snapshot.price * 100.0, 0.0001); assertEquals(1.80, (manualPlan.takeProfitPrice - snapshot.price) / snapshot.price * 100.0, 0.0001)
    }

    @Test fun staleMarketDataDoesNotOpenPosition() {
        val status = MireiPaperTradingRuntime(marketData = MutableMarket(10_000.0, fresh = false), symbol = "BTC/IDR").tick(1_000L)
        assertTrue(status.activePositions.isEmpty()); assertEquals(null, status.lastExecution); assertEquals(listOf("market_snapshot_stale"), status.entryPlanReasons)
    }

    @Test fun conflictingAgentsUseMajorityVoteAndNeverRequireHumanConfirmation() {
        val market = object : PaperMarketDataSource { override fun snapshot(symbol: String) = sampleBullishSnapshot().copy(symbol = symbol, momentumPercent = -0.10, sentimentScore = 10.0, forecastConfidence = 0.65, changeSinceLastTickPercent = -0.10, change1mPercent = -0.10, change5mPercent = -0.10, change15mPercent = -0.10, trendScorePercent = 0.0) }
        val status = MireiPaperTradingRuntime(marketData = market, symbol = "BTC/IDR").tick(1_000L)
        assertTrue(status.activePositions.isEmpty()); assertFalse(status.lastDecision!!.requiresHumanDecision); assertEquals(AgentAction.HOLD, status.lastDecision!!.action); assertEquals("agent_majority_vote", status.lastDecision!!.rationale); assertEquals(listOf("mirei_entry_gates_passed"), status.entryPlanReasons)
    }
}

private fun sampleBullishSnapshot() = MarketSnapshot("BTC/IDR", 10_000.0, 1.0, 0.5, 10.0, 0.90, true, changeSinceLastTickPercent = 0.20, change1mPercent = 0.20, change5mPercent = 0.40, change15mPercent = 0.60, tradeFlowPercent = 20.0, trendScorePercent = 5.0)
private class MutableMarket(var price: Double, private val fresh: Boolean = true) : PaperMarketDataSource { override fun snapshot(symbol: String) = sampleBullishSnapshot().copy(symbol = symbol, price = price, dataFresh = fresh) }
private class ScenarioMarket : PaperMarketDataSource {
    var bearishSymbol: String? = null
    var bearishPrice: Double = 9_990.0
    override fun snapshot(symbol: String): MarketSnapshot = if (bearishSymbol == symbol) sampleBullishSnapshot().copy(symbol = symbol, price = bearishPrice, momentumPercent = -5.0, sentimentScore = -40.0, forecastConfidence = 0.90, changeSinceLastTickPercent = -0.5, change1mPercent = -0.5, change5mPercent = -0.5, change15mPercent = -0.5, tradeFlowPercent = -40.0, trendScorePercent = -5.0) else sampleBullishSnapshot().copy(symbol = symbol, price = 10_000.0, momentumPercent = 5.0, sentimentScore = 20.0, forecastConfidence = 0.90, changeSinceLastTickPercent = 0.5, change1mPercent = 0.5, change5mPercent = 0.5, change15mPercent = 0.5, tradeFlowPercent = 40.0, trendScorePercent = 5.0)
}
private class RecordingLedger : TradeLedger {
    var openedCount = 0; var closedCount = 0
    override fun recordOpened(position: PaperPosition, entryFeeIdr: Double) { openedCount++ }
    override fun recordClosed(position: PaperPosition, exitPrice: Double, feeIdr: Double, pnlIdr: Double, closedAtEpochMs: Long, exitReason: String) { closedCount++ }
}
