package com.mirei.app.runtime

import com.mirei.app.core.EntryPlan
import com.mirei.app.core.MireiCycle
import com.mirei.app.core.MireiCycleState
import com.mirei.app.core.MireiDecision
import com.mirei.app.core.MireiDecisionAction
import com.mirei.app.core.MireiDecisionEngine
import com.mirei.app.core.MarketSnapshot
import com.mirei.app.core.PositionTradeConfig
import com.mirei.app.core.TradingConfig
import com.mirei.app.core.TradingUniverse
import com.mirei.app.execution.ExecutionResult
import com.mirei.app.execution.PaperEngineState
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
    val lastExecution: ExecutionResult?,
    val recentExecutions: List<ExecutionResult> = emptyList(),
    val dailyPnlIdr: Double,
    val marketSymbol: String = "",
    val marketPrice: Double = 0.0,
    val marketDataFresh: Boolean = false,
    val internetAvailable: Boolean = false,
    val exchangeHealthy: Boolean = false,
    val lastTickEpochMs: Long = 0L,
    val lastError: String? = null,
    val initialCapitalBySymbol: Map<String, Double> = emptyMap(),
    val mireiDecisions: List<MireiDecision> = emptyList(),
    val mireiCycles: Map<String, MireiCycle> = emptyMap(),
)

data class PaperRuntimePersistence(
    val engineState: PaperEngineState,
    val dailyPnlIdr: Double,
    val consecutiveLosses: Int,
    val holdingsSeeded: Boolean,
    val buyDecisionCount: Int = 0,
    val holdDecisionCount: Int = 0,
    val sellDecisionCount: Int = 0,
    val initialCapitalBySymbol: Map<String, Double> = emptyMap(),
    val mireiCycles: Map<String, MireiCycle> = emptyMap(),
)

private data class PendingReentry(
    val cycleId: String,
    val cycleCapitalIdr: Double,
    val initialBuyPrice: Double,
    val positionProfile: PositionTradeConfig?,
    val sequence: Int,
)

