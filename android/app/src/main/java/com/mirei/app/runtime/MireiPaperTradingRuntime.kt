package com.mirei.app.runtime

import com.mirei.app.agents.AgentAction
import com.mirei.app.agents.DefaultMireiAgents
import com.mirei.app.agents.MireiDecision
import com.mirei.app.agents.MireiOrchestrator
import com.mirei.app.core.MarketSnapshot
import com.mirei.app.core.MireiDecisionEngine
import com.mirei.app.core.RiskSnapshot
import com.mirei.app.core.TradingConfig
import com.mirei.app.execution.ExecutionResult
import com.mirei.app.execution.PaperExecutionEngine
import com.mirei.app.execution.PaperPosition
import com.mirei.app.execution.TradeLedger

interface PaperMarketDataSource {
    fun snapshot(symbol: String): MarketSnapshot?
}

data class RuntimeEnvironment(
    val internetAvailable: Boolean = true,
    val exchangeHealthy: Boolean = true,
)

data class PaperRuntimeStatus(
    val availableBalanceIdr: Double,
    val equityIdr: Double,
    val activePositions: List<PaperPosition>,
    val lastDecision: MireiDecision?,
    val lastExecution: ExecutionResult?,
    val dailyPnlIdr: Double,
    val consecutiveLosses: Int,
    val marketSymbol: String = "",
    val marketPrice: Double = 0.0,
    val marketBidPrice: Double = 0.0,
    val marketAskPrice: Double = 0.0,
    val marketHigh24h: Double = 0.0,
    val marketLow24h: Double = 0.0,
    val marketVolume24h: Double = 0.0,
    val marketMomentumPercent: Double = 0.0,
    val marketVolatilityPercent: Double = 0.0,
    val marketSentimentScore: Double = 0.0,
    val forecastConfidence: Double = 0.0,
    val marketSpreadPercent: Double = 0.0,
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
    val marketDataFresh: Boolean = false,
    val internetAvailable: Boolean = false,
    val exchangeHealthy: Boolean = false,
    val lastTickEpochMs: Long = 0L,
    val lastError: String? = null,
    val entryPlanReasons: List<String> = emptyList(),
)

