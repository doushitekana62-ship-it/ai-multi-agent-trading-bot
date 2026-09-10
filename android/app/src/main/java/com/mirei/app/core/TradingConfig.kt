package com.mirei.app.core

enum class ManualRiskMode { AUTO, MANUAL }

data class TradingConfig(
    val totalCapitalIdr: Double = 150_000.0,
    val positionSizeIdr: Double = 50_000.0,
    val maxOpenPositions: Int = 3,
    val baseStopLossPercent: Double = 0.5,
    val baseTakeProfitPercent: Double = 1.0,
    val sentimentHoldThreshold: Double = -30.0,
    val trailingActivationR: Double = 1.0,
    val maxDailyLossPercent: Double = 3.0,
    val maxConsecutiveLosses: Int = 3,
    val mode: ScalpingMode = ScalpingMode.BALANCED,
    val decisionMode: DecisionMode = DecisionMode.SUGGESTION,
    val manualRiskMode: ManualRiskMode = ManualRiskMode.AUTO,
    val manualStopLossPercent: Double? = null,
    val manualTakeProfitPercent: Double? = null,
) {
    init {
        require(totalCapitalIdr > 0)
        require(positionSizeIdr > 0)
        require(maxOpenPositions in 1..3)
        require(baseStopLossPercent > 0)
        require(baseTakeProfitPercent > 0)
        require(baseTakeProfitPercent > baseStopLossPercent)
        require(trailingActivationR > 0)
        require(maxDailyLossPercent > 0)
        require(maxConsecutiveLosses > 0)
        if (manualRiskMode == ManualRiskMode.MANUAL) {
            require(manualStopLossPercent != null && manualStopLossPercent > 0)
            require(manualTakeProfitPercent != null && manualTakeProfitPercent > manualStopLossPercent)
        }
    }

    fun effectiveStopLossPercent(): Double = when (manualRiskMode) {
        ManualRiskMode.MANUAL -> manualStopLossPercent!!
        ManualRiskMode.AUTO -> when (mode) {
            ScalpingMode.AGGRESSIVE -> 0.35
            ScalpingMode.BALANCED -> 0.50
            ScalpingMode.SAFETY -> 0.70
        }
    }

    fun effectiveTakeProfitPercent(): Double = when (manualRiskMode) {
        ManualRiskMode.MANUAL -> manualTakeProfitPercent!!
        ManualRiskMode.AUTO -> when (mode) {
            ScalpingMode.AGGRESSIVE -> 1.50
            ScalpingMode.BALANCED -> 1.00
            ScalpingMode.SAFETY -> 0.90
        }
    }
}
