package com.mirei.app.execution

enum class OrderStatus {
    SUBMITTED,
    ACKNOWLEDGED,
    PARTIALLY_FILLED,
    FILLED,
    CANCELLED,
    REJECTED,
    UNKNOWN,
    TIMEOUT,
}

/**
 * Pure lifecycle guard. Exchange adapters remain responsible for translating
 * exchange-specific responses into these normalized states.
 */
object OrderLifecycle {
    fun canTransition(from: OrderStatus?, to: OrderStatus): Boolean {
        if (from == null) return to == OrderStatus.SUBMITTED || to == OrderStatus.UNKNOWN
        if (from == to) return true
        return when (from) {
            OrderStatus.SUBMITTED -> to in setOf(
                OrderStatus.ACKNOWLEDGED,
                OrderStatus.PARTIALLY_FILLED,
                OrderStatus.FILLED,
                OrderStatus.CANCELLED,
                OrderStatus.REJECTED,
                OrderStatus.UNKNOWN,
                OrderStatus.TIMEOUT,
            )
            OrderStatus.ACKNOWLEDGED -> to in setOf(
                OrderStatus.PARTIALLY_FILLED,
                OrderStatus.FILLED,
                OrderStatus.CANCELLED,
                OrderStatus.REJECTED,
                OrderStatus.UNKNOWN,
                OrderStatus.TIMEOUT,
            )
            OrderStatus.PARTIALLY_FILLED -> to in setOf(
                OrderStatus.PARTIALLY_FILLED,
                OrderStatus.FILLED,
                OrderStatus.CANCELLED,
                OrderStatus.UNKNOWN,
                OrderStatus.TIMEOUT,
            )
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.UNKNOWN,
            OrderStatus.TIMEOUT -> false
        }
    }
}

data class NormalizedOrder(
    val clientOrderId: String? = null,
    val exchangeOrderId: String? = null,
    val symbol: String,
    val status: OrderStatus,
    val requestedQuoteAmount: Double = 0.0,
    val requestedBaseAmount: Double = 0.0,
    val filledBaseAmount: Double = 0.0,
    val averageFillPrice: Double = 0.0,
    val fee: Double = 0.0,
    val feeAsset: String? = null,
    val updatedAtEpochMs: Long,
) {
    fun isTerminal(): Boolean = status in setOf(
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED,
        OrderStatus.TIMEOUT,
    )
}
