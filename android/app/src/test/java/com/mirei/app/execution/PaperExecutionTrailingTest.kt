package com.mirei.app.execution

import com.mirei.app.core.EntryPlan
import com.mirei.app.core.TradingConfig
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class PaperExecutionTrailingTest {
    @Test
    fun trailingStopOnlyTightensExistingPosition() {
        val engine = PaperExecutionEngine(TradingConfig())
        val plan = EntryPlan(
            allowed = true,
            entryPrice = 100.0,
            stopLossPrice = 99.5,
            takeProfitPrice = 101.0,
            trailingActivationPrice = 100.5,
            stakeIdr = 50_000.0,
            reasons = listOf("test"),
        )
        val opened = engine.open("indodax", "BTC/IDR", plan, 1_000L)
        assertTrue(opened.success)
        val id = opened.orderId!!
        val original = engine.position(id)!!.stopLossPrice

        assertTrue(engine.updateTrailingStop(id, original + 0.2))
        val tightened = engine.position(id)!!.stopLossPrice
        assertTrue(tightened > original)

        assertEquals(false, engine.updateTrailingStop(id, tightened - 0.1))
        assertEquals(tightened, engine.position(id)!!.stopLossPrice)
    }
}
