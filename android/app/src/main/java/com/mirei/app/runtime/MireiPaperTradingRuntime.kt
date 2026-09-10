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

interface PaperMarketDataSource { fun snapshot(symbol: String): MarketSnapshot? }

data class RuntimeEnvironment(val internetAvailable: Boolean = true, val exchangeHealthy: Boolean = true)

data class PaperRuntimeStatus(
    val availableBalanceIdr: Double,
    val equityIdr: Double,
    val activePositions: List<PaperPosition>,
    val lastDecision: MireiDecision?,
    val lastExecution: ExecutionResult?,
    val recentExecutions: List<ExecutionResult> = emptyList(),
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
    val decisionsBySymbol: Map<String, MireiDecision> = emptyMap(),
    val snapshotsBySymbol: Map<String, MarketSnapshot> = emptyMap(),
    val scannerSummary: String = "",
)

class MireiPaperTradingRuntime(
    config: TradingConfig = TradingConfig(),
    private val marketData: PaperMarketDataSource,
    tradeLedger: TradeLedger? = null,
    private val symbol: String,
    private val exchangeId: String = "paper",
    private val managedSymbols: List<String> = listOf(symbol),
    private val engine: PaperExecutionEngine = PaperExecutionEngine(config, tradeLedger = tradeLedger),
    private val orchestrator: MireiOrchestrator = MireiOrchestrator(DefaultMireiAgents.create(), config.decisionMode),
    decisionEngine: MireiDecisionEngine = MireiDecisionEngine(config),
) {
    private var config = config
    private var decisionEngine = decisionEngine
    private val dailyStartBalanceIdr = config.totalCapitalIdr
    private var dailyPnlIdr = 0.0
    private var consecutiveLosses = 0
    private var lastDecision: MireiDecision? = null
    private var lastExecution: ExecutionResult? = null
    private var tickExecutions: MutableList<ExecutionResult> = mutableListOf()
    private var lastError: String? = null
    private var lastSnapshot: MarketSnapshot? = null
    private var lastSnapshots: Map<String, MarketSnapshot> = emptyMap()
    private var lastDecisions: Map<String, MireiDecision> = emptyMap()
    private var lastTickEpochMs = 0L
    private var lastExchangeHealthy = false
    private var lastEntryPlanReasons: List<String> = emptyList()
    private var holdingsSeeded = false
    private var lastScannerSummary = ""
    private val recentlyClosedSymbols = linkedMapOf<String, Long>()

    fun applyRiskConfig(newConfig: TradingConfig) {
        require(newConfig.totalCapitalIdr == config.totalCapitalIdr) { "paper_capital_immutable_while_running" }
        require(newConfig.maxOpenPositions == config.maxOpenPositions) { "paper_position_limit_immutable_while_running" }
        config = newConfig
        decisionEngine = MireiDecisionEngine(newConfig)
        engine.updateRiskTargets(newConfig.effectiveStopLossPercent(), newConfig.effectiveTakeProfitPercent())
    }

    fun seedInitialHoldings(allocations: Map<String, Double>, nowMs: Long): List<ExecutionResult> {
        if (holdingsSeeded || allocations.isEmpty()) return emptyList()
        val normalized = allocations.filter { it.key in managedSymbols && it.value > 0.0 }.toList()
        require(normalized.size <= config.maxOpenPositions) { "initial_holding_position_limit" }
        require(normalized.sumOf { it.second } <= config.totalCapitalIdr + 1e-6) { "initial_holding_exceeds_capital" }
        val results = mutableListOf<ExecutionResult>()
        for ((managedSymbol, amount) in normalized) {
            val snapshot = marketData.snapshot(managedSymbol) ?: continue
            if (!snapshot.dataFresh) continue
            results += engine.seedExistingHolding(exchangeId, managedSymbol, amount, snapshot.price, config.effectiveStopLossPercent(), config.effectiveTakeProfitPercent(), nowMs)
        }
        holdingsSeeded = results.any { it.success }
        if (results.none { it.success }) lastError = "initial_holdings_not_seeded"
        return results
    }

    fun tick(nowMs: Long, environment: RuntimeEnvironment = RuntimeEnvironment()): PaperRuntimeStatus = runCatching {
        tickExecutions = mutableListOf()
        lastError = null
        lastTickEpochMs = nowMs
        val snapshots = managedSymbols.distinct().take(3).mapNotNull { managedSymbol -> marketData.snapshot(managedSymbol)?.let { managedSymbol to it } }.toMap()
        lastSnapshots = snapshots
        lastSnapshot = snapshots[symbol] ?: snapshots.values.firstOrNull()
        lastExchangeHealthy = snapshots.isNotEmpty() && environment.exchangeHealthy
        if (snapshots.isEmpty()) { lastError = "market_data_unavailable"; lastEntryPlanReasons = listOf("market_data_unavailable"); lastDecision = null; return status(environment) }
        if (!environment.internetAvailable) { lastEntryPlanReasons = listOf("internet_unavailable"); return status(environment) }
        if (!environment.exchangeHealthy) { lastEntryPlanReasons = listOf("exchange_unhealthy"); return status(environment) }
        val fresh = snapshots.filterValues { it.dataFresh }
        if (fresh.isEmpty()) { lastEntryPlanReasons = listOf("market_snapshot_stale"); return status(environment) }
        val markPrices = fresh.mapValues { it.value.price }

        fresh.forEach { (managedSymbol, snapshot) -> closeTriggeredPositions(managedSymbol, snapshot.price, nowMs) }

        val riskSnapshot = RiskSnapshot(
            dailyPnlIdr = dailyPnlIdr,
            dailyStartBalanceIdr = dailyStartBalanceIdr,
            equityIdr = engine.equityIdr(markPrices),
            openPositions = engine.positionCount(),
            consecutiveLosses = consecutiveLosses,
            marketDataFresh = fresh.size == snapshots.size,
            exchangeHealthy = lastExchangeHealthy,
            internetAvailable = environment.internetAvailable,
        )
        val decisions = linkedMapOf<String, MireiDecision>()
        val planReasons = linkedMapOf<String, List<String>>()
        var lastExecutionForTick: ExecutionResult? = null

        for ((managedSymbol, snapshot) in fresh) {
            val plan = decisionEngine.buildEntryPlan(snapshot, riskSnapshot.copy(openPositions = engine.positionCount()))
            planReasons[managedSymbol] = plan.reasons
            val decision = orchestrator.evaluate(snapshot)
            decisions[managedSymbol] = decision
            if (decision.action == AgentAction.CLOSE && !decision.requiresHumanDecision) {
                engine.positions().filter { it.symbol == managedSymbol }.toList().forEach { position ->
                    val execution = engine.close(position.id, snapshot.price, "ai_close", nowMs)
                    if (execution.success) {
                        recentlyClosedSymbols[managedSymbol] = nowMs
                        lastExecutionForTick = execution
                        tickExecutions += execution
                        dailyPnlIdr += execution.pnlIdr
                        consecutiveLosses = if (execution.pnlIdr < 0.0) consecutiveLosses + 1 else 0
                    }
                }
            } else if (engine.positionCount() < config.maxOpenPositions && decision.action == AgentAction.BUY && !decision.requiresHumanDecision && plan.allowed) {
                val entryReason = if (recentlyClosedSymbols.containsKey(managedSymbol)) "re_entry" else "entry_filled"
                val execution = engine.open(exchangeId, managedSymbol, plan, nowMs, entryReason)
                lastExecutionForTick = execution
                if (execution.success) {
                    tickExecutions += execution
                    recentlyClosedSymbols.remove(managedSymbol)
                }
            }
        }

        lastDecisions = decisions
        lastDecision = decisions[symbol] ?: decisions.values.firstOrNull()
        lastExecution = lastExecutionForTick ?: tickExecutions.lastOrNull()
        lastEntryPlanReasons = planReasons[symbol] ?: planReasons.values.firstOrNull().orEmpty()
        status(environment, markPrices)
    }.getOrElse { error ->
        lastError = error.message ?: error.javaClass.simpleName
        lastEntryPlanReasons = listOf("runtime_error")
        lastTickEpochMs = nowMs
        lastExchangeHealthy = false
        status(environment)
    }

    fun updateScannerSummary(summary: String) { lastScannerSummary = summary }

    fun closeAll(nowMs: Long, environment: RuntimeEnvironment = RuntimeEnvironment(), reason: String = "manual_close_all"): PaperRuntimeStatus {
        tickExecutions = mutableListOf()
        lastTickEpochMs = nowMs
        lastError = null
        if (!environment.internetAvailable || !environment.exchangeHealthy) { lastExchangeHealthy = false; lastError = "close_all_exchange_unavailable"; lastEntryPlanReasons = listOf("close_all_exchange_unavailable"); return status(environment) }
        engine.positions().toList().forEach { position ->
            val snapshot = marketData.snapshot(position.symbol)
            if (snapshot == null || !snapshot.dataFresh) { lastExchangeHealthy = false; lastError = "close_all_market_data_unavailable"; lastEntryPlanReasons = listOf("close_all_market_data_unavailable"); return@forEach }
            lastExchangeHealthy = true
            close(position.id, snapshot.price, reason, nowMs)
        }
        lastExecution = tickExecutions.lastOrNull()
        return status(environment)
    }

    fun status(environment: RuntimeEnvironment = RuntimeEnvironment(), markPrices: Map<String, Double> = emptyMap()): PaperRuntimeStatus {
        val snapshot = lastSnapshot
        val prices = if (markPrices.isNotEmpty()) markPrices else lastSnapshots.mapValues { it.value.price }
        return PaperRuntimeStatus(
            availableBalanceIdr = engine.availableBalanceIdr(), equityIdr = engine.equityIdr(prices), activePositions = engine.positions(),
            lastDecision = lastDecision, lastExecution = lastExecution, recentExecutions = tickExecutions.toList(), dailyPnlIdr = dailyPnlIdr, consecutiveLosses = consecutiveLosses,
            marketSymbol = snapshot?.symbol.orEmpty(), marketPrice = snapshot?.price ?: 0.0, marketBidPrice = snapshot?.bidPrice ?: 0.0,
            marketAskPrice = snapshot?.askPrice ?: 0.0, marketHigh24h = snapshot?.high24h ?: 0.0, marketLow24h = snapshot?.low24h ?: 0.0,
            marketVolume24h = snapshot?.volume24h ?: 0.0, marketMomentumPercent = snapshot?.momentumPercent ?: 0.0,
            marketVolatilityPercent = snapshot?.volatilityPercent ?: 0.0, marketSentimentScore = snapshot?.sentimentScore ?: 0.0,
            forecastConfidence = snapshot?.forecastConfidence ?: 0.0, marketSpreadPercent = snapshot?.spreadPercent ?: 0.0,
            changeSinceLastTickPercent = snapshot?.changeSinceLastTickPercent ?: 0.0, change1mPercent = snapshot?.change1mPercent ?: 0.0,
            change5mPercent = snapshot?.change5mPercent ?: 0.0, change15mPercent = snapshot?.change15mPercent ?: 0.0,
            tradeFlowPercent = snapshot?.tradeFlowPercent ?: 0.0, trendScorePercent = snapshot?.trendScorePercent ?: 0.0,
            tradeCount = snapshot?.tradeCount ?: 0, buyVolume = snapshot?.buyVolume ?: 0.0, sellVolume = snapshot?.sellVolume ?: 0.0,
            lastTradeEpochMs = snapshot?.lastTradeEpochMs ?: 0L, snapshotEpochMs = snapshot?.snapshotEpochMs ?: 0L,
            sourceAgeMs = snapshot?.sourceAgeMs ?: 0L, marketDataFresh = snapshot?.dataFresh == true,
            internetAvailable = environment.internetAvailable, exchangeHealthy = lastExchangeHealthy && environment.exchangeHealthy && environment.internetAvailable,
            lastTickEpochMs = lastTickEpochMs, lastError = lastError, entryPlanReasons = lastEntryPlanReasons,
            decisionsBySymbol = lastDecisions, snapshotsBySymbol = lastSnapshots, scannerSummary = lastScannerSummary,
        )
    }

    fun paperEngine(): PaperExecutionEngine = engine

    private fun closeTriggeredPositions(managedSymbol: String, marketPrice: Double, nowMs: Long) {
        engine.positions().filter { it.symbol == managedSymbol }.forEach { position ->
            val reason = when {
                marketPrice <= position.stopLossPrice -> "stop_loss"
                marketPrice >= position.takeProfitPrice -> "take_profit"
                else -> null
            } ?: return@forEach
            close(position.id, marketPrice, reason, nowMs)
            if (engine.position(position.id) == null) recentlyClosedSymbols[managedSymbol] = nowMs
        }
    }

    private fun close(positionId: String, marketPrice: Double, reason: String, nowMs: Long) {
        val result = engine.close(positionId, marketPrice, reason, nowMs)
        if (!result.success) return
        dailyPnlIdr += result.pnlIdr
        consecutiveLosses = if (result.pnlIdr < 0.0) consecutiveLosses + 1 else 0
        lastExecution = result
        tickExecutions += result
    }
}
