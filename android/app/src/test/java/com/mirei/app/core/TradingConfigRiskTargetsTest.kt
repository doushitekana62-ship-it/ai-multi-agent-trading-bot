package com.mirei.app.core

import org.junit.Assert.assertEquals
import org.junit.Test

class TradingConfigRiskTargetsTest {
    @Test
    fun automaticTargetsUseEntryPriceAndAllocatedCapital() {
        val config = TradingConfig(
            positionSizeIdr = 50_000.0,
            mode = ScalpingMode.BALANCED,
            manualRiskMode = ManualRiskMode.AUTO,
        )

        val targets = config.calculateRiskTargets(
            entryPrice = 100_000.0,
            stakeIdr = 50_000.0,
        )

        assertEquals(0.50, targets.stopLossAmountIdr / 50_000.0 * 100.0, 1e-9)
        assertEquals(1.00, targets.takeProfitAmountIdr / 50_000.0 * 100.0, 1e-9)
        assertEquals(99_500.0, targets.stopLossPrice, 1e-9)
        assertEquals(101_000.0, targets.takeProfitPrice, 1e-9)
        assertEquals(0.5, targets.quantity, 1e-12)
    }

    @Test
    fun automaticTargetsScaleWithCapitalButKeepTheConfiguredRiskPercent() {
        val config = TradingConfig(mode = ScalpingMode.BALANCED, manualRiskMode = ManualRiskMode.AUTO)

        val smaller = config.calculateRiskTargets(200_000.0, 25_000.0)
        val larger = config.calculateRiskTargets(200_000.0, 100_000.0)

        assertEquals(199_000.0, smaller.stopLossPrice, 1e-9)
        assertEquals(202_000.0, smaller.takeProfitPrice, 1e-9)
        assertEquals(smaller.stopLossPrice, larger.stopLossPrice, 1e-9)
        assertEquals(smaller.takeProfitPrice, larger.takeProfitPrice, 1e-9)
        assertEquals(125.0, smaller.stopLossAmountIdr, 1e-9)
        assertEquals(250.0, smaller.takeProfitAmountIdr, 1e-9)
        assertEquals(500.0, larger.stopLossAmountIdr, 1e-9)
        assertEquals(1_000.0, larger.takeProfitAmountIdr, 1e-9)
        assertEquals(0.5, larger.quantity, 1e-12)
    }

    @Test
    fun initialCapitalBasisKeepsFirstBuyCapitalAsReference() {
        val config = TradingConfig(
            mode = ScalpingMode.BALANCED,
            manualRiskMode = ManualRiskMode.AUTO,
            riskReferenceMode = RiskReferenceMode.INITIAL_CAPITAL,
        )

        val targets = config.calculateRiskTargets(
            entryPrice = 200_000.0,
            stakeIdr = 25_000.0,
            initialCapitalIdr = 50_000.0,
        )

        assertEquals(50_000.0, targets.referenceCapitalIdr, 1e-9)
        assertEquals(250.0, targets.stopLossAmountIdr, 1e-9)
        assertEquals(500.0, targets.takeProfitAmountIdr, 1e-9)
        assertEquals(198_000.0, targets.stopLossPrice, 1e-9)
        assertEquals(204_000.0, targets.takeProfitPrice, 1e-9)
        assertEquals(0.125, targets.quantity, 1e-12)
    }
}