class MireiPaperTradingRuntime(
    config: TradingConfig = TradingConfig(),
    private val marketData: PaperMarketDataSource,
    tradeLedger: TradeLedger? = null,
    private val symbol: String,
    private val exchangeId: String = "paper",
    private val managedSymbols: List<String> = listOf(symbol),
    private val engine: PaperExecutionEngine = PaperExecutionEngine(config, tradeLedger = tradeLedger, useInstrumentCosts = true),
    decisionEngine: MireiDecisionEngine = MireiDecisionEngine(config),
) {
    private var config = config
    private var decisionEngine = decisionEngine
    private val dailyStartBalanceIdr = config.totalCapitalIdr
    private var dailyPnlIdr = 0.0
    private var consecutiveLosses = 0
    private var lastExecution: ExecutionResult? = null
    private var tickExecutions = mutableListOf<ExecutionResult>()
    private var lastError: String? = null
    private var lastSnapshot: MarketSnapshot? = null
    private var lastSnapshots: Map<String, MarketSnapshot> = emptyMap()
    private var lastTickEpochMs = 0L
    private var lastExchangeHealthy = false
    private var holdingsSeeded = false
    private var initialCapitalBySymbol: MutableMap<String, Double> = linkedMapOf()
    private val pendingReentries = linkedMapOf<String, PendingReentry>()
    private val cycles = linkedMapOf<String, MireiCycle>()
    private var lastDecision: MireiDecision? = null
    private val tickDecisions = mutableListOf<MireiDecision>()

    fun applyRiskConfig(newConfig: TradingConfig) {
        require(newConfig.totalCapitalIdr == config.totalCapitalIdr) { "paper_capital_immutable_while_running" }
        require(newConfig.maxOpenPositions == config.maxOpenPositions) { "paper_position_limit_immutable_while_running" }
        config = newConfig
        decisionEngine = MireiDecisionEngine(newConfig)
        engine.updateRiskTargets(newConfig)
    }

    fun seedInitialHoldings(allocations: Map<String, Double>, nowMs: Long): List<ExecutionResult> {
        if (holdingsSeeded || allocations.isEmpty()) return emptyList()
        require(allocations.size <= config.maxOpenPositions) { "initial_holding_position_limit" }
        require(allocations.values.fold(0.0) { acc, value -> acc + value } <= config.totalCapitalIdr + 1e-6) {
            "allocation_exceeds_session_capital"
        }

        val snapshots = linkedMapOf<String, MarketSnapshot>()
        allocations.forEach { (managedSymbol, amount) ->
            val instrument = TradingUniverse.bySymbol(managedSymbol)
                ?: throw IllegalStateException("instrument_not_supported:" + managedSymbol)
            if (amount < instrument.executionCosts.minimumOrderIdr - 1e-6) {
                throw IllegalStateException("initial_buy_below_minimum:" + managedSymbol + ":" + instrument.executionCosts.minimumOrderIdr)
            }
            val snapshot = runCatching { marketData.snapshot(managedSymbol) }.getOrNull()
                ?: throw IllegalStateException("market_data_unavailable:" + managedSymbol)
            if (snapshot.price <= 0.0) {
                throw IllegalStateException("invalid_market_price:" + managedSymbol)
            }
            if (!snapshot.dataFresh) {
                throw IllegalStateException("market_data_stale:" + managedSymbol + ":" + snapshot.sourceAgeMs + "ms")
            }
            snapshots[managedSymbol] = snapshot
        }

        initialCapitalBySymbol.clear()
        initialCapitalBySymbol.putAll(allocations)
        val results = mutableListOf<ExecutionResult>()
        allocations.forEach { (managedSymbol, amount) ->
            val snapshot = snapshots.getValue(managedSymbol)
            val pc = config.forPosition(managedSymbol)
            val result = engine.seedExistingHolding(
                exchangeId,
                managedSymbol,
                amount,
                snapshot.price,
                pc.effectiveStopLossPercent(),
                pc.effectiveTakeProfitPercent(),
                nowMs,
                pc.riskReferenceMode,
                amount,
            )
            if (!result.success) {
                throw IllegalStateException("initial_buy_failed:" + managedSymbol + ":" + (result.error ?: result.reason ?: "unknown"))
            }
            results += result
        }

        holdingsSeeded = results.size == allocations.size && results.all { it.success }
        if (!holdingsSeeded) throw IllegalStateException("initial_position_not_created")
        return results
    }
    fun restoreState(state: PaperRuntimePersistence) {
        engine.restoreState(state.engineState)
        dailyPnlIdr = state.dailyPnlIdr
        consecutiveLosses = state.consecutiveLosses
        holdingsSeeded = state.holdingsSeeded
        initialCapitalBySymbol = state.initialCapitalBySymbol.toMutableMap()
        pendingReentries.clear()
        lastExecution = null
        tickExecutions = mutableListOf()
        lastError = null
    }

    fun persistenceState() = PaperRuntimePersistence(
        engineState = engine.snapshotState(),
        dailyPnlIdr = dailyPnlIdr,
        consecutiveLosses = consecutiveLosses,
        holdingsSeeded = holdingsSeeded,
        initialCapitalBySymbol = initialCapitalBySymbol.toMap(),
    )

    fun tick(nowMs: Long, environment: RuntimeEnvironment = RuntimeEnvironment()): PaperRuntimeStatus = runCatching {
        tickExecutions = mutableListOf()
        lastError = null
        lastTickEpochMs = nowMs

        if (!environment.internetAvailable) {
            lastError = "internet_unavailable"
            return status(environment)
        }
        if (!environment.exchangeHealthy) {
            lastError = "exchange_unavailable"
            return status(environment)
        }

        val snapshots = managedSymbols.distinct().take(config.maxOpenPositions).mapNotNull { managedSymbol ->
            marketData.snapshot(managedSymbol)?.let { managedSymbol to it }
        }.toMap()
        lastSnapshots = snapshots
        lastSnapshot = snapshots[symbol] ?: snapshots.values.firstOrNull()
        lastExchangeHealthy = snapshots.isNotEmpty()

        if (snapshots.isEmpty()) {
            lastError = "market_data_unavailable"
            return status(environment)
        }

        snapshots.forEach { (managedSymbol, snapshot) ->
            if (snapshot.dataFresh) closeTriggeredPositions(managedSymbol, snapshot.price, nowMs)
        }

        snapshots.forEach { (managedSymbol, snapshot) ->
            if (!snapshot.dataFresh) return@forEach
            tryReentry(managedSymbol, snapshot, nowMs)
        }

        status(environment)
    }.getOrElse {
        lastError = it.message ?: it.javaClass.simpleName
        lastTickEpochMs = nowMs
        status(environment)
    }

    fun closeAll(
        nowMs: Long,
        environment: RuntimeEnvironment = RuntimeEnvironment(),
        reason: String = "manual_close_all",
    ): PaperRuntimeStatus {
        tickExecutions = mutableListOf()
        if (!environment.internetAvailable || !environment.exchangeHealthy) {
            lastError = "close_all_exchange_unavailable"
            return status(environment)
        }
        engine.positions().toList().forEach { position ->
            val snapshot = marketData.snapshot(position.symbol)
            if (snapshot == null || !snapshot.dataFresh) return@forEach
            val result = engine.close(position.id, snapshot.price, reason, nowMs)
            if (result.success) {
                tickExecutions += result
                lastExecution = result
                dailyPnlIdr += result.pnlIdr
                if (result.pnlIdr < 0.0) consecutiveLosses++
                else consecutiveLosses = 0
                pendingReentries.remove(position.symbol)
            }
        }
        return status(environment)
    }

    fun status(environment: RuntimeEnvironment = RuntimeEnvironment()): PaperRuntimeStatus {
        val snapshot = lastSnapshot
        val prices = lastSnapshots.mapValues { it.value.price }
        return PaperRuntimeStatus(
            availableBalanceIdr = engine.availableBalanceIdr(),
            equityIdr = engine.equityIdr(prices),
            activePositions = engine.positions(),
            lastExecution = lastExecution,
            recentExecutions = tickExecutions.toList(),
            dailyPnlIdr = dailyPnlIdr,
            marketSymbol = snapshot?.symbol.orEmpty(),
            marketPrice = snapshot?.price ?: 0.0,
            marketDataFresh = snapshot?.dataFresh == true,
            internetAvailable = environment.internetAvailable,
            exchangeHealthy = lastExchangeHealthy && environment.exchangeHealthy,
            lastTickEpochMs = lastTickEpochMs,
            lastError = lastError,
            initialCapitalBySymbol = initialCapitalBySymbol.toMap(),
        )
    }

    fun topUp(amountIdr: Double): PaperRuntimeStatus {
        val execution = engine.topUp(amountIdr)
        tickExecutions = mutableListOf()
        lastExecution = execution
        lastError = execution.error
        return status(RuntimeEnvironment())
    }

    fun paperEngine(): PaperExecutionEngine = engine

    private fun closeTriggeredPositions(managedSymbol: String, marketPrice: Double, nowMs: Long) {
        engine.positions().filter { it.symbol == managedSymbol }.toList().forEach { position ->
            val reason = when {
                position.stopLossPrice > 0.0 && marketPrice <= position.stopLossPrice -> "stop_loss"
                position.takeProfitPrice > 0.0 && marketPrice >= position.takeProfitPrice -> "take_profit"
                else -> null
            } ?: return@forEach

            val result = engine.close(position.id, marketPrice, reason, nowMs)
            if (!result.success) return@forEach
            tickExecutions += result
            lastExecution = result
            dailyPnlIdr += result.pnlIdr
            consecutiveLosses = if (result.pnlIdr < 0.0) consecutiveLosses + 1 else 0
            pendingReentries[managedSymbol] = PendingReentry(
                cycleCapitalIdr = initialCapitalBySymbol[managedSymbol]?.takeIf { it > 0.0 } ?: position.riskReferenceCapitalIdr.takeIf { it > 0.0 } ?: position.stakeIdr,
                positionProfile = position.positionProfile,
            )
        }
    }

    private fun tryReentry(managedSymbol: String, snapshot: MarketSnapshot, nowMs: Long) {
        val pending = pendingReentries[managedSymbol] ?: return
        if (engine.positionCount() >= config.maxOpenPositions) return
        val cycleCapital = pending.cycleCapitalIdr.coerceAtMost(engine.availableBalanceIdr())
        if (cycleCapital <= 0.0) return

        val plan = decisionEngine.buildEntryPlan(
            snapshot = snapshot,
            initialCapitalIdr = pending.cycleCapitalIdr,
            stakeOverrideIdr = cycleCapital,
        )
        if (!plan.allowed) return

        val result = engine.open(exchangeId, managedSymbol, plan, nowMs, "re_entry")
        lastExecution = result
        if (result.success) {
            tickExecutions += result
            pendingReentries.remove(managedSymbol)
        }
    }
}
