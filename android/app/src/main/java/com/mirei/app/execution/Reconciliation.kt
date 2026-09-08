package com.mirei.app.execution

enum class ReconciliationStatus {
    CONSISTENT,
    INTERNAL_ONLY,
    EXCHANGE_ONLY,
    STATUS_MISMATCH,
    SIZE_MISMATCH,
}

data class ReconciliationIssue(
    val status: ReconciliationStatus,
    val positionId: String,
    val detail: String,
)

data class InternalPositionSnapshot(
    val positionId: String,
    val symbol: String,
    val filledAmount: Double,
    val status: String = "OPEN",
)

data class ExchangePositionSnapshot(
    val positionId: String,
    val symbol: String,
    val filledAmount: Double,
    val status: String = "OPEN",
)

object PositionReconciler {
    private const val EPSILON = 1e-12

    fun compare(
        internal: List<InternalPositionSnapshot>,
        exchange: List<ExchangePositionSnapshot>,
    ): List<ReconciliationIssue> {
        val internalById = internal.associateBy { it.positionId }
        val exchangeById = exchange.associateBy { it.positionId }
        val issues = mutableListOf<ReconciliationIssue>()

        internalById.forEach { (id, local) ->
            val remote = exchangeById[id]
            if (remote == null) {
                issues += ReconciliationIssue(
                    ReconciliationStatus.INTERNAL_ONLY,
                    id,
                    "internal position is absent on exchange",
                )
                return@forEach
            }
            if (local.symbol != remote.symbol) {
                issues += ReconciliationIssue(
                    ReconciliationStatus.STATUS_MISMATCH,
                    id,
                    "symbol mismatch: internal=${local.symbol}, exchange=${remote.symbol}",
                )
                return@forEach
            }
            if (local.status != remote.status) {
                issues += ReconciliationIssue(
                    ReconciliationStatus.STATUS_MISMATCH,
                    id,
                    "status mismatch: internal=${local.status}, exchange=${remote.status}",
                )
                return@forEach
            }
            if (kotlin.math.abs(local.filledAmount - remote.filledAmount) > EPSILON) {
                issues += ReconciliationIssue(
                    ReconciliationStatus.SIZE_MISMATCH,
                    id,
                    "size mismatch: internal=${local.filledAmount}, exchange=${remote.filledAmount}",
                )
            }
        }

        exchangeById.keys
            .filterNot { internalById.containsKey(it) }
            .forEach { id ->
                issues += ReconciliationIssue(
                    ReconciliationStatus.EXCHANGE_ONLY,
                    id,
                    "exchange position is absent from internal state",
                )
            }

        return issues
    }

    fun isSafeToContinue(issues: List<ReconciliationIssue>): Boolean = issues.isEmpty()
}