class MireiPaperTradingRuntime(
    private val config: TradingConfig = TradingConfig(),
    private val marketData: PaperMarketDataSource,
    tradeLedger: TradeLedger? = null,
    private val symbol: String,
    private val engine: PaperExecutionEngine = PaperExecutionEngine(config, tradeLedger = tradeLedger),
    private val orchestrator: MireiOrchestrator = MireiOrchestrator(DefaultMireiAgents.create(), config.decisionMode),
    private val decisionEngine: MireiDecisionEngine = MireiDecisionEngine(config),
) {
    private val dailyStartBalanceIdr = config.totalCapitalIdr
    private var dailyPnlIdr = 0.0
    private var consecutiveLosses = 0
    private var lastDecision: MireiDecision? = null
    private var lastExecution: ExecutionResult? = null
    private var lastError: String? = null
    private var lastSnapshot: MarketSnapshot? = null
    private var lastTickEpochMs = 0L
    private var lastExchangeHealthy = false
    private var lastEntryPlanReasons: List<String> = emptyList()

    fun tick(nowMs: Long, environment: RuntimeEnvironment = RuntimeEnvironment()): PaperRuntimeStatus =
        runCatching {
            lastError = null
            lastTickEpochMs = nowMs
            val snapshot = marketData.snapshot(symbol)
            lastSnapshot = snapshot
            lastExchangeHealthy = snapshot != null && environment.exchangeHealthy
            if (snapshot == null) {
                lastError = "market_data_unavailable"
                lastEntryPlanReasons = listOf("market_data_unavailable")
                lastDecision = null
                return status(environment)
            }
            if (!environment.internetAvailable) {
                lastEntryPlanReasons = listOf("internet_unavailable")
                return status(environment)
            }
            if (!environment.exchangeHealthy) {
                lastEntryPlanReasons = listOf("exchange_unhealthy")
                return status(environment)
            }
            if (!snapshot.dataFresh) {
                lastEntryPlanReasons = listOf("market_snapshot_stale")
                return status(environment)
            }

            val markPrices = mapOf(symbol to snapshot.price)
            closeTriggeredPositions(snapshot.price, nowMs)
            val riskSnapshot = RiskSnapshot(
                dailyPnlIdr = dailyPnlIdr,
                dailyStartBalanceIdr = dailyStartBalanceIdr,
                equityIdr = engine.equityIdr(markPrices),
                openPositions = engine.positionCount(),
                consecutiveLosses = consecutiveLosses,
                marketDataFresh = snapshot.dataFresh,
                exchangeHealthy = lastExchangeHealthy,
                internetAvailable = environment.internetAvailable,
            )
            val plan = decisionEngine.buildEntryPlan(snapshot, riskSnapshot)
            lastEntryPlanReasons = plan.reasons
            val decision = orchestrator.evaluate(snapshot)
            lastDecision = decision
            if (engine.positionCount() < config.maxOpenPositions && decision.action == AgentAction.BUY && !decision.requiresHumanDecision && plan.allowed) {
                lastExecution = engine.open("paper", symbol, plan, nowMs)
            } else {
                lastExecution = null
            }
            status(environment, markPrices)
        }.getOrElse { error ->
            lastError = error.message ?: error.javaClass.simpleName
            lastEntryPlanReasons = listOf("runtime_error")
            lastTickEpochMs = nowMs
            lastExchangeHealthy = false
            status(environment)
        }

    fun closeAll(
        nowMs: Long,
        environment: RuntimeEnvironment = RuntimeEnvironment(),
        reason: String = "manual_close_all",
    ): PaperRuntimeStatus {
        lastTickEpochMs = nowMs
        lastError = null
        if (!environment.internetAvailable || !environment.exchangeHealthy) {
            lastExchangeHealthy = false
            lastError = "close_all_exchange_unavailable"
            lastEntryPlanReasons = listOf("close_all_exchange_unavailable")
            return status(environment)
        }

        val positions = engine.positions()
        for (position in positions) {
            val snapshot = marketData.snapshot(position.symbol)
            if (snapshot == null || !snapshot.dataFresh) {
                lastExchangeHealthy = false
                lastError = "close_all_market_data_unavailable"
                lastEntryPlanReasons = listOf("close_all_market_data_unavailable")
                break
            }
            lastExchangeHealthy = true
            close(position.id, snapshot.price, reason, nowMs)
        }
        return status(environment)
    }

    fun status(environment: RuntimeEnvironment = RuntimeEnvironment(), markPrices: Map<String, Double> = emptyMap()): PaperRuntimeStatus {
        val snapshot = lastSnapshot
        val prices = if (markPrices.isNotEmpty()) markPrices else snapshot?.let { mapOf(it.symbol to it.price) }.orEmpty()
        return PaperRuntimeStatus(
            availableBalanceIdr = engine.availableBalanceIdr(),
            equityIdr = engine.equityIdr(prices),
            activePositions = engine.positions(),
            lastDecision = lastDecision,
            lastExecution = lastExecution,
            dailyPnlIdr = dailyPnlIdr,
            consecutiveLosses = consecutiveLosses,
            marketSymbol = snapshot?.symbol.orEmpty(),
            marketPrice = snapshot?.price ?: 0.0,
            marketBidPrice = snapshot?.bidPrice ?: 0.0,
            marketAskPrice = snapshot?.askPrice ?: 0.0,
            marketHigh24h = snapshot?.high24h ?: 0.0,
            marketLow24h = snapshot?.low24h ?: 0.0,
            marketVolume24h = snapshot?.volume24h ?: 0.0,
            marketMomentumPercent = snapshot?.momentumPercent ?: 0.0,
            marketVolatilityPercent = snapshot?.volatilityPercent ?: 0.0,
            marketSentimentScore = snapshot?.sentimentScore ?: 0.0,
            forecastConfidence = snapshot?.forecastConfidence ?: 0.0,
            marketSpreadPercent = snapshot?.spreadPercent ?: 0.0,
            changeSinceLastTickPercent = snapshot?.changeSinceLastTickPercent ?: 0.0,
            change1mPercent = snapshot?.change1mPercent ?: 0.0,
            change5mPercent = snapshot?.change5mPercent ?: 0.0,
            change15mPercent = snapshot?.change15mPercent ?: 0.0,
            tradeFlowPercent = snapshot?.tradeFlowPercent ?: 0.0,
            trendScorePercent = snapshot?.trendScorePercent ?: 0.0,
            tradeCount = snapshot?.tradeCount ?: 0,
            buyVolume = snapshot?.buyVolume ?: 0.0,
            sellVolume = snapshot?.sellVolume ?: 0.0,
            lastTradeEpochMs = snapshot?.lastTradeEpochMs ?: 0L,
            snapshotEpochMs = snapshot?.snapshotEpochMs ?: 0L,
            sourceAgeMs = snapshot?.sourceAgeMs ?: 0L,
            marketDataFresh = snapshot?.dataFresh == true,
            internetAvailable = environment.internetAvailable,
            exchangeHealthy = lastExchangeHealthy && environment.exchangeHealthy && environment.internetAvailable,
            lastTickEpochMs = lastTickEpochMs,
            lastError = lastError,
            entryPlanReasons = lastEntryPlanReasons,
        )
    }

    fun paperEngine(): PaperExecutionEngine = engine

    private fun closeTriggeredPositions(marketPrice: Double, nowMs: Long) {
        engine.positions().forEach { position ->
            val reason = when {
                marketPrice <= position.stopLossPrice -> "stop_loss"
                marketPrice >= position.takeProfitPrice -> "take_profit"
                else -> null
            } ?: return@forEach
            close(position.id, marketPrice, reason, nowMs)
        }
    }

    private fun close(positionId: String, marketPrice: Double, reason: String, nowMs: Long) {
        val result = engine.close(positionId, marketPrice, reason, nowMs)
        if (!result.success) return
        dailyPnlIdr += result.pnlIdr
        consecutiveLosses = if (result.pnlIdr < 0.0) consecutiveLosses + 1 else 0
        lastExecution = result
    }
}
