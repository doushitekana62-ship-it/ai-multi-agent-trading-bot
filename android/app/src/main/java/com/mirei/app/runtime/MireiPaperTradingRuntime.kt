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
        require(allocations.values.fold(0.0) { acc, value -> acc + value } <= config.totalCapitalIdr + 1e-6) { "allocation_exceeds_session_capital" }

        val snapshots = linkedMapOf<String, MarketSnapshot>()
        allocations.forEach { (managedSymbol, amount) ->
            val instrument = TradingUniverse.bySymbol(managedSymbol) ?: throw IllegalStateException("instrument_not_supported:" + managedSymbol)
            if (amount < instrument.executionCosts.minimumOrderIdr - 1e-6) throw IllegalStateException("initial_buy_below_minimum:" + managedSymbol + ":" + instrument.executionCosts.minimumOrderIdr)
            if (!marketSessionOpen(instrument)) throw IllegalStateException("market_session_closed:" + managedSymbol)
            val snapshot = runCatching { marketData.snapshot(managedSymbol) }.getOrNull() ?: throw IllegalStateException("market_data_unavailable:" + managedSymbol)
            if (snapshot.price <= 0.0) throw IllegalStateException("invalid_market_price:" + managedSymbol)
            if (!snapshot.dataFresh) throw IllegalStateException("market_data_stale:" + managedSymbol + ":" + snapshot.sourceAgeMs + "ms")
            val decision = decisionEngine.decideInitialEntry(snapshot, amount, amount, cycleId(managedSymbol, nowMs))
            recordDecision(decision)
            if (decision.action != MireiDecisionAction.INITIAL_BUY) throw IllegalStateException("initial_buy_decision_rejected:" + managedSymbol + ":" + decision.reason)
            snapshots[managedSymbol] = snapshot
        }

        val beforeState = engine.snapshotState()
        val results = mutableListOf<ExecutionResult>()
        val created = mutableListOf<PaperPosition>()
        try {
            allocations.forEach { (managedSymbol, amount) ->
                val snapshot = snapshots.getValue(managedSymbol)
                val pc = config.forPosition(managedSymbol)
                val plan = decisionEngine.buildEntryPlan(snapshot, amount, amount)
                require(plan.allowed) { "initial_buy_plan_invalid:" + managedSymbol }
                val result = engine.seedExistingHolding(
                    exchangeId, managedSymbol, amount, snapshot.price,
                    pc.effectiveStopLossPercent(), pc.effectiveTakeProfitPercent(),
                    nowMs, pc.riskReferenceMode, amount, recordLedger = false
                )
                if (!result.success) throw IllegalStateException("initial_buy_failed:" + managedSymbol + ":" + (result.error ?: result.reason ?: "unknown"))
                results += result
                result.orderId?.let { engine.position(it)?.let(created::add) }
            }
        } catch (failure: Throwable) {
            engine.restoreState(beforeState)
            pendingReentries.clear()
            cycles.clear()
            initialCapitalBySymbol.clear()
            throw failure
        }

        created.forEach { position -> engine.recordOpenedPosition(position.id) }
        initialCapitalBySymbol.clear()
        initialCapitalBySymbol.putAll(allocations)
        created.forEach { position ->
            val id = cycleId(position.symbol, nowMs)
            cycles[position.symbol] = MireiCycle(
                id, position.symbol, allocations[position.symbol] ?: position.stakeIdr,
                position.entryPrice, 0, 1, MireiCycleState.HOLDING,
                MireiDecisionAction.INITIAL_BUY, "initial_buy_filled", nowMs
            )
            recordDecision(MireiDecision(MireiDecisionAction.HOLD, position.symbol, "hold_until_sl_tp", id, 1, position.riskReferenceCapitalIdr))
        }
        holdingsSeeded = results.size == allocations.size && results.all { it.success } && engine.positionCount() > 0
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
        cycles.clear()
        cycles.putAll(state.mireiCycles)
        cycles.values.filter { it.state == MireiCycleState.REENTRY_WAIT }.forEach { cycle ->
            pendingReentries[cycle.symbol] = PendingReentry(cycle.cycleId, cycle.initialCapitalIdr, cycle.initialBuyPrice, null, cycle.sequence)
        }
        lastExecution = null
        tickExecutions = mutableListOf()
        lastError = null
        lastDecision = null
        tickDecisions.clear()
    }

    fun persistenceState() = PaperRuntimePersistence(
        engineState = engine.snapshotState(),
        dailyPnlIdr = dailyPnlIdr,
        consecutiveLosses = consecutiveLosses,
        holdingsSeeded = holdingsSeeded,
        initialCapitalBySymbol = initialCapitalBySymbol.toMap(),
        mireiCycles = cycles.toMap(),
    )

    fun tick(nowMs: Long, environment: RuntimeEnvironment = RuntimeEnvironment()): PaperRuntimeStatus = runCatching {
        tickExecutions = mutableListOf()
        tickDecisions.clear()
        lastError = null
        lastTickEpochMs = nowMs
        if (!environment.internetAvailable) { lastError = "internet_unavailable"; return status(environment) }
        if (!environment.exchangeHealthy) { lastError = "exchange_unavailable"; return status(environment) }
        if (engine.positionCount() == 0) {
            lastError = if (pendingReentries.isNotEmpty()) "reentry_pending" else "no_active_positions"
            return status(environment)
        }

        val snapshots = linkedMapOf<String, MarketSnapshot>()
        managedSymbols.distinct().take(config.maxOpenPositions).forEach { managedSymbol ->
            val snapshot = runCatching { marketData.snapshot(managedSymbol) }.getOrNull()
            if (snapshot != null) snapshots[managedSymbol] = snapshot
            else lastError = "market_data_unavailable:" + managedSymbol
        }
        lastSnapshots = snapshots
        lastSnapshot = snapshots[symbol] ?: snapshots.values.firstOrNull()
        lastExchangeHealthy = snapshots.isNotEmpty()
        if (snapshots.isEmpty()) { lastError = "market_data_unavailable"; return status(environment) }

        snapshots.forEach { (managedSymbol, snapshot) ->
            val position = engine.positions().firstOrNull { it.symbol == managedSymbol } ?: return@forEach
            val cycle = cycles[managedSymbol]
            val decision = decisionEngine.decidePosition(
                snapshot, position,
                cycle?.cycleId ?: cycleId(managedSymbol, position.openedAtEpochMs),
                cycle?.sequence ?: 1
            )
            recordDecision(decision)
            if (snapshot.dataFresh && marketSessionOpen(TradingUniverse.bySymbol(managedSymbol))) {
                executeExitDecision(managedSymbol, snapshot.price, nowMs, position, decision)
            } else if (!snapshot.dataFresh) {
                lastError = "market_data_stale:" + managedSymbol + ":" + snapshot.sourceAgeMs + "ms"
            } else {
                lastError = "market_session_closed:" + managedSymbol
            }
        }

        snapshots.forEach { (managedSymbol, snapshot) ->
            if (!snapshot.dataFresh || !marketSessionOpen(TradingUniverse.bySymbol(managedSymbol))) return@forEach
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
            mireiDecisions = tickDecisions.toList(),
            mireiCycles = cycles.toMap(),
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

    private fun executeExitDecision(symbol: String, marketPrice: Double, nowMs: Long, position: PaperPosition, decision: MireiDecision) {
        if (decision.action != MireiDecisionAction.SELL_STOP_LOSS && decision.action != MireiDecisionAction.SELL_TAKE_PROFIT) return
        val reason = if (decision.action == MireiDecisionAction.SELL_STOP_LOSS) "stop_loss" else "take_profit"
        val result = engine.close(position.id, marketPrice, reason, nowMs)
        if (!result.success) {
            lastError = "sell_failed:" + symbol + ":" + (result.error ?: "unknown")
            return
        }
        tickExecutions += result
        lastExecution = result
        dailyPnlIdr += result.pnlIdr
        consecutiveLosses = if (result.pnlIdr < 0.0) consecutiveLosses + 1 else 0
        cycles[symbol]?.let { cycle ->
            val nextSequence = cycle.sequence + 1
            cycles[symbol] = cycle.copy(
                state = MireiCycleState.REENTRY_WAIT,
                lastDecision = decision.action,
                lastDecisionReason = decision.reason,
                sequence = nextSequence,
                lastTransitionAtEpochMs = nowMs
            )
            pendingReentries[symbol] = PendingReentry(
                cycle.cycleId, cycle.initialCapitalIdr, cycle.initialBuyPrice, position.positionProfile, nextSequence
            )
        }
    }

    private fun tryReentry(managedSymbol: String, snapshot: MarketSnapshot, nowMs: Long) {
        val pending = pendingReentries[managedSymbol] ?: return
        val cycle = cycles[managedSymbol] ?: return
        if (cycle.state != MireiCycleState.REENTRY_WAIT) return
        if (engine.positionCount() >= config.maxOpenPositions) return
        val available = engine.availableBalanceIdr()
        val decision = decisionEngine.decideReentry(
            snapshot, pending.cycleId, pending.sequence, pending.cycleCapitalIdr, available
        )
        recordDecision(decision)
        if (decision.action != MireiDecisionAction.REENTRY_BUY) {
            lastError = "reentry_wait:" + managedSymbol + ":" + decision.reason
            cycles[managedSymbol] = cycle.copy(
                state = MireiCycleState.REENTRY_WAIT,
                lastDecision = decision.action,
                lastDecisionReason = decision.reason,
                lastTransitionAtEpochMs = nowMs
            )
            return
        }
        val cycleCapital = pending.cycleCapitalIdr.coerceAtMost(available)
        val plan = decisionEngine.buildEntryPlan(snapshot, pending.cycleCapitalIdr, cycleCapital)
        if (!plan.allowed) {
            lastError = "reentry_plan_rejected:" + managedSymbol
            return
        }
        cycles[managedSymbol] = cycle.copy(
            state = MireiCycleState.REENTRY_PENDING,
            lastDecision = MireiDecisionAction.REENTRY_BUY,
            lastDecisionReason = "reentry_execution_pending",
            lastTransitionAtEpochMs = nowMs
        )
        val result = engine.open(exchangeId, managedSymbol, plan, nowMs, "re_entry")
        lastExecution = result
        if (result.success) {
            tickExecutions += result
            pendingReentries.remove(managedSymbol)
            cycles[managedSymbol] = cycle.copy(
                state = MireiCycleState.HOLDING,
                reentryCount = cycle.reentryCount + 1,
                sequence = pending.sequence + 1,
                lastDecision = MireiDecisionAction.REENTRY_BUY,
                lastDecisionReason = "reentry_buy_filled",
                lastTransitionAtEpochMs = nowMs
            )
            recordDecision(
                MireiDecision(
                    MireiDecisionAction.HOLD,
                    managedSymbol,
                    "hold_until_sl_tp_after_reentry",
                    cycle.cycleId,
                    pending.sequence + 1,
                    pending.cycleCapitalIdr
                )
            )
        } else {
            cycles[managedSymbol] = cycle.copy(
                state = MireiCycleState.REENTRY_WAIT,
                lastDecision = MireiDecisionAction.REENTRY_WAIT,
                lastDecisionReason = result.error ?: result.reason ?: "reentry_failed",
                lastTransitionAtEpochMs = nowMs
            )
            lastError = "reentry_failed:" + managedSymbol + ":" + (result.error ?: result.reason ?: "unknown")
        }
    }

    private fun recordDecision(decision: MireiDecision) {
        lastDecision = decision
        tickDecisions += decision
    }

    private fun cycleId(symbol: String, atMs: Long): String =
        "cycle-" + symbol.replace('/', '_').replace('=', '_') + "-" + atMs

    private fun marketSessionOpen(instrument: com.mirei.app.core.MarketInstrument?): Boolean {
        if (instrument == null) return false
        if (instrument.assetClass == com.mirei.app.core.AssetClass.CRYPTO) return true
        val now = java.time.ZonedDateTime.now(java.time.ZoneId.of("America/New_York"))
        if (now.dayOfWeek == java.time.DayOfWeek.SATURDAY || now.dayOfWeek == java.time.DayOfWeek.SUNDAY) return false
        return when (instrument.tradingHours) {
            "US session" -> !now.toLocalTime().isBefore(java.time.LocalTime.of(9, 30)) &&
                now.toLocalTime().isBefore(java.time.LocalTime.of(16, 0))
            else -> true
        }
    }
}
