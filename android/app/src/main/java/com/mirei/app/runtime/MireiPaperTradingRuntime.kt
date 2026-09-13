package com.mirei.app.runtime

import com.mirei.app.agents.AgentAction
import com.mirei.app.agents.DefaultMireiAgents
import com.mirei.app.agents.MireiDecision
import com.mirei.app.agents.MireiOrchestrator
import com.mirei.app.core.EntryPlan
import com.mirei.app.core.ExitPolicy
import com.mirei.app.core.MarketSnapshot
import com.mirei.app.core.MireiDecisionEngine
import com.mirei.app.core.RiskPolicy
import com.mirei.app.core.RiskReferenceMode
import com.mirei.app.core.RiskSnapshot
import com.mirei.app.core.TradingConfig
import com.mirei.app.execution.ExecutionResult
import com.mirei.app.execution.PaperEngineState
import com.mirei.app.execution.PaperExecutionEngine
import com.mirei.app.execution.PaperPosition
import com.mirei.app.execution.TradeLedger

interface PaperMarketDataSource { fun snapshot(symbol: String): MarketSnapshot? }
data class RuntimeEnvironment(val internetAvailable: Boolean = true, val exchangeHealthy: Boolean = true)

data class PaperRuntimeStatus(
    val availableBalanceIdr: Double, val equityIdr: Double, val activePositions: List<PaperPosition>,
    val lastDecision: MireiDecision?, val lastExecution: ExecutionResult?, val recentExecutions: List<ExecutionResult> = emptyList(),
    val dailyPnlIdr: Double, val consecutiveLosses: Int, val marketSymbol: String = "", val marketPrice: Double = 0.0,
    val marketBidPrice: Double = 0.0, val marketAskPrice: Double = 0.0, val marketHigh24h: Double = 0.0, val marketLow24h: Double = 0.0,
    val marketVolume24h: Double = 0.0, val marketMomentumPercent: Double = 0.0, val marketVolatilityPercent: Double = 0.0,
    val marketSentimentScore: Double = 0.0, val forecastConfidence: Double = 0.0, val marketSpreadPercent: Double = 0.0,
    val changeSinceLastTickPercent: Double = 0.0, val change1mPercent: Double = 0.0, val change5mPercent: Double = 0.0,
    val change15mPercent: Double = 0.0, val tradeFlowPercent: Double = 0.0, val trendScorePercent: Double = 0.0,
    val tradeCount: Int = 0, val buyVolume: Double = 0.0, val sellVolume: Double = 0.0, val lastTradeEpochMs: Long = 0L,
    val snapshotEpochMs: Long = 0L, val sourceAgeMs: Long = 0L, val marketDataFresh: Boolean = false,
    val internetAvailable: Boolean = false, val exchangeHealthy: Boolean = false, val lastTickEpochMs: Long = 0L,
    val lastError: String? = null, val entryPlanReasons: List<String> = emptyList(), val decisionsBySymbol: Map<String, MireiDecision> = emptyMap(),
    val snapshotsBySymbol: Map<String, MarketSnapshot> = emptyMap(), val scannerSummary: String = "",
    val buyDecisionCount: Int = 0, val holdDecisionCount: Int = 0, val sellDecisionCount: Int = 0,
    val humanVerificationRequired: Boolean = false, val humanAllowedIndicators: List<String> = emptyList(), val humanBlockedIndicators: List<String> = emptyList(),
)

data class PaperRuntimePersistence(
    val engineState: PaperEngineState, val dailyPnlIdr: Double, val consecutiveLosses: Int, val holdingsSeeded: Boolean,
    val buyDecisionCount: Int, val holdDecisionCount: Int, val sellDecisionCount: Int, val initialCapitalBySymbol: Map<String, Double> = emptyMap(),
)

