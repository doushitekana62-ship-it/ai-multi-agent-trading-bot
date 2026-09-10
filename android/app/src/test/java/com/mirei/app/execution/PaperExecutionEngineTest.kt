package com.mirei.app.execution

import com.mirei.app.core.EntryPlan
import com.mirei.app.core.TradingConfig
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

        val closed = engine.close(opened.orderId!!, 1_010_000.0, "take_profit", 2000L)
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

    @Test
    fun ledgerFailureDoesNotCommitOpenState() {
        val ledger = object : TradeLedger {
            override fun recordOpened(position: PaperPosition, entryFeeIdr: Double) { error("ledger_down") }
            override fun recordClosed(position: PaperPosition, exitPrice: Double, feeIdr: Double, pnlIdr: Double, closedAtEpochMs: Long, exitReason: String) = Unit
        }
        val engine = PaperExecutionEngine(tradeLedger = ledger)
        var failed = false
        try { engine.open("paper", "BTC/IDR", plan, 1000L) } catch (_: IllegalStateException) { failed = true }
        assertTrue(failed)
        assertEquals(0, engine.positionCount())
        assertEquals(150_000.0, engine.availableBalanceIdr(), 0.001)
    }

    @Test
    fun ledgerFailureDoesNotCommitCloseState() {
        val ledger = object : TradeLedger {
            override fun recordOpened(position: PaperPosition, entryFeeIdr: Double) = Unit
            override fun recordClosed(position: PaperPosition, exitPrice: Double, feeIdr: Double, pnlIdr: Double, closedAtEpochMs: Long, exitReason: String) { error("ledger_down") }
        }
        val engine = PaperExecutionEngine(tradeLedger = ledger)
        val opened = engine.open("paper", "BTC/IDR", plan, 1000L)
        val balanceBefore = engine.availableBalanceIdr()
        var failed = false
        try { engine.close(opened.orderId!!, 1_010_000.0, "take_profit", 2000L) } catch (_: IllegalStateException) { failed = true }
        assertTrue(failed)
        assertEquals(1, engine.positionCount())
        assertEquals(balanceBefore, engine.availableBalanceIdr(), 0.001)
    }

    @Test
    fun limitOrdersReserveCapitalAndCancellationReleasesIt() {
        val config = TradingConfig(totalCapitalIdr = 150_000.0, positionSizeIdr = 50_000.0, maxOpenPositions = 3)
        val engine = PaperExecutionEngine(config = config)
        val first = engine.placeLimit("paper", "BTC/IDR", 50_000.0, 1_000_000.0, 1000L)
        val second = engine.placeLimit("paper", "ETH/IDR", 50_000.0, 2_000_000.0, 1001L)
        val third = engine.placeLimit("paper", "SOL/IDR", 50_000.0, 3_000_000.0, 1002L)
        val fourth = engine.placeLimit("paper", "XRP/IDR", 50_000.0, 4_000_000.0, 1003L)
        assertTrue(first.success); assertTrue(second.success); assertTrue(third.success); assertTrue(!fourth.success)
        assertEquals(3, engine.pendingLimitOrders().size); assertEquals(0.0, engine.availableBalanceIdr(), 0.001)
        assertTrue(engine.cancelLimit(second.orderId!!)); assertEquals(2, engine.pendingLimitOrders().size); assertEquals(50_000.0, engine.availableBalanceIdr(), 0.001)
    }

    @Test
    fun limitFillConsumesReservationWithoutDoubleCharging() {
        val config = TradingConfig(totalCapitalIdr = 150_000.0, positionSizeIdr = 50_000.0, maxOpenPositions = 3)
        val engine = PaperExecutionEngine(config = config, feePercent = 0.3, slippagePercent = 0.05)
        val order = engine.placeLimit("paper", "BTC/IDR", 50_000.0, 1_000_000.0, 1000L)
        val reservedBalance = engine.availableBalanceIdr()
        val filled = engine.fillLimit(order.orderId!!, 999_000.0, 2000L)
        assertTrue(filled.success); assertEquals(1, engine.positionCount()); assertEquals(0, engine.pendingLimitOrders().size); assertEquals(reservedBalance, engine.availableBalanceIdr(), 0.001)
    }

    @Test
    fun reentryDoesNotRequireRecoveryOfPreviousLossAndUsesUniqueId() {
        val engine = PaperExecutionEngine(config = TradingConfig(positionSizeIdr = 50_000.0), feePercent = 0.0, slippagePercent = 0.0)
        val first = engine.open("paper", "BTC/IDR", plan.copy(entryPrice = 1_000_000.0, stopLossPrice = 999_000.0), 1000L, "entry_filled")
        assertTrue(first.success)
        val closed = engine.close(first.orderId!!, 999_000.0, "stop_loss", 2000L)
        assertTrue(closed.success)
        assertEquals(49_950.0, engine.availableBalanceIdr(), 0.001)
        val reentryPlan = plan.copy(entryPrice = 1_001_000.0, stopLossPrice = 1_000_000.0, takeProfitPrice = 1_011_000.0, stakeIdr = 49_950.0)
        val second = engine.open("paper", "BTC/IDR", reentryPlan, 2000L, "re_entry")
        assertTrue(second.success)
        assertEquals("re_entry", engine.position(second.orderId!!)?.entryReason)
        assertEquals(1, engine.positionCount())
        assertTrue(second.orderId != first.orderId)
    }

    @Test
    fun e2EndToEndThreePositionsCloseAndCompoundBalance() {
        val config = TradingConfig(totalCapitalIdr = 150_000.0, positionSizeIdr = 50_000.0, maxOpenPositions = 3)
        val events = mutableListOf<String>()
        val ledger = object : TradeLedger {
            override fun recordOpened(position: PaperPosition, entryFeeIdr: Double) { events += "OPEN:${position.id}:$entryFeeIdr:${position.entryReason}" }
            override fun recordClosed(position: PaperPosition, exitPrice: Double, feeIdr: Double, pnlIdr: Double, closedAtEpochMs: Long, exitReason: String) { events += "CLOSE:${position.id}:$pnlIdr:$exitReason" }
        }
        val engine = PaperExecutionEngine(config = config, feePercent = 0.3, slippagePercent = 0.05, tradeLedger = ledger)
        val p1 = engine.open("paper", "BTC/IDR", plan, 1000L)
        val p2 = engine.open("paper", "ETH/IDR", plan.copy(entryPrice = 2_000_000.0, stopLossPrice = 1_990_000.0, takeProfitPrice = 2_020_000.0, trailingActivationPrice = 2_010_000.0), 2000L)
        val p3 = engine.open("paper", "SOL/IDR", plan.copy(entryPrice = 3_000_000.0, stopLossPrice = 2_985_000.0, takeProfitPrice = 3_030_000.0, trailingActivationPrice = 3_015_000.0), 3000L)
        val rejected = engine.open("paper", "XRP/IDR", plan.copy(entryPrice = 4_000_000.0), 4000L)
        assertTrue(p1.success && p2.success && p3.success); assertTrue(!rejected.success); assertEquals(3, engine.positionCount()); assertEquals(0.0, engine.availableBalanceIdr(), 0.001)
        val c1 = engine.close(p1.orderId!!, 1_010_000.0, "take_profit", 5000L); assertTrue(c1.success); assertTrue(c1.pnlIdr > 0.0)
        val compoundedStake = engine.availableBalanceIdr(); assertTrue(compoundedStake > config.positionSizeIdr)
        val p4 = engine.open("paper", "XRP/IDR", plan.copy(entryPrice = 4_000_000.0, stopLossPrice = 3_980_000.0, takeProfitPrice = 4_040_000.0, trailingActivationPrice = 4_020_000.0, stakeIdr = compoundedStake), 5500L)
        assertTrue(p4.success); assertEquals(0.0, engine.availableBalanceIdr(), 0.001); assertEquals(3, engine.positionCount())
        val c2 = engine.close(p2.orderId!!, 1_990_000.0, "stop_loss", 6000L); val c3 = engine.close(p3.orderId!!, 3_030_000.0, "take_profit", 7000L); val c4 = engine.close(p4.orderId!!, 4_040_000.0, "take_profit", 8000L)
        assertTrue(c2.success && c3.success && c4.success); assertEquals(0, engine.positionCount()); assertTrue(engine.availableBalanceIdr() > 0.0); assertEquals(8, events.size); assertEquals(4, events.count { it.startsWith("OPEN:") }); assertEquals(4, events.count { it.startsWith("CLOSE:") })
    }
}
