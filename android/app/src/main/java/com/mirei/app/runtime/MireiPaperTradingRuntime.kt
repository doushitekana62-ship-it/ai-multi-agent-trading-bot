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
    val lastError: String? = null,
)

/**
 * Application-level paper trading pipeline. No live exchange or API credentials are used here.
 * The market-data source is injected so Android can later connect a real-time adapter safely.
 */
class MireiPaperTradingRuntime(
    private val config: TradingConfig = TradingConfig(),
    private val marketData: PaperMarketDataSource,
    tradeLedger: TradeLedger? = null,
    private val symbol: String,
    private val engine: PaperExecutionEngine = PaperExecutionEngine(config, tradeLedger = tradeLedger),
    private val orchestrator: MireiOrchestrator = MireiOrchestrator(
        DefaultMireiAgents.create(),
        config.decisionMode,
    ),
    private val decisionEngine: MireiDecisionEngine = MireiDecisionEngine(config),
) {
    private val dailyStartBalanceIdr = config.totalCapitalIdr
    private var dailyPnlIdr = 0.0
    private var consecutiveLosses = 0
    private var lastDecision: MireiDecision? = null
    private var lastExecution: ExecutionResult? = null
    private var lastError: String? = null

    fun tick(nowMs: Long, environment: RuntimeEnvironment = RuntimeEnvironment()): PaperRuntimeStatus {
        return runCatching {
            lastError = null
            val snapshot = marketData.snapshot(symbol)
            if (snapshot == null) return status(emptyMap())

            if (!environment.internetAvailable) return status(mapOf(symbol to snapshot.price))
            if (!environment.exchangeHealthy) return status(mapOf(symbol to snapshot.price))
            if (!snapshot.dataFresh) return status(mapOf(symbol to snapshot.price))

            val markPrices = mapOf(symbol to snapshot.price)
            closeTriggeredPositions(snapshot.price, nowMs)

            val riskSnapshot = RiskSnapshot(
                dailyPnlIdr = dailyPnlIdr,
                dailyStartBalanceIdr = dailyStartBalanceIdr,
                equityIdr = engine.equityIdr(markPrices),
                openPositions = engine.positionCount(),
                consecutiveLosses = consecutiveLosses,
                marketDataFresh = snapshot.dataFresh,
                exchangeHealthy = environment.exchangeHealthy,
                internetAvailable = environment.internetAvailable,
            )
            val plan = decisionEngine.buildEntryPlan(snapshot, riskSnapshot)
            val decision = orchestrator.evaluate(snapshot)
            lastDecision = decision

            if (decision.action == AgentAction.BUY && !decision.requiresHumanDecision && plan.allowed) {
                lastExecution = engine.open("paper", symbol, plan, nowMs)
            } else {
                lastExecution = null
            }
            status(markPrices)
        }.getOrElse { error ->
            lastError = error.message ?: error.javaClass.simpleName
            status(emptyMap())
        }
    }

    fun closeAll(nowMs: Long, reason: String = "manual_close_all"): PaperRuntimeStatus {
        engine.positions().forEach { position ->
            val snapshot = marketData.snapshot(position.symbol) ?: return@forEach
            close(position.id, snapshot.price, reason, nowMs)
        }
        return status(emptyMap())
    }

    fun status(markPrices: Map<String, Double> = emptyMap()): PaperRuntimeStatus = PaperRuntimeStatus(
        availableBalanceIdr = engine.availableBalanceIdr(),
        equityIdr = engine.equityIdr(markPrices),
        activePositions = engine.positions(),
        lastDecision = lastDecision,
        lastExecution = lastExecution,
        dailyPnlIdr = dailyPnlIdr,
        consecutiveLosses = consecutiveLosses,
        lastError = lastError,
    )

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
