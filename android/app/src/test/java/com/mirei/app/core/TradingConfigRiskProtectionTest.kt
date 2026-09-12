package com.mirei.app.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TradingConfigRiskProtectionTest {
    @Test
    fun everyAutomaticScalpingModeHasExplicitStopLoss() {
        val aggressive = TradingConfig(mode = ScalpingMode.AGGRESSIVE)
        val balanced = TradingConfig(mode = ScalpingMode.BALANCED)
        val safety = TradingConfig(mode = ScalpingMode.SAFETY)

        assertEquals(0.40, aggressive.effectiveStopLossPercent(), 1e-9)
        assertEquals(0.50, balanced.effectiveStopLossPercent(), 1e-9)
        assertEquals(0.65, safety.effectiveStopLossPercent(), 1e-9)
    }

    @Test
    fun calculatedTargetsAlwaysContainStopAndTakeProfit() {
        listOf(ScalpingMode.AGGRESSIVE, ScalpingMode.BALANCED, ScalpingMode.SAFETY).forEach { mode ->
            val config = TradingConfig(mode = mode)
            val targets = config.calculateRiskTargets(100_000.0, 50_000.0)
            assertTrue(targets.stopLossPrice > 0.0)
            assertTrue(targets.stopLossPrice < 100_000.0)
            assertTrue(targets.takeProfitPrice > 100_000.0)
        }
    }

    // CI trigger marker: validate the canonical main risk/runtime source state.
}
