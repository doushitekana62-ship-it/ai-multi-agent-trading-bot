package com.mirei.app.execution

import com.mirei.app.core.EntryPlan

enum class BrokerMode { PAPER, LIVE }

interface BrokerPort {
    val mode: BrokerMode
    val executionEnabled: Boolean
    fun positionCount(): Int
    fun positions(): List<PaperPosition>
    fun availableBalanceIdr(): Double
    fun open(exchangeId: String, symbol: String, plan: EntryPlan, nowMs: Long, entryReason: String): ExecutionResult
    fun close(positionId: String, marketPrice: Double, reason: String, nowMs: Long): ExecutionResult
    fun snapshotState(): PaperEngineState
    fun restoreState(state: PaperEngineState)
}