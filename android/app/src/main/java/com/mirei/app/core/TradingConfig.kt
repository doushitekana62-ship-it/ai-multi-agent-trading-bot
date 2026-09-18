package com.mirei.app.core

enum class RiskReferenceMode { ENTRY_PRICE, INITIAL_CAPITAL }
enum class TakeProfitMode { MANUAL_NET_IDR }

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
    val maxOpenPositions: Int = 10,
    val baseStopLossPercent: Double = 0.50,
    val reentryPriceTolerancePercent: Double = 0.35,
    val riskReferenceMode: RiskReferenceMode = RiskReferenceMode.ENTRY_PRICE,
    val manualStopLossPercent: Double = baseStopLossPercent,
    val manualNetProfitTargetIdr: Double = 30.0,
    val positionProfiles: Map<String, PositionTradeConfig> = emptyMap(),
) {
    init {
        require(totalCapitalIdr > 0.0)
        require(positionSizeIdr > 0.0)
        require(maxOpenPositions in 1..10)
        require(manualStopLossPercent >= 0.0)
        require(manualNetProfitTargetIdr > 0.0)
        require(reentryPriceTolerancePercent >= 0.0)
    }

    fun profileFor(symbol: String): PositionTradeConfig? = positionProfiles[symbol] ?: PositionTradeConfigStore.get(symbol)

    fun forPosition(symbol: String): TradingConfig {
        val profile = profileFor(symbol) ?: return this
        return copy(
            manualStopLossPercent = profile.stopLossPercent ?: manualStopLossPercent,
            manualNetProfitTargetIdr = profile.manualNetProfitTargetIdr ?: manualNetProfitTargetIdr,
            riskReferenceMode = profile.riskReferenceMode ?: riskReferenceMode,
            positionProfiles = emptyMap(),
        )
    }

    fun effectiveStopLossPercent(): Double = manualStopLossPercent

    fun effectiveTakeProfitPercent(): Double = 1.0

    fun effectiveTakeProfitMode(): TakeProfitMode = TakeProfitMode.MANUAL_NET_IDR

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
        require(stopLossPercent >= 0.0)

        val quantity = stakeIdr / entryPrice
        val referenceCapital = if (riskReferenceMode == RiskReferenceMode.ENTRY_PRICE) stakeIdr else initialCapitalIdr
        val stopLossAmountIdr = referenceCapital * stopLossPercent / 100.0
        val stopLossPrice = if (stopLossPercent == 0.0) 0.0 else (entryPrice - stopLossAmountIdr / quantity).coerceAtLeast(entryPrice * 0.000001)

        val netTarget = manualNetProfitTargetIdr
        val takeProfitPrice = if (executionCosts != null) {
            val buyFeeIdr = stakeIdr * executionCosts.buyFeePercent / (100.0 + executionCosts.buyFeePercent)
            val entryNotional = stakeIdr - buyFeeIdr
            val executionEntryPrice = entryPrice * (1.0 + (executionCosts.spreadPercent / 2.0 + executionCosts.slippagePercent) / 100.0)
            val executedQuantity = entryNotional / executionEntryPrice
            val exitMultiplier = (1.0 - (executionCosts.spreadPercent / 2.0 + executionCosts.slippagePercent) / 100.0) *
                (1.0 - executionCosts.sellFeePercent / 100.0)
            ((stakeIdr + netTarget) / (executedQuantity * exitMultiplier)).coerceAtLeast(entryPrice * 1.000001)
        } else {
            entryPrice + netTarget / quantity
        }

        return RiskTargets(
            stopLossPrice = stopLossPrice,
            takeProfitPrice = takeProfitPrice,
            stopLossAmountIdr = stopLossAmountIdr,
            takeProfitAmountIdr = netTarget,
            quantity = quantity,
            referenceCapitalIdr = referenceCapital,
        )
    }
}
