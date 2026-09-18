package com.mirei.app.core

data class MarketSnapshot(
    val symbol: String,
    val price: Double,
    val momentumPercent: Double = 0.0,
    val volatilityPercent: Double = 0.0,
    val sentimentScore: Double = 0.0,
    val forecastConfidence: Double = 0.0,
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
    val assetClass: AssetClass = AssetClass.CRYPTO,
    val providerId: String = "paper",
    val quoteCurrency: String = "IDR",
)

data class EntryPlan(
    val allowed: Boolean,
    val entryPrice: Double,
    val stopLossPrice: Double,
    val takeProfitPrice: Double,
    val trailingActivationPrice: Double,
    val stakeIdr: Double,
    val reasons: List<String>,
    val riskReferenceMode: RiskReferenceMode = RiskReferenceMode.ENTRY_PRICE,
    val riskReferenceCapitalIdr: Double = 0.0,
    val takeProfitMode: TakeProfitMode = TakeProfitMode.MANUAL_NET_IDR,
    val manualNetProfitTargetIdr: Double? = null,
    val positionProfile: PositionTradeConfig? = null,
)

class MireiDecisionEngine(initialConfig: TradingConfig) {
    @Volatile private var config: TradingConfig = initialConfig

    fun updateConfig(newConfig: TradingConfig) {
        config = newConfig
    }

    fun buildEntryPlan(
        snapshot: MarketSnapshot,
        initialCapitalIdr: Double? = null,
        stakeOverrideIdr: Double? = null,
    ): EntryPlan {
        val activeConfig = config.forPosition(snapshot.symbol)
        if (!snapshot.dataFresh || snapshot.price <= 0.0) {
            return EntryPlan(false, snapshot.price, 0.0, 0.0, 0.0, 0.0, listOf("market_data_unavailable"))
        }

        val configuredStake = stakeOverrideIdr?.takeIf { it > 0.0 } ?: activeConfig.positionSizeIdr
        val stake = configuredStake.coerceAtMost(activeConfig.totalCapitalIdr / activeConfig.maxOpenPositions)
        if (stake <= 0.0) return EntryPlan(false, snapshot.price, 0.0, 0.0, 0.0, 0.0, listOf("invalid_stake"))

        val referenceCapital = initialCapitalIdr?.takeIf { it > 0.0 } ?: stake
        val costs = TradingUniverse.bySymbol(snapshot.symbol)?.executionCosts
        val targets = activeConfig.calculateRiskTargets(
            entryPrice = snapshot.price,
            stakeIdr = stake,
            initialCapitalIdr = referenceCapital,
            stopLossPercent = activeConfig.effectiveStopLossPercent(),
            executionCosts = costs,
        )
        return EntryPlan(
            allowed = true,
            entryPrice = snapshot.price,
            stopLossPrice = targets.stopLossPrice,
            takeProfitPrice = targets.takeProfitPrice,
            trailingActivationPrice = 0.0,
            stakeIdr = stake,
            reasons = listOf("mirei_reentry_ready"),
            riskReferenceMode = activeConfig.riskReferenceMode,
            riskReferenceCapitalIdr = targets.referenceCapitalIdr,
            takeProfitMode = TakeProfitMode.MANUAL_NET_IDR,
            manualNetProfitTargetIdr = activeConfig.manualNetProfitTargetIdr,
            positionProfile = activeConfig.profileFor(snapshot.symbol),
        )
    }
}
