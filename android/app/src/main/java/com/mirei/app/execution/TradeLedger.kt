package com.mirei.app.execution

/** Persists execution lifecycle events without coupling the execution engine to Android storage. */
interface TradeLedger {
    fun recordOpened(position: PaperPosition, entryFeeIdr: Double = 0.0)
    fun recordClosed(
        position: PaperPosition,
        exitPrice: Double,
        feeIdr: Double,
        pnlIdr: Double,
        closedAtEpochMs: Long,
        exitReason: String,
    )
}
