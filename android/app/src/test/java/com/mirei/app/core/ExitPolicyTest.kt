package com.mirei.app.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ExitPolicyTest {
    @Test
    fun baselineRiskTargetsMatchMireiRequirement() {
        val config = TradingConfig()
        assertEquals(0.50, config.baseStopLossPercent, 0.000001)
        assertEquals(1.00, config.baseTakeProfitPercent, 0.000001)
        assertEquals(1.0, config.trailingActivationR, 0.000001)
        assertEquals(3.0, config.maxDailyLossPercent, 0.000001)
        assertEquals(3, config.maxConsecutiveLosses)
    }

    @Test
    fun trailingActivatesAtOneRAndMovesStopToBreakevenOrBetter() {
        val config = TradingConfig()
        val policy = ExitPolicy(config)
        val entry = 100.0
        val initialStop = 99.5
        val takeProfit = 101.0

        val beforeOneR = policy.evaluate(entry, 100.4, initialStop, takeProfit, 0.20, null)
        assertEquals("initial_protection", beforeOneR.reason)
        assertEquals(false, beforeOneR.breakevenApplied)

        val atOneR = policy.evaluate(entry, 100.5, initialStop, takeProfit, 0.20, null)
        assertTrue(atOneR.breakevenApplied)
        assertTrue((atOneR.trailingStopPrice ?: 0.0) >= entry)
    }

    @Test
    fun trailingNeverLowersExistingStop() {
        val config = TradingConfig()
        val policy = ExitPolicy(config)
        val entry = 100.0
        val initialStop = 99.5
        val first = policy.evaluate(entry, 101.0, initialStop, 101.0, 0.20, null)
        val second = policy.evaluate(entry, 100.7, initialStop, 101.0, 0.20, null)
        assertTrue((first.trailingStopPrice ?: 0.0) >= entry)
        assertTrue((second.trailingStopPrice ?: 0.0) >= entry)
        assertTrue((first.trailingStopPrice ?: 0.0) >= (second.trailingStopPrice ?: 0.0))
    }
}
