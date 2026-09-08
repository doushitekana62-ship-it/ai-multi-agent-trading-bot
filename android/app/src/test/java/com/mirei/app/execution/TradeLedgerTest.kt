package com.mirei.app.execution

import com.mirei.app.core.EntryPlan
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TradeLedgerTest {
    @Test
    fun recordsOpenAndCloseLifecycle() {
        val events = mutableListOf<String>()
        val ledger = object : TradeLedger {
            override fun recordOpened(position: PaperPosition, entryFeeIdr: Double) {
                events += "open:${position.id}:$entryFeeIdr"
            }

            override fun recordClosed(
                position: PaperPosition,
                exitPrice: Double,
                feeIdr: Double,
                pnlIdr: Double,
                closedAtEpochMs: Long,
                exitReason: String,
            ) {
                events += "close:${position.id}:$exitPrice:$feeIdr:$pnlIdr:$exitReason"
            }
        }
        val plan = EntryPlan(true, 1_000_000.0, 995_000.0, 1_010_000.0, 1_005_000.0, 50_000.0, listOf("test"))
        val engine = PaperExecutionEngine(feePercent = 0.3, slippagePercent = 0.05, tradeLedger = ledger)

        val opened = engine.open("paper", "BTC/IDR", plan, 1000L)
        assertTrue(opened.success)
        val closed = engine.close(opened.orderId!!, 1_010_000.0, "take_profit", 2000L)

        assertTrue(closed.success)
        assertEquals(2, events.size)
        assertTrue(events[0].startsWith("open:paper-1000-1"))
        assertTrue(events[1].contains(":take_profit"))
    }
}
