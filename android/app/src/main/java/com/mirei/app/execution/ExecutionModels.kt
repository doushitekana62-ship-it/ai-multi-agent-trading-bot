package com.mirei.app.execution

import com.mirei.app.core.EntryPlan
import com.mirei.app.core.RiskReferenceMode
import com.mirei.app.core.TradingConfig

interface ExchangeAdapter {
    val exchangeId: String
    suspend fun fetchPrice(symbol: String): Double
    suspend fun placeMarketBuy(symbol: String, quoteAmount: Double): ExecutionResult
    suspend fun placeLimitBuy(symbol: String, quoteAmount: Double, limitPrice: Double): ExecutionResult
    suspend fun closePosition(positionId: String, reason: String): ExecutionResult
}

data class ExecutionResult(
    val success: Boolean,
    val orderId: String? = null,
    val filledAmount: Double = 0.0,
    val averagePrice: Double = 0.0,
    val fee: Double = 0.0,
    val entryFee: Double = 0.0,
    val exitFee: Double = 0.0,
    val slippagePercent: Double = 0.0,
    val pnlIdr: Double = 0.0,
    val remainingBalanceIdr: Double = 0.0,
    val reason: String? = null,
    val error: String? = null,
    val balanceBeforeIdr: Double = 0.0,
)

data class PaperPosition(
    val id: String,
    val exchangeId: String,
    val symbol: String,
    val stakeIdr: Double,
    val entryPrice: Double,
    val stopLossPrice: Double,
    val takeProfitPrice: Double,
    val trailingActivationPrice: Double,
    val openedAtEpochMs: Long,
    val entryReason: String = "entry_filled",
    val riskReferenceMode: RiskReferenceMode = RiskReferenceMode.ENTRY_PRICE,
    val riskReferenceCapitalIdr: Double = 0.0,
)

data class PaperLimitOrder(val id: String, val exchangeId: String, val symbol: String, val quoteAmount: Double, val limitPrice: Double, val reservedIdr: Double, val createdAtEpochMs: Long)

data class PaperEngineState(
    val availableBalanceIdr: Double,
    val positions: List<PaperPosition>,
)

