package com.mirei.app.execution

import com.mirei.app.core.EntryPlan
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
)

data class PaperLimitOrder(
    val id: String,
    val exchangeId: String,
    val symbol: String,
    val quoteAmount: Double,
    val limitPrice: Double,
    val reservedIdr: Double,
    val createdAtEpochMs: Long,
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

    init {
        require(feePercent >= 0.0)
        require(slippagePercent >= 0.0)
    }

    fun seedExistingHolding(
        exchangeId: String,
        symbol: String,
        quoteAmount: Double,
        marketPrice: Double,
        stopLossPercent: Double,
        takeProfitPercent: Double,
        nowMs: Long,
    ): ExecutionResult {
        if (quoteAmount <= 0.0 || marketPrice <= 0.0) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "invalid_initial_holding")
        if (positions.size >= config.maxOpenPositions) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "paper_position_limit")
        if (quoteAmount > availableBalanceIdr + 1e-9) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "initial_holding_exceeds_capital")
        require(stopLossPercent > 0.0)
        require(takeProfitPercent > stopLossPercent)

        val entryFee = quoteAmount * feePercent / (100.0 + feePercent)
        val entryNotional = quoteAmount - entryFee
        val position = PaperPosition(
            id = "paper-initial-$nowMs-${positions.size + 1}",
            exchangeId = exchangeId,
            symbol = symbol,
            stakeIdr = quoteAmount,
            entryPrice = marketPrice,
            stopLossPrice = marketPrice * (1.0 - stopLossPercent / 100.0),
            takeProfitPrice = marketPrice * (1.0 + takeProfitPercent / 100.0),
            trailingActivationPrice = marketPrice * (1.0 + stopLossPercent / 100.0),
            openedAtEpochMs = nowMs,
        )
        tradeLedger?.recordOpened(position, entryFee)
        availableBalanceIdr -= quoteAmount
        positions[position.id] = position
        return ExecutionResult(true, position.id, entryNotional / marketPrice, marketPrice, entryFee, entryFee = entryFee, remainingBalanceIdr = availableBalanceIdr, reason = "initial_holding_seeded")
    }

    fun open(exchangeId: String, symbol: String, plan: EntryPlan, nowMs: Long): ExecutionResult = openInternal(exchangeId, symbol, plan, nowMs, reservedIdr = 0.0)

    private fun openInternal(exchangeId: String, symbol: String, plan: EntryPlan, nowMs: Long, reservedIdr: Double): ExecutionResult {
        if (!plan.allowed || plan.stakeIdr <= 0.0) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "entry_plan_not_allowed")
        if (positions.size >= config.maxOpenPositions) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "paper_position_limit")
        val entryFee = plan.stakeIdr * feePercent / (100.0 + feePercent)
        val entryNotional = plan.stakeIdr - entryFee
        val required = plan.stakeIdr
        if (reservedIdr > 0.0) {
            if (reservedIdr + 1e-9 < required) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "invalid_limit_reservation")
        } else if (required > availableBalanceIdr) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "insufficient_paper_balance")
        require(plan.entryPrice > 0.0)
        val executionPrice = plan.entryPrice * (1.0 + slippagePercent / 100.0)
        val id = "paper-$nowMs-${positions.size + 1}"
        val position = PaperPosition(id, exchangeId, symbol, plan.stakeIdr, executionPrice, executionPrice * (plan.stopLossPrice / plan.entryPrice), executionPrice * (plan.takeProfitPrice / plan.entryPrice), executionPrice * (plan.trailingActivationPrice / plan.entryPrice), nowMs)
        tradeLedger?.recordOpened(position, entryFee)
        if (reservedIdr <= 0.0) availableBalanceIdr -= required
        positions[id] = position
        return ExecutionResult(true, id, entryNotional / executionPrice, executionPrice, entryFee, entryFee = entryFee, slippagePercent = slippagePercent, remainingBalanceIdr = availableBalanceIdr, reason = "entry_filled")
    }

    fun close(positionId: String, marketPrice: Double, reason: String, nowMs: Long = System.currentTimeMillis()): ExecutionResult {
        if (marketPrice <= 0.0) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, reason = reason, error = "invalid_market_price")
        val position = positions[positionId] ?: return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, reason = reason, error = "paper_position_not_found")
        val executionPrice = marketPrice * (1.0 - slippagePercent / 100.0)
        val entryFee = position.stakeIdr * feePercent / (100.0 + feePercent)
        val entryNotional = position.stakeIdr - entryFee
        val amount = entryNotional / position.entryPrice
        val exitNotional = executionPrice * amount
        val exitFee = exitNotional * feePercent / 100.0
        val proceedsAfterFee = exitNotional - exitFee
        val netPnl = proceedsAfterFee - position.stakeIdr
        tradeLedger?.recordClosed(position, executionPrice, entryFee + exitFee, netPnl, nowMs, reason)
        availableBalanceIdr += proceedsAfterFee
        positions.remove(positionId)
        return ExecutionResult(true, positionId, amount, executionPrice, exitFee, entryFee = entryFee, exitFee = exitFee, slippagePercent = slippagePercent, pnlIdr = netPnl, remainingBalanceIdr = availableBalanceIdr, reason = reason)
    }

    fun placeLimit(exchangeId: String, symbol: String, quoteAmount: Double, limitPrice: Double, nowMs: Long): ExecutionResult {
        if (quoteAmount <= 0.0) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "invalid_quote_amount")
        if (limitPrice <= 0.0) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "invalid_limit_price")
        if (positions.size + limitOrders.size >= config.maxOpenPositions) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "paper_position_limit")
        if (quoteAmount > availableBalanceIdr) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "insufficient_paper_balance")
        val id = "limit-$nowMs-${limitOrders.size + 1}"
        availableBalanceIdr -= quoteAmount
        limitOrders[id] = PaperLimitOrder(id, exchangeId, symbol, quoteAmount, limitPrice, quoteAmount, nowMs)
        return ExecutionResult(true, orderId = id, remainingBalanceIdr = availableBalanceIdr, reason = "limit_order_accepted")
    }

    fun fillLimit(orderId: String, marketPrice: Double, nowMs: Long): ExecutionResult {
        val order = limitOrders[orderId] ?: return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "paper_limit_order_not_found")
        if (marketPrice <= 0.0) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "invalid_market_price")
        if (marketPrice > order.limitPrice) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "paper_limit_not_reached")
        val plan = EntryPlan(true, order.limitPrice, order.limitPrice * 0.995, order.limitPrice * 1.01, order.limitPrice * 1.005, order.quoteAmount, listOf("paper_limit_fill"))
        val result = openInternal(order.exchangeId, order.symbol, plan, nowMs, reservedIdr = order.reservedIdr)
        if (result.success) limitOrders.remove(orderId)
        return result.copy(orderId = orderId)
    }

    fun cancelLimit(orderId: String): Boolean {
        val order = limitOrders.remove(orderId) ?: return false
        availableBalanceIdr += order.reservedIdr
        return true
    }

    fun updateRiskTargets(stopLossPercent: Double, takeProfitPercent: Double) {
        require(stopLossPercent > 0.0)
        require(takeProfitPercent > stopLossPercent)
        positions.entries.forEach { (id, position) ->
            positions[id] = position.copy(
                stopLossPrice = position.entryPrice * (1.0 - stopLossPercent / 100.0),
                takeProfitPrice = position.entryPrice * (1.0 + takeProfitPercent / 100.0),
                trailingActivationPrice = position.entryPrice * (1.0 + stopLossPercent / 100.0),
            )
        }
    }

    fun position(positionId: String): PaperPosition? = positions[positionId]
    fun positionCount(): Int = positions.size
    fun positions(): List<PaperPosition> = positions.values.toList()
    fun pendingLimitOrders(): List<PaperLimitOrder> = limitOrders.values.toList()
    fun availableBalanceIdr(): Double = availableBalanceIdr
    fun reservedBalanceIdr(): Double = limitOrders.values.sumOf { it.reservedIdr }
    fun equityIdr(markPrices: Map<String, Double>): Double = availableBalanceIdr + reservedBalanceIdr() + positions.values.sumOf { position ->
        val mark = markPrices[position.symbol] ?: position.entryPrice
        val entryFee = position.stakeIdr * feePercent / (100.0 + feePercent)
        val entryNotional = position.stakeIdr - entryFee
        mark.coerceAtLeast(0.0) * (entryNotional / position.entryPrice)
    }
    fun forgetPositionAfterReconciliation(positionId: String): PaperPosition? = positions.remove(positionId)
}

