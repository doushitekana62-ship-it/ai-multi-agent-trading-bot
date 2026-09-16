package com.mirei.app.execution

import com.mirei.app.core.EntryPlan
import com.mirei.app.core.RiskReferenceMode
import com.mirei.app.core.TradingConfig
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class PaperExecutionReentrySizingTest {
    @Test fun reentryUsesRemainingCashInsteadOfWaitingForLossRecovery() {
        val config = TradingConfig(totalCapitalIdr = 50_000.0, positionSizeIdr = 50_000.0)
        val engine = PaperExecutionEngine(config, feePercent = 0.3, slippagePercent = 0.0)
        val initial = engine.seedExistingHolding("indodax", "BTC/IDR", 50_000.0, 100_000.0, 0.5, 1.0, 1L, RiskReferenceMode.INITIAL_CAPITAL, 50_000.0)
        assertTrue(initial.success)
        val closed = engine.close(initial.orderId!!, 99_400.0, "stop_loss", 2L)
        assertTrue(closed.success)
        assertTrue(closed.remainingBalanceIdr < 50_000.0)
        val requested = EntryPlan(true, 100_000.0, 99_500.0, 101_000.0, 100_500.0, 50_000.0, listOf("mirei_entry_gates_passed"), RiskReferenceMode.INITIAL_CAPITAL, 50_000.0)
        val blocked = engine.open("indodax", "BTC/IDR", requested, 3L, "re_entry")
        assertTrue(!blocked.success)
        assertEquals("reentry_cooldown_hold", blocked.reason)
        val reopened = engine.open("indodax", "BTC/IDR", requested, 1_003L, "re_entry")
        assertTrue(reopened.success)
        assertEquals(closed.remainingBalanceIdr, reopened.balanceBeforeIdr, 1e-6)
        assertEquals(closed.remainingBalanceIdr, engine.positions().single().stakeIdr, 1e-6)
        assertEquals("re_entry", engine.positions().single().entryReason)
        assertEquals(50_000.0, engine.positions().single().riskReferenceCapitalIdr, 1e-6)
    }
}
