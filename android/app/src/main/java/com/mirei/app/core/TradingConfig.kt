package com.mirei.app.core

enum class ManualRiskMode { AUTO, MANUAL }
enum class RiskReferenceMode { ENTRY_PRICE, INITIAL_CAPITAL }

data class RiskTargets(
    val stopLossPrice: Double,
    val takeProfitPrice: Double,
    val stopLossAmountIdr: Double,
    val takeProfitAmountIdr: Double,
    val quantity: Double,
    val referenceCapitalIdr: Double,
)

data class TradingConfig(
    val totalCapitalIdr: Double = 150_000.0,
    val positionSizeIdr: Double = 50_000.0,
    val maxOpenPositions: Int = 3,
    val baseStopLossPercent: Double = 0.50,
    val baseTakeProfitPercent: Double = 1.00,
    val sentimentHoldThreshold: Double = -30.0,
    val trailingActivationR: Double = 1.0,
    val maxDailyLossPercent: Double = 3.0,
    val maxConsecutiveLosses: Int = 3,
    val mode: ScalpingMode = ScalpingMode.BALANCED,
    val decisionMode: DecisionMode = DecisionMode.SUGGESTION,
    val manualRiskMode: ManualRiskMode = ManualRiskMode.AUTO,
    val manualStopLossPercent: Double? = null,
    val manualTakeProfitPercent: Double? = null,
    val riskReferenceMode: RiskReferenceMode = RiskReferenceMode.ENTRY_PRICE,
) {
    init {
        require(totalCapitalIdr > 0)
        require(positionSizeIdr > 0)
        require(maxOpenPositions in 1..3)
        require(baseStopLossPercent >= 0)
        require(baseTakeProfitPercent > 0)
        require(baseTakeProfitPercent > baseStopLossPercent)
        require(trailingActivationR > 0)
        require(maxDailyLossPercent > 0)
        require(maxConsecutiveLosses > 0)
        if (manualRiskMode == ManualRiskMode.MANUAL) {
            require(manualStopLossPercent != null && manualStopLossPercent >= 0)
            require(manualTakeProfitPercent != null && manualTakeProfitPercent > manualStopLossPercent)
        }
    }

    fun effectiveStopLossPercent(): Double = when (manualRiskMode) {
        ManualRiskMode.MANUAL -> manualStopLossPercent!!
        ManualRiskMode.AUTO -> when (mode) {
            // Aggressive template intentionally uses unlimited hold: no price stop.
            ScalpingMode.AGGRESSIVE -> 0.0
            ScalpingMode.BALANCED -> 0.50
            ScalpingMode.SAFETY -> 0.65
        }
    }

    fun effectiveTakeProfitPercent(): Double = when (manualRiskMode) {
        ManualRiskMode.MANUAL -> manualTakeProfitPercent!!
        ManualRiskMode.AUTO -> when (mode) {
            ScalpingMode.AGGRESSIVE -> 1.00
            ScalpingMode.BALANCED -> 1.00
            ScalpingMode.SAFETY -> 1.25
        }
    }

    /**
     * Calculates exit thresholds only. This function is deliberately outside
     * Mirei's entry decision gates: changing riskReferenceMode must never turn
     * a BUY/SELL/HOLD decision into another decision.
     *
     * A zero stop-loss percentage is a deliberate unlimited-hold mode. In that
     * mode stopLossPrice is 0 and the runtime must not close the position on SL
     * or use trailing protection; the position remains open until take-profit
     * or an explicit user close.
     */
    fun calculateRiskTargets(
        entryPrice: Double,
        stakeIdr: Double,
        initialCapitalIdr: Double = stakeIdr,
        stopLossPercent: Double = effectiveStopLossPercent(),
        takeProfitPercent: Double = effectiveTakeProfitPercent(),
    ): RiskTargets {
        require(entryPrice > 0.0)
        require(stakeIdr > 0.0)
        require(initialCapitalIdr > 0.0)
        require(stopLossPercent >= 0.0)
        require(takeProfitPercent > stopLossPercent)

        val quantity = stakeIdr / entryPrice
        val referenceCapital = when (riskReferenceMode) {
            RiskReferenceMode.ENTRY_PRICE -> stakeIdr
            RiskReferenceMode.INITIAL_CAPITAL -> initialCapitalIdr
        }
        val stopLossAmountIdr = referenceCapital * stopLossPercent / 100.0
        val takeProfitAmountIdr = referenceCapital * takeProfitPercent / 100.0
        val stopLossPrice = if (stopLossPercent == 0.0) {
            0.0
        } else {
            (entryPrice - (stopLossAmountIdr / quantity)).coerceAtLeast(entryPrice * 0.000001)
        }
        val takeProfitPrice = entryPrice + (takeProfitAmountIdr / quantity)

        return RiskTargets(
            stopLossPrice = stopLossPrice,
            takeProfitPrice = takeProfitPrice,
            stopLossAmountIdr = stopLossAmountIdr,
            takeProfitAmountIdr = takeProfitAmountIdr,
            quantity = quantity,
            referenceCapitalIdr = referenceCapital,
        )
    }
}
