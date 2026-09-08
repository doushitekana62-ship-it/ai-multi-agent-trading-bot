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
    private val feePercent: Double = 0.3,
    private val slippagePercent: Double = 0.05,
) {
    private val positions = linkedMapOf<String, PaperPosition>()

    fun open(exchangeId: String, symbol: String, plan: EntryPlan, nowMs: Long): ExecutionResult {
        if (!plan.allowed || plan.stakeIdr <= 0.0) {
            return ExecutionResult(false, error = "entry_plan_not_allowed")
        }
        val executionPrice = plan.entryPrice * (1.0 + slippagePercent / 100.0)
        val id = "paper-$nowMs-${positions.size + 1}"
        positions[id] = PaperPosition(
            id = id,
            exchangeId = exchangeId,
            symbol = symbol,
            stakeIdr = plan.stakeIdr,
            entryPrice = executionPrice,
            stopLossPrice = plan.stopLossPrice,
            takeProfitPrice = plan.takeProfitPrice,
            trailingActivationPrice = plan.trailingActivationPrice,
            openedAtEpochMs = nowMs,
        )
        return ExecutionResult(
            success = true,
            orderId = id,
            filledAmount = plan.stakeIdr / executionPrice,
            averagePrice = executionPrice,
            fee = plan.stakeIdr * feePercent / 100.0,
            slippagePercent = slippagePercent,
        )
    }

    fun close(positionId: String, marketPrice: Double, reason: String): ExecutionResult {
        if (marketPrice <= 0.0) return ExecutionResult(false, error = "invalid_market_price")
        val position = positions[positionId] ?: return ExecutionResult(false, error = "paper_position_not_found")
        val executionPrice = marketPrice * (1.0 - slippagePercent / 100.0)
        val amount = position.stakeIdr / position.entryPrice
        val grossPnl = (executionPrice - position.entryPrice) * amount
        val entryFee = position.stakeIdr * feePercent / 100.0
        val exitNotional = executionPrice * amount
        val exitFee = exitNotional * feePercent / 100.0
        val netPnl = grossPnl - entryFee - exitFee
        positions.remove(positionId)
        return ExecutionResult(
            success = true,
            orderId = positionId,
            filledAmount = amount,
            averagePrice = executionPrice,
            fee = entryFee + exitFee,
            slippagePercent = slippagePercent,
            pnlIdr = netPnl,
            error = null,
        )
    }

    fun positionCount(): Int = positions.size
    fun positions(): List<PaperPosition> = positions.values.toList()
    fun remove(positionId: String): PaperPosition? = positions.remove(positionId)
}
