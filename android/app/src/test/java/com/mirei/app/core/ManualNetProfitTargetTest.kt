package com.mirei.app.core

import com.mirei.app.execution.PaperExecutionEngine
import org.junit.Assert.assertTrue
import org.junit.Test

class ManualNetProfitTargetTest {
    @Test
    fun manualTargetIsNetAfterInstrumentCosts() {
        val config = TradingConfig(totalCapitalIdr = 50_000.0, positionSizeIdr = 50_000.0, maxOpenPositions = 1, manualRiskMode = ManualRiskMode.MANUAL, manualStopLossPercent = 0.5, manualTakeProfitPercent = 1.0, manualNetProfitTargetIdr = 30.0)
        val costs = ExecutionCostProfile.INDODAX_IDR_TAKER
        val targets = config.calculateRiskTargets(1_000_000.0, 50_000.0, 50_000.0, executionCosts = costs)
        val engine = PaperExecutionEngine(config = config, tradeLedger = null, useInstrumentCosts = true)
        val opened = engine.open("indodax", "BTC/IDR", EntryPlan(true, 1_000_000.0, targets.stopLossPrice, targets.takeProfitPrice, 1_005_000.0, 50_000.0, listOf("test")), 1_000L)
        assertTrue(opened.success)
        val closed = engine.close(opened.orderId!!, targets.takeProfitPrice, "take_profit", 70_000L)
        assertTrue(closed.success)
        assertTrue("net pnl should meet Rp30 target within floating-point tolerance, got ${closed.pnlIdr}", closed.pnlIdr >= 29.99)
    }
}
