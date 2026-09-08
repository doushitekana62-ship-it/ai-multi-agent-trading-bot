package com.mirei.app.execution

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ExecutionSafetyTest {
    @Test
    fun orderLifecycleRejectsTerminalStateChanges() {
        assertTrue(OrderLifecycle.canTransition(null, OrderStatus.SUBMITTED))
        assertTrue(OrderLifecycle.canTransition(OrderStatus.SUBMITTED, OrderStatus.ACKNOWLEDGED))
        assertTrue(OrderLifecycle.canTransition(OrderStatus.ACKNOWLEDGED, OrderStatus.PARTIALLY_FILLED))
        assertTrue(OrderLifecycle.canTransition(OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED))
        assertFalse(OrderLifecycle.canTransition(OrderStatus.FILLED, OrderStatus.CANCELLED))
        assertFalse(OrderLifecycle.canTransition(OrderStatus.REJECTED, OrderStatus.FILLED))
    }

    @Test
    fun orderLifecycleAllowsExchangeUncertainty() {
        assertTrue(OrderLifecycle.canTransition(OrderStatus.ACKNOWLEDGED, OrderStatus.UNKNOWN))
        assertTrue(OrderLifecycle.canTransition(OrderStatus.PARTIALLY_FILLED, OrderStatus.TIMEOUT))
        assertTrue(NormalizedOrder(symbol = "BTC/IDR", status = OrderStatus.FILLED, updatedAtEpochMs = 1L).isTerminal())
        assertFalse(NormalizedOrder(symbol = "BTC/IDR", status = OrderStatus.UNKNOWN, updatedAtEpochMs = 1L).isTerminal())
    }

    @Test
    fun reconciliationFindsInternalOnlyPosition() {
        val issues = PositionReconciler.compare(
            internal = listOf(InternalPositionSnapshot("p1", "BTC/IDR", 0.01)),
            exchange = emptyList(),
        )

        assertFalse(PositionReconciler.isSafeToContinue(issues))
        assertTrue(issues.single().status == ReconciliationStatus.INTERNAL_ONLY)
    }

    @Test
    fun reconciliationFindsExchangeOnlyPosition() {
        val issues = PositionReconciler.compare(
            internal = emptyList(),
            exchange = listOf(ExchangePositionSnapshot("p1", "BTC/IDR", 0.01)),
        )

        assertFalse(PositionReconciler.isSafeToContinue(issues))
        assertTrue(issues.single().status == ReconciliationStatus.EXCHANGE_ONLY)
    }

    @Test
    fun reconciliationFindsSizeAndStatusMismatch() {
        val issues = PositionReconciler.compare(
            internal = listOf(InternalPositionSnapshot("p1", "BTC/IDR", 0.01, "OPEN")),
            exchange = listOf(ExchangePositionSnapshot("p1", "BTC/IDR", 0.02, "CLOSED")),
        )

        assertFalse(PositionReconciler.isSafeToContinue(issues))
        assertTrue(issues.single().status == ReconciliationStatus.STATUS_MISMATCH)
    }

    @Test
    fun reconciliationAcceptsMatchingPositions() {
        val issues = PositionReconciler.compare(
            internal = listOf(InternalPositionSnapshot("p1", "BTC/IDR", 0.01)),
            exchange = listOf(ExchangePositionSnapshot("p1", "BTC/IDR", 0.01)),
        )

        assertTrue(issues.isEmpty())
        assertTrue(PositionReconciler.isSafeToContinue(issues))
    }
}