class MireiPaperTradingRuntime(
    config: TradingConfig = TradingConfig(), private val marketData: PaperMarketDataSource, tradeLedger: TradeLedger? = null,
    private val symbol: String, private val exchangeId: String = "paper", private val managedSymbols: List<String> = listOf(symbol),
    private val engine: PaperExecutionEngine = PaperExecutionEngine(config, tradeLedger = tradeLedger),
    private val orchestrator: MireiOrchestrator = MireiOrchestrator(DefaultMireiAgents.create(), config.decisionMode),
    decisionEngine: MireiDecisionEngine = MireiDecisionEngine(config),
) {
    private var config = config
    private var decisionEngine = decisionEngine
    private var exitPolicy = ExitPolicy(config)
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
    private var initialHoldingProtectionPending = false
    private var lastScannerSummary = ""
    private val recentlyClosedSymbols = linkedMapOf<String, Long>()
    private var initialCapitalBySymbol: MutableMap<String, Double> = linkedMapOf()
    private var buyDecisionCount = 0
    private var holdDecisionCount = 0
    private var sellDecisionCount = 0

    fun applyRiskConfig(newConfig: TradingConfig) {
        require(newConfig.totalCapitalIdr == config.totalCapitalIdr) { "paper_capital_immutable_while_running" }
        require(newConfig.maxOpenPositions == config.maxOpenPositions) { "paper_position_limit_immutable_while_running" }
        config = newConfig; decisionEngine = MireiDecisionEngine(newConfig); exitPolicy = ExitPolicy(newConfig); engine.updateRiskTargets(newConfig)
    }

    fun seedInitialHoldings(allocations: Map<String, Double>, nowMs: Long): List<ExecutionResult> {
        if (holdingsSeeded || allocations.isEmpty()) return emptyList()
        val normalized = allocations.filter { it.key in managedSymbols && it.value > 0.0 }.toList()
        require(normalized.size <= config.maxOpenPositions) { "initial_holding_position_limit" }
        require(normalized.sumOf { it.second } <= config.totalCapitalIdr + 1e-6) { "initial_holding_exceeds_capital" }
        initialCapitalBySymbol.clear(); normalized.forEach { (managedSymbol, amount) -> initialCapitalBySymbol[managedSymbol] = amount }
        val results = mutableListOf<ExecutionResult>()
        for ((managedSymbol, amount) in normalized) {
            val snapshot = marketData.snapshot(managedSymbol) ?: continue
            if (!snapshot.dataFresh) continue
            results += engine.seedExistingHolding(exchangeId, managedSymbol, amount, snapshot.price, config.effectiveStopLossPercent(), config.effectiveTakeProfitPercent(), nowMs, config.riskReferenceMode, amount)
        }
        holdingsSeeded = results.any { it.success }
        initialHoldingProtectionPending = holdingsSeeded
        if (results.none { it.success }) lastError = "initial_holdings_not_seeded"
        return results
    }

    fun restoreState(state: PaperRuntimePersistence) {
        engine.restoreState(state.engineState); dailyPnlIdr = state.dailyPnlIdr
        consecutiveLosses = if (state.engineState.positions.isEmpty()) 0 else state.consecutiveLosses
        holdingsSeeded = state.holdingsSeeded; initialHoldingProtectionPending = false
        buyDecisionCount = state.buyDecisionCount; holdDecisionCount = state.holdDecisionCount; sellDecisionCount = state.sellDecisionCount
        initialCapitalBySymbol = state.initialCapitalBySymbol.toMutableMap(); lastError = null; tickExecutions = mutableListOf()
    }

    fun persistenceState() = PaperRuntimePersistence(engine.snapshotState(), dailyPnlIdr, consecutiveLosses, holdingsSeeded, buyDecisionCount, holdDecisionCount, sellDecisionCount, initialCapitalBySymbol.toMap())

    fun humanVerificationForm(symbol: String): Pair<List<String>, List<String>> {
        val decision = lastDecisions[symbol] ?: return emptyList<String>() to emptyList()
        return decision.observations.filter { it.action == AgentAction.BUY }.map { it.agent.name }.distinct() to decision.observations.filter { it.action != AgentAction.BUY }.map { it.agent.name }.distinct()
    }

    fun confirmHumanBuy(symbol: String, confirmedIndicators: Set<String>, nowMs: Long = System.currentTimeMillis()): PaperRuntimeStatus {
        tickExecutions = mutableListOf()
        val snapshot = lastSnapshots[symbol] ?: return status(RuntimeEnvironment(), errorOverride = "human_verification_market_unavailable")
        val decision = lastDecisions[symbol] ?: return status(RuntimeEnvironment(), errorOverride = "human_verification_no_decision")
        val allowed = decision.observations.filter { it.action == AgentAction.BUY }.map { it.agent.name }.toSet()
        if (!decision.requiresHumanDecision || allowed.isEmpty()) return status(RuntimeEnvironment(), errorOverride = "human_verification_not_required")
        if (confirmedIndicators != allowed) return status(RuntimeEnvironment(), errorOverride = "human_verification_form_incomplete")
        val markPrices = lastSnapshots.filterValues { it.dataFresh }.mapValues { it.value.price }
        val risk = RiskSnapshot(dailyPnlIdr, dailyStartBalanceIdr, engine.equityIdr(markPrices), engine.positionCount(), consecutiveLosses, snapshot.dataFresh, lastExchangeHealthy, true)
        val plan = decisionEngine.buildEntryPlan(snapshot, risk, initialCapitalBySymbol[symbol]); lastEntryPlanReasons = plan.reasons
        if (!plan.allowed) return status(RuntimeEnvironment(), errorOverride = "human_verification_risk_or_market_gate")
        if (engine.positionCount() >= config.maxOpenPositions) return status(RuntimeEnvironment(), errorOverride = "human_verification_position_limit")
        val reason = if (recentlyClosedSymbols.containsKey(symbol)) "human_verified_re_entry" else "human_verified_entry"
        val execution = engine.open(exchangeId, symbol, plan, nowMs, reason); lastExecution = execution
        if (execution.success) { tickExecutions += execution; recentlyClosedSymbols.remove(symbol) }
        lastError = if (execution.success) null else execution.error
        return status(RuntimeEnvironment(true, lastExchangeHealthy), markPrices)
    }

    fun topUp(amountIdr: Double, nowMs: Long = System.currentTimeMillis()): PaperRuntimeStatus {
        val execution = engine.topUp(amountIdr); tickExecutions = mutableListOf()
        if (execution.success) { lastExecution = execution; lastError = null; lastTickEpochMs = nowMs } else lastError = execution.error ?: "top_up_failed"
        return status(RuntimeEnvironment(true, lastExchangeHealthy))
    }

    fun tick(nowMs: Long, environment: RuntimeEnvironment = RuntimeEnvironment()): PaperRuntimeStatus = runCatching {
        tickExecutions = mutableListOf(); lastError = null; lastTickEpochMs = nowMs
        val snapshots = managedSymbols.distinct().take(3).mapNotNull { managedSymbol -> marketData.snapshot(managedSymbol)?.let { managedSymbol to it } }.toMap()
        lastSnapshots = snapshots; lastSnapshot = snapshots[symbol] ?: snapshots.values.firstOrNull(); lastExchangeHealthy = snapshots.isNotEmpty() && environment.exchangeHealthy
        if (snapshots.isEmpty()) { lastError = "market_data_unavailable"; lastEntryPlanReasons = listOf("market_data_unavailable"); lastDecision = null; return status(environment) }
        if (!environment.internetAvailable) { lastEntryPlanReasons = listOf("internet_unavailable"); return status(environment) }
        if (!environment.exchangeHealthy) { lastEntryPlanReasons = listOf("exchange_unhealthy"); return status(environment) }
        val fresh = snapshots.filterValues { it.dataFresh }
        if (fresh.isEmpty()) { lastEntryPlanReasons = listOf("market_snapshot_stale"); return status(environment) }
        val markPrices = fresh.mapValues { it.value.price }
        val tpClosedSymbols = linkedSetOf<String>(); val slClosedEntries = linkedMapOf<String, Double>()
        fresh.forEach { (managedSymbol, snapshot) -> applyTrailingProtection(managedSymbol, snapshot); closeTriggeredPositions(managedSymbol, snapshot.price, nowMs, tpClosedSymbols, slClosedEntries) }
        val riskSnapshot = RiskSnapshot(dailyPnlIdr, dailyStartBalanceIdr, engine.equityIdr(markPrices), engine.positionCount(), consecutiveLosses, fresh.size == snapshots.size, lastExchangeHealthy, environment.internetAvailable)
        val decisions = linkedMapOf<String, MireiDecision>(); val planReasons = linkedMapOf<String, List<String>>(); var lastExecutionForTick: ExecutionResult? = null

        for ((managedSymbol, snapshot) in fresh) {
            val plan = decisionEngine.buildEntryPlan(snapshot, riskSnapshot.copy(openPositions = engine.positionCount()), initialCapitalBySymbol[managedSymbol])
            planReasons[managedSymbol] = plan.reasons
            val decision = orchestrator.evaluate(snapshot); decisions[managedSymbol] = decision
            when (decision.action) { AgentAction.BUY -> buyDecisionCount++; AgentAction.HOLD -> holdDecisionCount++; AgentAction.CLOSE -> sellDecisionCount++ }

            val slEntryPrice = slClosedEntries[managedSymbol]
            if (slEntryPrice != null && engine.positionCount() < config.maxOpenPositions) {
                val risk = RiskPolicy(config).evaluate(riskSnapshot.copy(openPositions = engine.positionCount()))
                if (risk.allowedToOpen) {
                    val cycleCapital = initialCapitalBySymbol[managedSymbol]?.takeIf { it > 0.0 } ?: config.positionSizeIdr
                    val reentryPlan = buildStopLossReentryPlan(slEntryPrice, cycleCapital)
                    val execution = engine.open(exchangeId, managedSymbol, reentryPlan, nowMs, "sl_re_entry")
                    lastExecutionForTick = execution
                    if (execution.success) { tickExecutions += execution; recentlyClosedSymbols.remove(managedSymbol) }
                } else {
                    planReasons[managedSymbol] = planReasons[managedSymbol].orEmpty() + risk.reasons.map { "sl_reentry_blocked_$it" }
                }
                slClosedEntries.remove(managedSymbol); continue
            }

            if (managedSymbol in tpClosedSymbols && engine.positionCount() < config.maxOpenPositions) {
                if (decision.action == AgentAction.BUY && !decision.requiresHumanDecision && plan.allowed) {
                    val cycleCapital = initialCapitalBySymbol[managedSymbol]?.takeIf { it > 0.0 } ?: config.positionSizeIdr
                    val compoundPlan = buildTakeProfitReentryPlan(snapshot, cycleCapital)
                    val execution = engine.open(exchangeId, managedSymbol, compoundPlan, nowMs, "re_entry")
                    lastExecutionForTick = execution
                    if (execution.success) { tickExecutions += execution; recentlyClosedSymbols.remove(managedSymbol) }
                }
                tpClosedSymbols.remove(managedSymbol); continue
            }

            val protectInitialHolding = initialHoldingProtectionPending && engine.positions().any { it.symbol == managedSymbol && it.entryReason == "initial_holding" }
            if (decision.action == AgentAction.CLOSE && !decision.requiresHumanDecision && !protectInitialHolding) {
                engine.positions().filter { it.symbol == managedSymbol && it.stopLossPrice != 0.0 }.toList().forEach { position ->
                    val execution = engine.close(position.id, snapshot.price, "ai_close", nowMs)
                    if (execution.success) { recentlyClosedSymbols[managedSymbol] = nowMs; lastExecutionForTick = execution; tickExecutions += execution; dailyPnlIdr += execution.pnlIdr; consecutiveLosses = if (execution.pnlIdr < 0.0) consecutiveLosses + 1 else 0 }
                }
            } else if (engine.positionCount() < config.maxOpenPositions && decision.action == AgentAction.BUY && !decision.requiresHumanDecision && plan.allowed) {
                val entryReason = if (recentlyClosedSymbols.containsKey(managedSymbol)) "re_entry" else "entry_filled"
                val execution = engine.open(exchangeId, managedSymbol, plan, nowMs, entryReason); lastExecutionForTick = execution
                if (execution.success) { tickExecutions += execution; recentlyClosedSymbols.remove(managedSymbol) }
            }
        }
        initialHoldingProtectionPending = false
        lastDecisions = decisions; lastDecision = decisions[symbol] ?: decisions.values.firstOrNull(); lastExecution = lastExecutionForTick ?: tickExecutions.lastOrNull(); lastEntryPlanReasons = planReasons[symbol] ?: planReasons.values.firstOrNull().orEmpty()
        status(environment, markPrices)
    }.getOrElse { error ->
        lastError = error.message ?: error.javaClass.simpleName; lastEntryPlanReasons = listOf("runtime_error"); lastTickEpochMs = nowMs; lastExchangeHealthy = false; status(environment)
    }

    fun updateScannerSummary(summary: String) { lastScannerSummary = summary }

    fun closeAll(nowMs: Long, environment: RuntimeEnvironment = RuntimeEnvironment(), reason: String = "manual_close_all"): PaperRuntimeStatus {
        tickExecutions = mutableListOf(); lastTickEpochMs = nowMs; lastError = null
        if (!environment.internetAvailable || !environment.exchangeHealthy) { lastExchangeHealthy = false; lastError = "close_all_exchange_unavailable"; lastEntryPlanReasons = listOf("close_all_exchange_unavailable"); return status(environment) }
        engine.positions().toList().forEach { position ->
            val snapshot = marketData.snapshot(position.symbol)
            if (snapshot == null || !snapshot.dataFresh) { lastExchangeHealthy = false; lastError = "close_all_market_data_unavailable"; lastEntryPlanReasons = listOf("close_all_market_data_unavailable"); return@forEach }
            lastExchangeHealthy = true; close(position.id, snapshot.price, reason, nowMs)
        }
        lastExecution = tickExecutions.lastOrNull(); return status(environment)
    }

    fun status(environment: RuntimeEnvironment = RuntimeEnvironment(), markPrices: Map<String, Double> = emptyMap(), errorOverride: String? = null): PaperRuntimeStatus {
        val snapshot = lastSnapshot; val prices = if (markPrices.isNotEmpty()) markPrices else lastSnapshots.mapValues { it.value.price }; val humanDecision = lastDecision
        val humanAllowed = humanDecision?.observations?.filter { it.action == AgentAction.BUY }?.map { it.agent.name }?.distinct().orEmpty(); val humanBlocked = humanDecision?.observations?.filter { it.action != AgentAction.BUY }?.map { it.agent.name }?.distinct().orEmpty()
        return PaperRuntimeStatus(
            engine.availableBalanceIdr(), engine.equityIdr(prices), engine.positions(), lastDecision, lastExecution, tickExecutions.toList(), dailyPnlIdr, consecutiveLosses,
            snapshot?.symbol.orEmpty(), snapshot?.price ?: 0.0, snapshot?.bidPrice ?: 0.0, snapshot?.askPrice ?: 0.0, snapshot?.high24h ?: 0.0, snapshot?.low24h ?: 0.0,
            snapshot?.volume24h ?: 0.0, snapshot?.momentumPercent ?: 0.0, snapshot?.volatilityPercent ?: 0.0, snapshot?.sentimentScore ?: 0.0, snapshot?.forecastConfidence ?: 0.0,
            snapshot?.spreadPercent ?: 0.0, snapshot?.changeSinceLastTickPercent ?: 0.0, snapshot?.change1mPercent ?: 0.0, snapshot?.change5mPercent ?: 0.0, snapshot?.change15mPercent ?: 0.0,
            snapshot?.tradeFlowPercent ?: 0.0, snapshot?.trendScorePercent ?: 0.0, snapshot?.tradeCount ?: 0, snapshot?.buyVolume ?: 0.0, snapshot?.sellVolume ?: 0.0,
            snapshot?.lastTradeEpochMs ?: 0L, snapshot?.snapshotEpochMs ?: 0L, snapshot?.sourceAgeMs ?: 0L, snapshot?.dataFresh == true,
            environment.internetAvailable, lastExchangeHealthy && environment.exchangeHealthy && environment.internetAvailable, lastTickEpochMs, errorOverride ?: lastError,
            lastEntryPlanReasons, lastDecisions, lastSnapshots, lastScannerSummary, buyDecisionCount, holdDecisionCount, sellDecisionCount,
            humanDecision?.requiresHumanDecision == true && humanAllowed.isNotEmpty(), humanAllowed, humanBlocked,
        )
    }

    fun paperEngine(): PaperExecutionEngine = engine

    private fun applyTrailingProtection(managedSymbol: String, snapshot: MarketSnapshot) {
        engine.positions().filter { it.symbol == managedSymbol && it.stopLossPrice != 0.0 }.forEach { position ->
            val initialStop = (2.0 * position.entryPrice - position.trailingActivationPrice).coerceAtLeast(0.00000001)
            val plan = exitPolicy.evaluate(position.entryPrice, snapshot.price, initialStop, position.takeProfitPrice, snapshot.volatilityPercent, null)
            if (plan.trailingStopPrice != null && plan.breakevenApplied) engine.updateTrailingStop(position.id, plan.trailingStopPrice)
        }
    }

    private fun closeTriggeredPositions(managedSymbol: String, marketPrice: Double, nowMs: Long, tpClosedSymbols: MutableSet<String>, slClosedEntries: MutableMap<String, Double>) {
        engine.positions().filter { it.symbol == managedSymbol }.forEach { position ->
            val reason = when { position.stopLossPrice != 0.0 && marketPrice <= position.stopLossPrice -> "stop_loss"; marketPrice >= position.takeProfitPrice -> "take_profit"; else -> null } ?: return@forEach
            val reentryAnchor = position.stopLossPrice
            val result = engine.close(position.id, marketPrice, reason, nowMs); if (!result.success) return@forEach
            dailyPnlIdr += result.pnlIdr; consecutiveLosses = if (result.pnlIdr < 0.0) consecutiveLosses + 1 else 0; lastExecution = result; tickExecutions += result; recentlyClosedSymbols[managedSymbol] = nowMs
            if (reason == "take_profit") {
                val previousCycleCapital = initialCapitalBySymbol[managedSymbol]?.takeIf { it > 0.0 } ?: position.stakeIdr
                initialCapitalBySymbol[managedSymbol] = maxOf(position.stakeIdr, previousCycleCapital + result.pnlIdr); tpClosedSymbols += managedSymbol
            } else if (reason == "stop_loss" && reentryAnchor > 0.0) {
                slClosedEntries[managedSymbol] = reentryAnchor
            }
        }
    }

    private fun buildStopLossReentryPlan(entryPrice: Double, cycleCapital: Double): EntryPlan {
        val stake = cycleCapital.coerceAtMost(engine.availableBalanceIdr()).coerceAtLeast(0.0)
        if (stake <= 0.0 || entryPrice <= 0.0) return EntryPlan(false, entryPrice, 0.0, 0.0, 0.0, 0.0, listOf("sl_reentry_insufficient_cash"), config.riskReferenceMode, cycleCapital)
        val targets = config.calculateRiskTargets(entryPrice, stake, cycleCapital, config.effectiveStopLossPercent(), config.effectiveTakeProfitPercent())
        val activation = entryPrice + (entryPrice - targets.stopLossPrice) * config.trailingActivationR
        return EntryPlan(true, entryPrice, targets.stopLossPrice, targets.takeProfitPrice, activation, stake, listOf("sl_reentry_from_last_stop"), config.riskReferenceMode, targets.referenceCapitalIdr)
    }

    private fun buildTakeProfitReentryPlan(snapshot: MarketSnapshot, cycleCapital: Double): EntryPlan {
        val stake = cycleCapital.coerceAtMost(engine.availableBalanceIdr()).coerceAtLeast(0.0)
        if (stake <= 0.0) return EntryPlan(false, snapshot.price, 0.0, 0.0, 0.0, 0.0, listOf("tp_compound_insufficient_cash"), config.riskReferenceMode, cycleCapital)
        val targets = config.calculateRiskTargets(snapshot.price, stake, cycleCapital, config.effectiveStopLossPercent(), config.effectiveTakeProfitPercent())
        val activation = snapshot.price + (snapshot.price - targets.stopLossPrice) * config.trailingActivationR
        return EntryPlan(true, snapshot.price, targets.stopLossPrice, targets.takeProfitPrice, activation, stake, listOf("tp_compound_reentry"), config.riskReferenceMode, targets.referenceCapitalIdr)
    }

    private fun close(positionId: String, marketPrice: Double, reason: String, nowMs: Long) {
        val result = engine.close(positionId, marketPrice, reason, nowMs); if (!result.success) return
        dailyPnlIdr += result.pnlIdr; consecutiveLosses = if (result.pnlIdr < 0.0) consecutiveLosses + 1 else 0; lastExecution = result; tickExecutions += result
    }
}
