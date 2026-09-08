package com.mirei.app.core

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
    }
}
