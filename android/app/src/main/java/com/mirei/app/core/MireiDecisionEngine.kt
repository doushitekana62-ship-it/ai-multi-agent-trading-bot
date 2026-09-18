package com.mirei.app.core

enum class MireiCycleState { IDLE, INITIAL_BUY_PENDING, HOLDING, REENTRY_WAIT, REENTRY_PENDING, CLOSED }

data class MireiCycle(
    val cycleId: String,
    val symbol: String,
    val initialCapitalIdr: Double,
    val initialBuyPrice: Double,
    val reentryCount: Int = 0,
    val sequence: Int = 1,
    val state: MireiCycleState = MireiCycleState.HOLDING,
    val lastDecision: MireiDecisionAction = MireiDecisionAction.INITIAL_BUY,
    val lastDecisionReason: String = "",
    val lastTransitionAtEpochMs: Long = 0L,
)

enum class MireiDecisionAction {
    INITIAL_BUY,
    HOLD,
    SELL_STOP_LOSS,
    SELL_TAKE_PROFIT,
    REENTRY_WAIT,
    REENTRY_BUY,
    ERROR,
}

data class MireiDecision(
    val action: MireiDecisionAction,
    val symbol: String,
    val reason: String,
    val cycleId: String = "",
    val sequence: Int = 0,
    val referenceCapitalIdr: Double = 0.0,
)

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

    fun decideInitialEntry(
        snapshot: MarketSnapshot,
        initialCapitalIdr: Double,
        stakeOverrideIdr: Double? = null,
        cycleId: String,
    ): MireiDecision {
        if (!snapshot.dataFresh) return MireiDecision(MireiDecisionAction.ERROR, snapshot.symbol, "market_data_unavailable", cycleId)
        if (snapshot.price <= 0.0) return MireiDecision(MireiDecisionAction.ERROR, snapshot.symbol, "invalid_market_price", cycleId)
        if (initialCapitalIdr <= 0.0) return MireiDecision(MireiDecisionAction.ERROR, snapshot.symbol, "invalid_initial_capital", cycleId)
        val plan = buildEntryPlan(snapshot, initialCapitalIdr, stakeOverrideIdr)
        return if (plan.allowed) {
            MireiDecision(MireiDecisionAction.INITIAL_BUY, snapshot.symbol, "mirei_initial_buy_ready", cycleId, 1, initialCapitalIdr)
        } else {
            MireiDecision(MireiDecisionAction.ERROR, snapshot.symbol, plan.reasons.joinToString(","), cycleId, 1, initialCapitalIdr)
        }
    }

    fun decidePosition(snapshot: MarketSnapshot, position: PaperPosition, cycleId: String, sequence: Int): MireiDecision {
        if (!snapshot.dataFresh) return MireiDecision(MireiDecisionAction.HOLD, snapshot.symbol, "market_data_stale_hold", cycleId, sequence, position.riskReferenceCapitalIdr)
        if (snapshot.price <= 0.0) return MireiDecision(MireiDecisionAction.HOLD, snapshot.symbol, "invalid_market_price_hold", cycleId, sequence, position.riskReferenceCapitalIdr)
        return when {
            position.stopLossPrice > 0.0 && snapshot.price <= position.stopLossPrice ->
                MireiDecision(MireiDecisionAction.SELL_STOP_LOSS, snapshot.symbol, "stop_loss_reached", cycleId, sequence, position.riskReferenceCapitalIdr)
            position.takeProfitPrice > 0.0 && snapshot.price >= position.takeProfitPrice ->
                MireiDecision(MireiDecisionAction.SELL_TAKE_PROFIT, snapshot.symbol, "take_profit_reached", cycleId, sequence, position.riskReferenceCapitalIdr)
            else ->
                MireiDecision(MireiDecisionAction.HOLD, snapshot.symbol, "hold_until_sl_tp", cycleId, sequence, position.riskReferenceCapitalIdr)
        }
    }

    fun decideReentry(
        snapshot: MarketSnapshot,
        cycleId: String,
        sequence: Int,
        cycleCapitalIdr: Double,
        availableBalanceIdr: Double,
    ): MireiDecision {
        if (!snapshot.dataFresh) return MireiDecision(MireiDecisionAction.REENTRY_WAIT, snapshot.symbol, "market_data_stale_reentry_wait", cycleId, sequence, cycleCapitalIdr)
        if (snapshot.price <= 0.0) return MireiDecision(MireiDecisionAction.REENTRY_WAIT, snapshot.symbol, "invalid_market_price_reentry_wait", cycleId, sequence, cycleCapitalIdr)
        if (cycleCapitalIdr <= 0.0) return MireiDecision(MireiDecisionAction.REENTRY_WAIT, snapshot.symbol, "reentry_capital_unavailable", cycleId, sequence, cycleCapitalIdr)
        if (availableBalanceIdr <= 0.0) return MireiDecision(MireiDecisionAction.REENTRY_WAIT, snapshot.symbol, "reentry_balance_unavailable", cycleId, sequence, cycleCapitalIdr)
        val stake = cycleCapitalIdr.coerceAtMost(availableBalanceIdr)
        val plan = buildEntryPlan(snapshot, cycleCapitalIdr, stake)
        return if (plan.allowed) {
            MireiDecision(MireiDecisionAction.REENTRY_BUY, snapshot.symbol, "mirei_reentry_ready", cycleId, sequence, cycleCapitalIdr)
        } else {
            MireiDecision(MireiDecisionAction.REENTRY_WAIT, snapshot.symbol, plan.reasons.joinToString(","), cycleId, sequence, cycleCapitalIdr)
        }
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
        val stake = configuredStake.coerceAtMost(activeConfig.totalCapitalIdr)
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
