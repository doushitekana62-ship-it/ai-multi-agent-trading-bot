package com.mirei.app.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TradingConfigPhase1Test {
    @Test fun stopLossZeroIsOff() {
        val config = TradingConfig(manualStopLossPercent = 0.0, manualNetProfitTargetIdr = 30.0)
        val targets = config.calculateRiskTargets(100.0, 10_000.0)
        assertEquals(0.0, targets.stopLossPrice, 0.0)
    }

    @Test fun takeProfitTargetIsNetIdrAfterCosts() {
        val config = TradingConfig(manualStopLossPercent = 0.0, manualNetProfitTargetIdr = 30.0)
        val costs = ExecutionCostProfile(0.3, 0.4, 0.1, 0.2)
        val stake = 10_000.0
        val entry = 100.0
        val targets = config.calculateRiskTargets(entry, stake, executionCosts = costs)
        val buyFee = stake * costs.buyFeePercent / (100.0 + costs.buyFeePercent)
        val executedQuantity = (stake - buyFee) / (entry * (1.0 + (costs.spreadPercent / 2.0 + costs.slippagePercent) / 100.0))
        val exitMultiplier = (1.0 - (costs.spreadPercent / 2.0 + costs.slippagePercent) / 100.0) * (1.0 - costs.sellFeePercent / 100.0)
        val netProfit = executedQuantity * targets.takeProfitPrice * exitMultiplier - stake
        assertEquals(30.0, netProfit, 1e-6)
    }

    @Test fun maxOpenPositionsIsTen() {
        assertEquals(10, TradingConfig().maxOpenPositions)
        assertTrue(TradingConfig(maxOpenPositions = 10).maxOpenPositions == 10)
    }
}