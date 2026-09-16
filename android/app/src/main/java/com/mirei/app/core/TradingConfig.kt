package com.mirei.app.core

enum class ManualRiskMode { AUTO, MANUAL }
enum class RiskReferenceMode { ENTRY_PRICE, INITIAL_CAPITAL }
enum class TakeProfitMode { MODE, MANUAL_PERCENT, MANUAL_NET_IDR }

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
    /** When set, manual TP is a net realized IDR target after execution costs. */
    val manualNetProfitTargetIdr: Double? = null,
    val riskReferenceMode: RiskReferenceMode = RiskReferenceMode.ENTRY_PRICE,
) {
    init {
        require(totalCapitalIdr > 0)
        require(positionSizeIdr > 0)
        require(maxOpenPositions in 1..3)
        require(baseStopLossPercent > 0)
        require(baseTakeProfitPercent > baseStopLossPercent)
        require(trailingActivationR > 0)
        require(maxDailyLossPercent > 0)
        require(maxConsecutiveLosses > 0)
        if (manualRiskMode == ManualRiskMode.MANUAL) {
            require(manualStopLossPercent != null && manualStopLossPercent > 0)
            require((manualTakeProfitPercent != null && manualTakeProfitPercent > manualStopLossPercent) || (manualNetProfitTargetIdr != null && manualNetProfitTargetIdr > 0.0))
        }
        if (manualNetProfitTargetIdr != null) require(manualNetProfitTargetIdr > 0.0)
    }

    fun effectiveStopLossPercent(): Double = when (manualRiskMode) {
        ManualRiskMode.MANUAL -> manualStopLossPercent!!
        ManualRiskMode.AUTO -> when (mode) {
            ScalpingMode.AGGRESSIVE -> 0.40
            ScalpingMode.BALANCED -> 0.50
            ScalpingMode.SAFETY -> 0.65
        }
    }

    fun effectiveTakeProfitPercent(): Double = when (manualRiskMode) {
        ManualRiskMode.MANUAL -> manualTakeProfitPercent ?: baseTakeProfitPercent
        ManualRiskMode.AUTO -> when (mode) {
            ScalpingMode.AGGRESSIVE -> 1.00
            ScalpingMode.BALANCED -> 1.00
            ScalpingMode.SAFETY -> 1.25
        }
    }

    fun effectiveTakeProfitMode(): TakeProfitMode = when {
        manualRiskMode != ManualRiskMode.MANUAL -> TakeProfitMode.MODE
        manualNetProfitTargetIdr != null -> TakeProfitMode.MANUAL_NET_IDR
        else -> TakeProfitMode.MANUAL_PERCENT
    }

    fun calculateRiskTargets(
        entryPrice: Double,
        stakeIdr: Double,
        initialCapitalIdr: Double = stakeIdr,
        stopLossPercent: Double = effectiveStopLossPercent(),
        takeProfitPercent: Double = effectiveTakeProfitPercent(),
        executionCosts: ExecutionCostProfile? = null,
    ): RiskTargets {
        require(entryPrice > 0.0)
        require(stakeIdr > 0.0)
        require(initialCapitalIdr > 0.0)
        require(stopLossPercent > 0.0)
        require(takeProfitPercent > stopLossPercent || manualNetProfitTargetIdr != null)

        val quantity = stakeIdr / entryPrice
        val referenceCapital = when (riskReferenceMode) {
            RiskReferenceMode.ENTRY_PRICE -> stakeIdr
            RiskReferenceMode.INITIAL_CAPITAL -> initialCapitalIdr
        }
        val stopLossAmountIdr = referenceCapital * stopLossPercent / 100.0
        val configuredTakeProfitAmountIdr = referenceCapital * takeProfitPercent / 100.0
        val stopLossPrice = (entryPrice - (stopLossAmountIdr / quantity)).coerceAtLeast(entryPrice * 0.000001)

        val netTarget = manualNetProfitTargetIdr
        val takeProfitPrice = if (effectiveTakeProfitMode() == TakeProfitMode.MANUAL_NET_IDR && executionCosts != null) {
            val buyFeeIdr = stakeIdr * executionCosts.buyFeePercent / (100.0 + executionCosts.buyFeePercent)
            val entryNotional = stakeIdr - buyFeeIdr
            val executionEntryPrice = entryPrice * (1.0 + (executionCosts.spreadPercent / 2.0 + executionCosts.slippagePercent) / 100.0)
            val executedQuantity = entryNotional / executionEntryPrice
            val exitMultiplier = (1.0 - (executionCosts.spreadPercent / 2.0 + executionCosts.slippagePercent) / 100.0) * (1.0 - executionCosts.sellFeePercent / 100.0)
            ((stakeIdr + netTarget!!) / (executedQuantity * exitMultiplier)).coerceAtLeast(entryPrice * 1.000001)
        } else {
            entryPrice + (configuredTakeProfitAmountIdr / quantity)
        }
        val takeProfitAmountIdr = if (netTarget != null) netTarget else configuredTakeProfitAmountIdr

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