class PaperExecutionEngine(
    private val config: TradingConfig = TradingConfig(),
    private val feePercent: Double = 0.3,
    private val slippagePercent: Double = 0.05,
    private val tradeLedger: TradeLedger? = null,
) {
    private var availableBalanceIdr = config.totalCapitalIdr
    private val positions = linkedMapOf<String, PaperPosition>()
    private val limitOrders = linkedMapOf<String, PaperLimitOrder>()
    private var positionSequence = 0L

    init { require(feePercent >= 0.0); require(slippagePercent >= 0.0) }

    fun seedExistingHolding(
        exchangeId: String,
        symbol: String,
        quoteAmount: Double,
        marketPrice: Double,
        stopLossPercent: Double,
        takeProfitPercent: Double,
        nowMs: Long,
        riskReferenceMode: RiskReferenceMode = config.riskReferenceMode,
        initialCapitalIdr: Double = quoteAmount,
    ): ExecutionResult {
        if (quoteAmount <= 0.0 || marketPrice <= 0.0) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "invalid_initial_holding")
        if (positions.size >= config.maxOpenPositions) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "paper_position_limit")
        if (quoteAmount > availableBalanceIdr + 1e-9) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "initial_holding_exceeds_capital")
        require(stopLossPercent > 0.0); require(takeProfitPercent > stopLossPercent); require(initialCapitalIdr > 0.0)
        val before = availableBalanceIdr
        val referenceCapital = when (riskReferenceMode) {
            RiskReferenceMode.ENTRY_PRICE -> quoteAmount
            RiskReferenceMode.INITIAL_CAPITAL -> initialCapitalIdr
        }
        val quantity = quoteAmount / marketPrice
        val stopAmount = referenceCapital * stopLossPercent / 100.0
        val takeAmount = referenceCapital * takeProfitPercent / 100.0
        val position = PaperPosition(
            nextPositionId("paper-initial", nowMs), exchangeId, symbol, quoteAmount, marketPrice,
            (marketPrice - stopAmount / quantity).coerceAtLeast(marketPrice * 0.000001),
            marketPrice + takeAmount / quantity,
            marketPrice + stopAmount / quantity,
            nowMs, "initial_holding", riskReferenceMode, referenceCapital,
        )
        tradeLedger?.recordOpened(position, 0.0)
        availableBalanceIdr -= quoteAmount
        positions[position.id] = position
        return ExecutionResult(true, position.id, quantity, marketPrice, 0.0, entryFee = 0.0, remainingBalanceIdr = availableBalanceIdr, reason = "initial_holding_seeded", balanceBeforeIdr = before)
    }

    fun open(exchangeId: String, symbol: String, plan: EntryPlan, nowMs: Long, entryReason: String = "entry_filled"): ExecutionResult = openInternal(exchangeId, symbol, plan, nowMs, 0.0, entryReason)

    private fun openInternal(exchangeId: String, symbol: String, plan: EntryPlan, nowMs: Long, reservedIdr: Double, entryReason: String): ExecutionResult {
        if (!plan.allowed || plan.stakeIdr <= 0.0) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "entry_plan_not_allowed")
        if (positions.size >= config.maxOpenPositions) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "paper_position_limit")
        val entryFee = plan.stakeIdr * feePercent / (100.0 + feePercent)
        val entryNotional = plan.stakeIdr - entryFee
        val required = plan.stakeIdr
        if (reservedIdr > 0.0) { if (reservedIdr + 1e-9 < required) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "invalid_limit_reservation") }
        else if (required > availableBalanceIdr) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "insufficient_paper_balance")
        require(plan.entryPrice > 0.0)
        val before = availableBalanceIdr
        val executionPrice = plan.entryPrice * (1.0 + slippagePercent / 100.0)
        val entryRatio = executionPrice / plan.entryPrice
        val id = nextPositionId("paper", nowMs)
        val position = PaperPosition(
            id = id,
            exchangeId = exchangeId,
            symbol = symbol,
            stakeIdr = plan.stakeIdr,
            entryPrice = executionPrice,
            stopLossPrice = plan.stopLossPrice * entryRatio,
            takeProfitPrice = plan.takeProfitPrice * entryRatio,
            trailingActivationPrice = plan.trailingActivationPrice * entryRatio,
            openedAtEpochMs = nowMs,
            entryReason = entryReason,
            riskReferenceMode = plan.riskReferenceMode,
            riskReferenceCapitalIdr = plan.riskReferenceCapitalIdr.takeIf { it > 0.0 } ?: plan.stakeIdr,
        )
        tradeLedger?.recordOpened(position, entryFee)
        if (reservedIdr <= 0.0) availableBalanceIdr -= required
        positions[id] = position
        return ExecutionResult(true, id, entryNotional / executionPrice, executionPrice, entryFee, entryFee = entryFee, slippagePercent = slippagePercent, remainingBalanceIdr = availableBalanceIdr, reason = entryReason, balanceBeforeIdr = before)
    }

    fun close(positionId: String, marketPrice: Double, reason: String, nowMs: Long = System.currentTimeMillis()): ExecutionResult {
        if (marketPrice <= 0.0) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, reason = reason, error = "invalid_market_price")
        val position = positions[positionId] ?: return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, reason = reason, error = "paper_position_not_found")
        val before = availableBalanceIdr
        val isInitial = position.entryReason == "initial_holding"
        val executionPrice = marketPrice * (1.0 - slippagePercent / 100.0)
        val entryFee = if (isInitial) 0.0 else position.stakeIdr * feePercent / (100.0 + feePercent)
        val entryNotional = position.stakeIdr - entryFee
        val amount = entryNotional / position.entryPrice
        val exitNotional = executionPrice * amount
        val exitFee = exitNotional * feePercent / 100.0
        val proceedsAfterFee = exitNotional - exitFee
        val netPnl = proceedsAfterFee - position.stakeIdr
        tradeLedger?.recordClosed(position, executionPrice, entryFee + exitFee, netPnl, nowMs, reason)
        availableBalanceIdr += proceedsAfterFee
        positions.remove(positionId)
        return ExecutionResult(true, positionId, amount, executionPrice, exitFee, entryFee = entryFee, exitFee = exitFee, slippagePercent = slippagePercent, pnlIdr = netPnl, remainingBalanceIdr = availableBalanceIdr, reason = reason, balanceBeforeIdr = before)
    }

    fun placeLimit(exchangeId: String, symbol: String, quoteAmount: Double, limitPrice: Double, nowMs: Long): ExecutionResult {
        if (quoteAmount <= 0.0) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "invalid_quote_amount")
        if (limitPrice <= 0.0) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "invalid_limit_price")
        if (positions.size + limitOrders.size >= config.maxOpenPositions) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "paper_position_limit")
        if (quoteAmount > availableBalanceIdr) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "insufficient_paper_balance")
        val before = availableBalanceIdr
        val id = "limit-$nowMs-${limitOrders.size + 1}"
        availableBalanceIdr -= quoteAmount
        limitOrders[id] = PaperLimitOrder(id, exchangeId, symbol, quoteAmount, limitPrice, quoteAmount, nowMs)
        return ExecutionResult(true, orderId = id, remainingBalanceIdr = availableBalanceIdr, reason = "limit_order_accepted", balanceBeforeIdr = before)
    }

    fun fillLimit(orderId: String, marketPrice: Double, nowMs: Long): ExecutionResult {
        val order = limitOrders[orderId] ?: return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "paper_limit_order_not_found")
        if (marketPrice <= 0.0) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "invalid_market_price")
        if (marketPrice > order.limitPrice) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "paper_limit_not_reached")
        val plan = EntryPlan(true, order.limitPrice, order.limitPrice * 0.995, order.limitPrice * 1.01, order.limitPrice * 1.005, order.quoteAmount, listOf("paper_limit_fill"), RiskReferenceMode.ENTRY_PRICE, order.quoteAmount)
        val result = openInternal(order.exchangeId, order.symbol, plan, nowMs, order.reservedIdr, "limit_fill")
        if (result.success) limitOrders.remove(orderId)
        return result.copy(orderId = orderId)
    }

    fun cancelLimit(orderId: String): Boolean { val order = limitOrders.remove(orderId) ?: return false; availableBalanceIdr += order.reservedIdr; return true }

    fun updateRiskTargets(newConfig: TradingConfig) {
        positions.entries.forEach { (id, position) ->
            val referenceCapital = when (newConfig.riskReferenceMode) {
                RiskReferenceMode.ENTRY_PRICE -> position.stakeIdr
                RiskReferenceMode.INITIAL_CAPITAL -> position.riskReferenceCapitalIdr.takeIf { it > 0.0 } ?: position.stakeIdr
            }
            val quantity = position.stakeIdr / position.entryPrice
            val stopAmount = referenceCapital * newConfig.effectiveStopLossPercent() / 100.0
            val takeAmount = referenceCapital * newConfig.effectiveTakeProfitPercent() / 100.0
            positions[id] = position.copy(
                stopLossPrice = (position.entryPrice - stopAmount / quantity).coerceAtLeast(position.entryPrice * 0.000001),
                takeProfitPrice = position.entryPrice + takeAmount / quantity,
                trailingActivationPrice = position.entryPrice + stopAmount / quantity,
                riskReferenceMode = newConfig.riskReferenceMode,
                riskReferenceCapitalIdr = referenceCapital,
            )
        }
    }

    fun updateTrailingStop(positionId: String, newStopLossPrice: Double): Boolean {
        if (newStopLossPrice <= 0.0) return false
        val position = positions[positionId] ?: return false
        if (newStopLossPrice <= position.stopLossPrice) return false
        if (newStopLossPrice >= position.entryPrice * 1.000001 && newStopLossPrice > position.takeProfitPrice) return false
        positions[positionId] = position.copy(stopLossPrice = newStopLossPrice)
        return true
    }

    fun position(positionId: String): PaperPosition? = positions[positionId]
    fun positionCount(): Int = positions.size
    fun positions(): List<PaperPosition> = positions.values.toList()
    fun pendingLimitOrders(): List<PaperLimitOrder> = limitOrders.values.toList()
    fun availableBalanceIdr(): Double = availableBalanceIdr
    fun reservedBalanceIdr(): Double = limitOrders.values.sumOf { it.reservedIdr }
    fun equityIdr(markPrices: Map<String, Double>): Double = availableBalanceIdr + reservedBalanceIdr() + positions.values.sumOf { position -> val mark = markPrices[position.symbol] ?: position.entryPrice; val entryFee = if (position.entryReason == "initial_holding") 0.0 else position.stakeIdr * feePercent / (100.0 + feePercent); val entryNotional = position.stakeIdr - entryFee; mark.coerceAtLeast(0.0) * (entryNotional / position.entryPrice) }

    fun snapshotState(): PaperEngineState = PaperEngineState(availableBalanceIdr, positions.values.toList())

    fun restoreState(state: PaperEngineState) {
        require(state.availableBalanceIdr >= 0.0) { "invalid_paper_balance_state" }
        require(state.positions.size <= config.maxOpenPositions) { "paper_position_limit" }
        positions.clear()
        limitOrders.clear()
        state.positions.forEach { position -> require(position.stakeIdr > 0.0 && position.entryPrice > 0.0); positions[position.id] = position }
        availableBalanceIdr = state.availableBalanceIdr
        positionSequence = state.positions.mapNotNull { it.id.substringAfterLast('-').toLongOrNull() }.maxOrNull() ?: 0L
    }

    fun forgetPositionAfterReconciliation(positionId: String): PaperPosition? = positions.remove(positionId)
    private fun nextPositionId(prefix: String, nowMs: Long): String { positionSequence += 1; return "$prefix-$nowMs-$positionSequence" }
}

