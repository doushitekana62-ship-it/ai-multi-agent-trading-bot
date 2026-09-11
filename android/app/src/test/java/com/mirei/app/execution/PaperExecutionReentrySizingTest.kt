package com.mirei.app.execution

import com.mirei.app.core.EntryPlan
import com.mirei.app.core.RiskReferenceMode
import com.mirei.app.core.TradingConfig
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class PaperExecutionReentrySizingTest {
    @Test
    fun reentryUsesRemainingCashInsteadOfWaitingForLossRecovery() {
        val config = TradingConfig(totalCapitalIdr = 50_000.0, positionSizeIdr = 50_000.0)
        val engine = PaperExecutionEngine(config, feePercent = 0.3, slippagePercent = 0.0)

        val initial = engine.seedExistingHolding(
            exchangeId = "indodax",
            symbol = "BTC/IDR",
            quoteAmount = 50_000.0,
            marketPrice = 100_000.0,
            stopLossPercent = 0.5,
            takeProfitPercent = 1.0,
            nowMs = 1L,
            riskReferenceMode = RiskReferenceMode.INITIAL_CAPITAL,
            initialCapitalIdr = 50_000.0,
        )
        assertTrue(initial.success)

        val closed = engine.close(initial.orderId!!, 99_400.0, "stop_loss", 2L)
        assertTrue(closed.success)
        assertTrue(closed.remainingBalanceIdr < 50_000.0)

        val requested = EntryPlan(
            allowed = true,
            entryPrice = 100_000.0,
            stopLossPrice = 99_500.0,
            takeProfitPrice = 101_000.0,
            trailingActivationPrice = 100_500.0,
            stakeIdr = 50_000.0,
            reasons = listOf("mirei_entry_gates_passed"),
            riskReferenceMode = RiskReferenceMode.INITIAL_CAPITAL,
            riskReferenceCapitalIdr = 50_000.0,
        )
        val reopened = engine.open("indodax", "BTC/IDR", requested, 3L, "re_entry")

        assertTrue(reopened.success)
        assertEquals(closed.remainingBalanceIdr, reopened.balanceBeforeIdr, 1e-6)
        assertEquals(closed.remainingBalanceIdr, engine.positions().single().stakeIdr, 1e-6)
        assertEquals("re_entry", engine.positions().single().entryReason)
        assertEquals(50_000.0, engine.positions().single().riskReferenceCapitalIdr, 1e-6)
    }
}
