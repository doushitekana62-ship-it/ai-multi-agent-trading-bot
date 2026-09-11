package com.mirei.app.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ExitPolicyUnlimitedHoldTest {
    @Test
    fun zeroStopLossNeverActivatesTrailingAndKeepsConfiguredTakeProfit() {
        val config = TradingConfig(mode = ScalpingMode.AGGRESSIVE)
        val plan = ExitPolicy(config).evaluate(
            entryPrice = 100_000.0,
            currentPrice = 101_000.0,
            initialStopLossPrice = 0.0,
            initialTakeProfitPrice = 101_000.0,
            atrPercent = 0.5,
            recentSwingLow = 99_500.0,
        )

        assertEquals(0.0, plan.stopLossPrice, 1e-9)
        assertEquals(101_000.0, plan.takeProfitPrice, 1e-9)
        assertNull(plan.trailingStopPrice)
        assertEquals(0.0, plan.partialCloseFraction, 1e-9)
        assertEquals("unlimited_hold_until_tp_or_manual_close", plan.reason)
    }

    @Test
    fun normalStopStillActivatesAtOneR() {
        val config = TradingConfig(mode = ScalpingMode.BALANCED)
        val plan = ExitPolicy(config).evaluate(
            entryPrice = 100_000.0,
            currentPrice = 100_500.0,
            initialStopLossPrice = 99_500.0,
            initialTakeProfitPrice = 101_000.0,
            atrPercent = 0.2,
            recentSwingLow = 100_200.0,
        )

        assertEquals("trailing_1R", plan.reason)
        assertEquals(100_500.0, plan.stopLossPrice, 1e-9)
        assertEquals(101_000.0, plan.takeProfitPrice, 1e-9)
    }
}
