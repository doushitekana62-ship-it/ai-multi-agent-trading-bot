package com.mirei.app.execution

import com.mirei.app.core.EntryPlan
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class PaperExecutionEngineTest {
    private val plan = EntryPlan(
        allowed = true,
        entryPrice = 1_000_000.0,
        stopLossPrice = 995_000.0,
        takeProfitPrice = 1_010_000.0,
        trailingActivationPrice = 1_005_000.0,
        stakeIdr = 50_000.0,
        reasons = listOf("test"),
    )

    @Test
    fun openAndCloseCalculatesNetPnl() {
        val engine = PaperExecutionEngine(feePercent = 0.3, slippagePercent = 0.05)
        val opened = engine.open("paper-exchange", "BTC/IDR", plan, 1000L)
        assertTrue(opened.success)
        assertEquals(1, engine.positionCount())

        val closed = engine.close(opened.orderId!!, 1_010_000.0, "take_profit")
        assertTrue(closed.success)
        assertTrue(closed.pnlIdr > 0.0)
        assertEquals(0, engine.positionCount())
    }

    @Test
    fun invalidClosePriceDoesNotRemovePosition() {
        val engine = PaperExecutionEngine()
        val opened = engine.open("paper-exchange", "BTC/IDR", plan, 1000L)
        val closed = engine.close(opened.orderId!!, 0.0, "invalid")

        assertTrue(!closed.success)
        assertEquals(1, engine.positionCount())
    }
}
