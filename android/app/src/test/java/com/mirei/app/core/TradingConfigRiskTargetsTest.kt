package com.mirei.app.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
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

    @Test
    fun manualTpSlWithInitialCapitalUsesTheFirstBuyAsTheMonetaryReference() {
        val config = TradingConfig(
            mode = ScalpingMode.AGGRESSIVE,
            manualRiskMode = ManualRiskMode.MANUAL,
            manualStopLossPercent = 0.50,
            manualTakeProfitPercent = 1.00,
            riskReferenceMode = RiskReferenceMode.INITIAL_CAPITAL,
        )

        val targets = config.calculateRiskTargets(
            entryPrice = 43_283_000.0,
            stakeIdr = 50_000.0,
            initialCapitalIdr = 50_000.0,
        )

        assertEquals(50_000.0, targets.referenceCapitalIdr, 1e-9)
        assertEquals(250.0, targets.stopLossAmountIdr, 1e-9)
        assertEquals(500.0, targets.takeProfitAmountIdr, 1e-9)
        assertEquals(43_715_830.0, targets.takeProfitPrice, 1e-6)
        assertEquals(43_066_585.0, targets.stopLossPrice, 1e-6)
    }

    @Test
    fun referenceModeOnlyChangesExitTargetsNotEntryGateDecisionInputs() {
        val snapshot = MarketSnapshot(
            symbol = "TEST/IDR",
            price = 100_000.0,
            momentumPercent = 5.0,
            volatilityPercent = 0.5,
            sentimentScore = 10.0,
            forecastConfidence = 0.80,
            dataFresh = true,
        )
        val risk = RiskSnapshot(
            dailyPnlIdr = 0.0,
            dailyStartBalanceIdr = 150_000.0,
            equityIdr = 150_000.0,
            openPositions = 0,
            consecutiveLosses = 0,
            marketDataFresh = true,
            exchangeHealthy = true,
            internetAvailable = true,
        )
        val entryConfig = TradingConfig(riskReferenceMode = RiskReferenceMode.ENTRY_PRICE)
        val initialCapitalConfig = TradingConfig(riskReferenceMode = RiskReferenceMode.INITIAL_CAPITAL)

        val entryPlan = MireiDecisionEngine(entryConfig).buildEntryPlan(snapshot, risk, 50_000.0)
        val capitalPlan = MireiDecisionEngine(initialCapitalConfig).buildEntryPlan(snapshot, risk, 50_000.0)

        assertEquals(entryPlan.allowed, capitalPlan.allowed)
        assertEquals(entryPlan.reasons, capitalPlan.reasons)
        assertEquals(entryPlan.entryPrice, capitalPlan.entryPrice, 1e-9)
        assertEquals(entryPlan.stakeIdr, capitalPlan.stakeIdr, 1e-9)
        assertNotEquals(entryPlan.riskReferenceMode, capitalPlan.riskReferenceMode)
    }

    @Test
    fun extremeInitialCapitalCannotChangeEntryGateOutcome() {
        val snapshot = MarketSnapshot(
            symbol = "TEST/IDR",
            price = 100_000.0,
            momentumPercent = 4.0,
            volatilityPercent = 0.5,
            sentimentScore = 5.0,
            forecastConfidence = 0.80,
            dataFresh = true,
        )
        val risk = RiskSnapshot(
            dailyPnlIdr = 0.0,
            dailyStartBalanceIdr = 150_000.0,
            equityIdr = 150_000.0,
            openPositions = 0,
            holdDecisionCount = 0,
            consecutiveLosses = 0,
            marketDataFresh = true,
            exchangeHealthy = true,
            internetAvailable = true,
        )
        val entryEngine = MireiDecisionEngine(TradingConfig(riskReferenceMode = RiskReferenceMode.ENTRY_PRICE))
        val capitalEngine = MireiDecisionEngine(TradingConfig(riskReferenceMode = RiskReferenceMode.INITIAL_CAPITAL))

        val entryPlan = entryEngine.buildEntryPlan(snapshot, risk, initialCapitalIdr = 50_000.0)
        val capitalPlan = capitalEngine.buildEntryPlan(snapshot, risk, initialCapitalIdr = 500_000.0)

        assertEquals(true, entryPlan.allowed)
        assertEquals(entryPlan.allowed, capitalPlan.allowed)
        assertEquals(entryPlan.reasons, capitalPlan.reasons)
        assertEquals(entryPlan.entryPrice, capitalPlan.entryPrice, 1e-9)
        assertEquals(entryPlan.stakeIdr, capitalPlan.stakeIdr, 1e-9)
        assertEquals(RiskReferenceMode.ENTRY_PRICE, entryPlan.riskReferenceMode)
        assertEquals(RiskReferenceMode.INITIAL_CAPITAL, capitalPlan.riskReferenceMode)
    }
}
