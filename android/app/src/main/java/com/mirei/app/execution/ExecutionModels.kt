package com.mirei.app.execution

import com.mirei.app.core.EntryPlan

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

class PaperExecutionEngine(
    private val initialBalanceIdr: Double = 150_000.0,
    private val maxOpenPositions: Int = 3,
    private val feePercent: Double = 0.3,
    private val slippagePercent: Double = 0.05,
) {
    private var availableBalanceIdr = initialBalanceIdr
    private val positions = linkedMapOf<String, PaperPosition>()

    init {
        require(initialBalanceIdr > 0.0)
        require(maxOpenPositions in 1..3)
        require(feePercent >= 0.0)
        require(slippagePercent >= 0.0)
    }

    fun open(exchangeId: String, symbol: String, plan: EntryPlan, nowMs: Long): ExecutionResult {
        if (!plan.allowed || plan.stakeIdr <= 0.0) {
            return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "entry_plan_not_allowed")
        }
        if (positions.size >= maxOpenPositions) {
            return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "paper_position_limit")
        }

        val entryFee = plan.stakeIdr * feePercent / 100.0
        val required = plan.stakeIdr + entryFee
        if (required > availableBalanceIdr) {
            return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, error = "insufficient_paper_balance")
        }

        val executionPrice = plan.entryPrice * (1.0 + slippagePercent / 100.0)
        val id = "paper-$nowMs-${positions.size + 1}"
        val actualStop = executionPrice * (plan.stopLossPrice / plan.entryPrice)
        val actualTarget = executionPrice * (plan.takeProfitPrice / plan.entryPrice)
        val actualActivation = executionPrice * (plan.trailingActivationPrice / plan.entryPrice)

        availableBalanceIdr -= required
        positions[id] = PaperPosition(
            id = id,
            exchangeId = exchangeId,
            symbol = symbol,
            stakeIdr = plan.stakeIdr,
            entryPrice = executionPrice,
            stopLossPrice = actualStop,
            takeProfitPrice = actualTarget,
            trailingActivationPrice = actualActivation,
            openedAtEpochMs = nowMs,
        )
        return ExecutionResult(
            success = true,
            orderId = id,
            filledAmount = plan.stakeIdr / executionPrice,
            averagePrice = executionPrice,
            fee = entryFee,
            slippagePercent = slippagePercent,
            remainingBalanceIdr = availableBalanceIdr,
            reason = "entry_filled",
        )
    }

    fun close(positionId: String, marketPrice: Double, reason: String): ExecutionResult {
        if (marketPrice <= 0.0) return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, reason = reason, error = "invalid_market_price")
        val position = positions[positionId]
            ?: return ExecutionResult(false, remainingBalanceIdr = availableBalanceIdr, reason = reason, error = "paper_position_not_found")

        val executionPrice = marketPrice * (1.0 - slippagePercent / 100.0)
        val amount = position.stakeIdr / position.entryPrice
        val exitNotional = executionPrice * amount
        val exitFee = exitNotional * feePercent / 100.0
        val proceedsAfterFee = exitNotional - exitFee
        val netPnl = proceedsAfterFee - position.stakeIdr

        availableBalanceIdr += proceedsAfterFee
        positions.remove(positionId)

        return ExecutionResult(
            success = true,
            orderId = positionId,
            filledAmount = amount,
            averagePrice = executionPrice,
            fee = exitFee,
            slippagePercent = slippagePercent,
            pnlIdr = netPnl,
            remainingBalanceIdr = availableBalanceIdr,
            reason = reason,
        )
    }

    fun position(positionId: String): PaperPosition? = positions[positionId]
    fun positionCount(): Int = positions.size
    fun positions(): List<PaperPosition> = positions.values.toList()
    fun availableBalanceIdr(): Double = availableBalanceIdr
    fun equityIdr(markPrices: Map<String, Double>): Double = availableBalanceIdr + positions.values.sumOf { position ->
        val mark = markPrices[position.symbol] ?: position.entryPrice
        mark.coerceAtLeast(0.0) * (position.stakeIdr / position.entryPrice)
    }
    fun remove(positionId: String): PaperPosition? = positions.remove(positionId)
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
        val plan = entryPlan(symbol, price, quoteAmount)
        return engine.open(exchangeId, symbol, plan, System.currentTimeMillis())
    }

    override suspend fun placeLimitBuy(symbol: String, quoteAmount: Double, limitPrice: Double): ExecutionResult {
        val marketPrice = fetchPrice(symbol)
        if (marketPrice <= 0.0) return ExecutionResult(false, error = "paper_price_unavailable")
        if (limitPrice <= 0.0) return ExecutionResult(false, error = "invalid_limit_price")
        if (marketPrice > limitPrice) return ExecutionResult(false, error = "paper_limit_not_reached")
        val plan = entryPlan(symbol, limitPrice, quoteAmount)
        return engine.open(exchangeId, symbol, plan, System.currentTimeMillis())
    }

    override suspend fun closePosition(positionId: String, reason: String): ExecutionResult {
        val position = engine.position(positionId) ?: return ExecutionResult(false, reason = reason, error = "paper_position_not_found")
        val price = fetchPrice(position.symbol)
        return engine.close(positionId, price, reason)
    }

    fun paperEngine(): PaperExecutionEngine = engine

    private fun entryPlan(symbol: String, price: Double, quoteAmount: Double): EntryPlan = EntryPlan(
        allowed = quoteAmount > 0.0,
        entryPrice = price,
        stopLossPrice = price * 0.995,
        takeProfitPrice = price * 1.01,
        trailingActivationPrice = price * 1.005,
        stakeIdr = quoteAmount,
        reasons = listOf("paper_market_entry", symbol),
    )
}
