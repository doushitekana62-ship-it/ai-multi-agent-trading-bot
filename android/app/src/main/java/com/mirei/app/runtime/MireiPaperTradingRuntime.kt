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
    val marketPrice: Double = 0.0,
    val marketDataFresh: Boolean = false,
    val internetAvailable: Boolean = false,
    val exchangeHealthy: Boolean = false,
    val lastTickEpochMs: Long = 0L,
    val lastError: String? = null,
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

    fun tick(nowMs: Long, environment: RuntimeEnvironment = RuntimeEnvironment()): PaperRuntimeStatus =
        runCatching {
            lastError = null
            lastTickEpochMs = nowMs
            val snapshot = marketData.snapshot(symbol)
            lastSnapshot = snapshot
            lastExchangeHealthy = snapshot != null && environment.exchangeHealthy
            if (snapshot == null) {
                lastError = "market_data_unavailable"
                return status(environment)
            }
            if (!environment.internetAvailable) return status(environment)
            if (!environment.exchangeHealthy) return status(environment)
            if (!snapshot.dataFresh) return status(environment)

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
            val decision = orchestrator.evaluate(snapshot)
            lastDecision = decision
            if (engine.positionCount() == 0 && decision.action == AgentAction.BUY && !decision.requiresHumanDecision && plan.allowed) {
                lastExecution = engine.open("paper", symbol, plan, nowMs)
            } else {
                lastExecution = null
            }
            status(environment, markPrices)
        }.getOrElse { error ->
            lastError = error.message ?: error.javaClass.simpleName
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
            return status(environment)
        }

        val positions = engine.positions()
        for (position in positions) {
            val snapshot = marketData.snapshot(position.symbol)
            if (snapshot == null || !snapshot.dataFresh) {
                lastExchangeHealthy = false
                lastError = "close_all_market_data_unavailable"
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
            marketPrice = snapshot?.price ?: 0.0,
            marketDataFresh = snapshot?.dataFresh == true,
            internetAvailable = environment.internetAvailable,
            exchangeHealthy = lastExchangeHealthy && environment.exchangeHealthy && environment.internetAvailable,
            lastTickEpochMs = lastTickEpochMs,
            lastError = lastError,
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
