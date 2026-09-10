package com.mirei.app.core

data class MarketSnapshot(
    val symbol: String,
    val price: Double,
    val momentumPercent: Double,
    val volatilityPercent: Double,
    val sentimentScore: Double,
    val forecastConfidence: Double,
    val dataFresh: Boolean,
    val bidPrice: Double = price,
    val askPrice: Double = price,
    val high24h: Double = price,
    val low24h: Double = price,
    val volume24h: Double = 0.0,
    val spreadPercent: Double = 0.0,
    val changeSinceLastTickPercent: Double = 0.0,
    val change1mPercent: Double = 0.0,
    val change5mPercent: Double = 0.0,
    val change15mPercent: Double = 0.0,
    val tradeFlowPercent: Double = 0.0,
    val trendScorePercent: Double = 0.0,
    val tradeCount: Int = 0,
    val buyVolume: Double = 0.0,
    val sellVolume: Double = 0.0,
    val lastTradeEpochMs: Long = 0L,
    val snapshotEpochMs: Long = 0L,
    val sourceAgeMs: Long = 0L,
)

data class EntryPlan(
    val allowed: Boolean,
    val entryPrice: Double,
    val stopLossPrice: Double,
    val takeProfitPrice: Double,
    val trailingActivationPrice: Double,
    val stakeIdr: Double,
    val reasons: List<String>,
)

class MireiDecisionEngine(
    private val config: TradingConfig,
    private val riskPolicy: RiskPolicy = RiskPolicy(config),
) {
    fun buildEntryPlan(snapshot: MarketSnapshot, riskSnapshot: RiskSnapshot): EntryPlan {
        val risk = riskPolicy.evaluate(riskSnapshot)
        val reasons = mutableListOf<String>()
        if (!risk.allowedToOpen) reasons += risk.reasons
        if (!snapshot.dataFresh) reasons += "market_snapshot_stale"
        if (snapshot.price <= 0.0) reasons += "invalid_price"
        if (snapshot.forecastConfidence < minimumConfidence()) reasons += "forecast_confidence_low"
        if (snapshot.sentimentScore <= config.sentimentHoldThreshold) reasons += "negative_sentiment_hold"
        if (snapshot.momentumPercent <= 0.0) reasons += "momentum_not_positive"

        if (!risk.allowedToOpen || reasons.isNotEmpty()) {
            return EntryPlan(false, snapshot.price, 0.0, 0.0, 0.0, 0.0, reasons.ifEmpty { listOf("no_trade") })
        }

        val baseStop = config.effectiveStopLossPercent()
        val baseTake = config.effectiveTakeProfitPercent()
        val volatilityFactor = (snapshot.volatilityPercent / 0.5).coerceAtLeast(1.0)
        val riskLossPercent = if (config.manualRiskMode == ManualRiskMode.MANUAL) {
            baseStop
        } else {
            (baseStop / volatilityFactor).coerceIn(baseStop * 0.50, baseStop)
        }
        val stop = snapshot.price * (1.0 - riskLossPercent / 100.0)
        val target = snapshot.price * (1.0 + baseTake / 100.0)
        val activation = snapshot.price * (1.0 + (riskLossPercent * config.trailingActivationR) / 100.0)
        val stake = minOf(config.positionSizeIdr * risk.positionMultiplier, config.totalCapitalIdr / config.maxOpenPositions)

        return EntryPlan(
            allowed = true,
            entryPrice = snapshot.price,
            stopLossPrice = stop,
            takeProfitPrice = target,
            trailingActivationPrice = activation,
            stakeIdr = stake,
            reasons = listOf("mirei_entry_gates_passed"),
        )
    }

    fun minimumConfidence(): Double = when (config.mode) {
        ScalpingMode.AGGRESSIVE -> 0.55
        ScalpingMode.BALANCED -> 0.65
        ScalpingMode.SAFETY -> 0.75
    }
}