class PaperExchangeAdapter(
    private val prices: () -> Map<String, Double>,
    private val engine: PaperExecutionEngine = PaperExecutionEngine(),
    private val exchangeName: String = "paper",
) : ExchangeAdapter {
    override val exchangeId: String = exchangeName
    override suspend fun fetchPrice(symbol: String): Double = prices()[symbol] ?: 0.0
    override suspend fun placeMarketBuy(symbol: String, quoteAmount: Double): ExecutionResult {
        val price = fetchPrice(symbol)
        if (price <= 0.0) return ExecutionResult(false, error = "paper_price_unavailable")
        return engine.open(exchangeId, symbol, EntryPlan(true, price, price * 0.995, price * 1.01, price * 1.005, quoteAmount, listOf("paper_market_entry")), System.currentTimeMillis())
    }
    override suspend fun placeLimitBuy(symbol: String, quoteAmount: Double, limitPrice: Double): ExecutionResult = engine.placeLimit(exchangeId, symbol, quoteAmount, limitPrice, System.currentTimeMillis())
    override suspend fun closePosition(positionId: String, reason: String): ExecutionResult {
        val position = engine.position(positionId) ?: return ExecutionResult(false, reason = reason, error = "paper_position_not_found")
        val price = fetchPrice(position.symbol)
        return engine.close(positionId, price, reason)
    }
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