class PaperExchangeAdapter(private val prices: () -> Map<String, Double>, private val engine: PaperExecutionEngine = PaperExecutionEngine(), private val exchangeName: String = "paper") : ExchangeAdapter {
    override val exchangeId: String = exchangeName
    override suspend fun fetchPrice(symbol: String): Double = prices()[symbol] ?: 0.0
    override suspend fun placeMarketBuy(symbol: String, quoteAmount: Double): ExecutionResult { val price = fetchPrice(symbol); if (price <= 0.0) return ExecutionResult(false, error = "paper_price_unavailable"); return engine.open(exchangeId, symbol, EntryPlan(true, price, price * 0.995, price * 1.01, price * 1.005, quoteAmount, listOf("paper_market_entry")), System.currentTimeMillis()) }
    override suspend fun placeLimitBuy(symbol: String, quoteAmount: Double, limitPrice: Double): ExecutionResult = engine.placeLimit(exchangeId, symbol, quoteAmount, limitPrice, System.currentTimeMillis())
    override suspend fun closePosition(positionId: String, reason: String): ExecutionResult { val position = engine.position(positionId) ?: return ExecutionResult(false, reason = reason, error = "paper_position_not_found"); val price = fetchPrice(position.symbol); return engine.close(positionId, price, reason) }
    fun paperEngine(): PaperExecutionEngine = engine
}

data class ExchangeHandle(val id: String, val displayName: String, val adapter: ExchangeAdapter, val tradingEnabled: Boolean = false)
class ExchangeRegistry {
    private val handles = linkedMapOf<String, ExchangeHandle>()
    fun register(handle: ExchangeHandle) { require(handle.id.isNotBlank()); require(handle.displayName.isNotBlank()); require(handle.adapter.exchangeId == handle.id); handles[handle.id] = handle }
    fun remove(exchangeId: String): ExchangeHandle? = handles.remove(exchangeId)
    fun get(exchangeId: String): ExchangeHandle? = handles[exchangeId]
    fun activeTradingAdapters(): List<ExchangeAdapter> = handles.values.filter { it.tradingEnabled }.map { it.adapter }
    fun ids(): List<String> = handles.keys.toList()
    fun all(): List<ExchangeHandle> = handles.values.toList()
}
