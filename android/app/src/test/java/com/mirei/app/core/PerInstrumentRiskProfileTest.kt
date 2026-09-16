package com.mirei.app.core

import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertEquals
import org.junit.Test

class PerInstrumentRiskProfileTest {
    @Test
    fun manualContractsAreResolvedIndependentlyPerSymbol() {
        val btc = PositionTradeConfig(
            mode = ScalpingMode.BALANCED,
            manualRiskMode = ManualRiskMode.MANUAL,
            stopLossPercent = 0.50,
            takeProfitMode = TakeProfitMode.MANUAL_NET_IDR,
            manualNetProfitTargetIdr = 30.0,
            riskReferenceMode = RiskReferenceMode.ENTRY_PRICE,
        )
        val eth = PositionTradeConfig(
            mode = ScalpingMode.AGGRESSIVE,
            manualRiskMode = ManualRiskMode.MANUAL,
            stopLossPercent = 0.80,
            takeProfitMode = TakeProfitMode.MANUAL_PERCENT,
            manualTakeProfitPercent = 1.40,
            riskReferenceMode = RiskReferenceMode.INITIAL_CAPITAL,
        )
        val config = TradingConfig(positionProfiles = mapOf("BTC/IDR" to btc, "ETH/IDR" to eth))
        val btcConfig = config.forPosition("BTC/IDR")
        val ethConfig = config.forPosition("ETH/IDR")
        assertEquals(ManualRiskMode.MANUAL, btcConfig.manualRiskMode)
        assertEquals(TakeProfitMode.MANUAL_NET_IDR, btcConfig.effectiveTakeProfitMode())
        assertEquals(30.0, btcConfig.manualNetProfitTargetIdr!!, 0.0001)
        assertEquals(0.80, ethConfig.manualStopLossPercent!!, 0.0001)
        assertEquals(1.40, ethConfig.manualTakeProfitPercent!!, 0.0001)
        assertNotEquals(btcConfig.riskReferenceMode, ethConfig.riskReferenceMode)
    }
}
