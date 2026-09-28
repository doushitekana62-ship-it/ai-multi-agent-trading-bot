package com.mirei.app.execution

import com.mirei.app.core.EntryPlan
import com.mirei.app.core.TradingConfig
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PaperExecutionEnginePhase1Test {
    private fun plan(price: Double, stake: Double) = EntryPlan(true, price, 0.0, price * 1.1, 0.0, stake, listOf("test"))

    @Test fun reentryCooldownOnlyBlocksDuplicateBuy() {
        val engine = PaperExecutionEngine(TradingConfig(totalCapitalIdr = 100_000.0, positionSizeIdr = 50_000.0))
        val first = engine.open("indodax", "BTC/IDR", plan(100.0, 50_000.0), 1_000L, "entry_filled")
        assertTrue(first.success)
        val close = engine.close(first.orderId!!, 100.0, "take_profit", 2_000L)
        assertTrue(close.success)
        val blocked = engine.open("indodax", "BTC/IDR", plan(100.0, 50_000.0), 2_500L, "re_entry")
        assertFalse(blocked.success)
        assertEquals("reentry_cooldown_hold", blocked.error)
        val allowed = engine.open("indodax", "BTC/IDR", plan(200.0, 50_000.0), 3_001L, "re_entry")
        assertTrue(allowed.success)
    }

    @Test fun insufficientReentryBalanceDoesNotPartiallySizeOrder() {
        val config = TradingConfig(totalCapitalIdr = 40_000.0, positionSizeIdr = 25_000.0, maxOpenPositions = 10)
        val engine = PaperExecutionEngine(config)
        val first = engine.open("indodax", "BTC/IDR", plan(100.0, 25_000.0), 1_000L, "entry_filled")
        val second = engine.open("indodax", "ETH/IDR", plan(100.0, 10_000.0), 1_100L, "entry_filled")
        assertTrue(first.success); assertTrue(second.success)
        val closed = engine.close(second.orderId!!, 100.0, "take_profit", 2_000L)
        assertTrue(closed.success)
        val balanceBeforeReentry = engine.availableBalanceIdr()
        val result = engine.open("indodax", "BTC/IDR", plan(200.0, 25_000.0), 3_500L, "re_entry")
        assertFalse(result.success)
        assertEquals("insufficient_reentry_balance_wait", result.error)
        assertEquals(balanceBeforeReentry, engine.availableBalanceIdr(), 0.01)
    }
}