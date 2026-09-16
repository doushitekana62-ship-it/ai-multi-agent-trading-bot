package com.mirei.app.core

import com.mirei.app.execution.PaperExecutionEngine
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ReentryPriceGateTest {
    @Test
    fun reentryOutsideToleranceWaitsAndNearEntryCanFill() {
        val config = TradingConfig(totalCapitalIdr = 50_000.0, positionSizeIdr = 25_000.0, maxOpenPositions = 1, reentryPriceTolerancePercent = 0.35)
        val engine = PaperExecutionEngine(config = config, tradeLedger = null, useInstrumentCosts = true)
        val first = EntryPlan(true, 1_000_000.0, 995_000.0, 1_010_000.0, 1_005_000.0, 25_000.0, listOf("test"))
        val opened = engine.open("indodax", "BTC/IDR", first, 1_000L)
        assertTrue(opened.success)
        val closed = engine.close(opened.orderId!!, 995_000.0, "stop_loss", 3_000L)
        assertTrue(closed.success)

        val far = first.copy(entryPrice = 1_010_000.0, stakeIdr = 20_000.0)
        val farResult = engine.open("indodax", "BTC/IDR", far, 5_000L, "sl_re_entry")
        assertTrue(!farResult.success)
        assertEquals("reentry_price_tolerance_hold", farResult.error)

        val near = first.copy(entryPrice = 1_002_000.0, stakeIdr = 20_000.0)
        val nearResult = engine.open("indodax", "BTC/IDR", near, 6_000L, "sl_re_entry")
        assertTrue(nearResult.success)
    }
}
