package com.mirei.app.execution

class PaperBroker(private val engine: PaperExecutionEngine) : BrokerPort {
    override val mode: BrokerMode = BrokerMode.PAPER
    override val executionEnabled: Boolean = true
    override fun positionCount(): Int = engine.positionCount()
    override fun positions(): List<PaperPosition> = engine.positions()
    override fun availableBalanceIdr(): Double = engine.availableBalanceIdr()
    override fun open(exchangeId: String, symbol: String, plan: com.mirei.app.core.EntryPlan, nowMs: Long, entryReason: String): ExecutionResult = engine.open(exchangeId, symbol, plan, nowMs, entryReason)
    override fun close(positionId: String, marketPrice: Double, reason: String, nowMs: Long): ExecutionResult = engine.close(positionId, marketPrice, reason, nowMs)
    override fun snapshotState(): PaperEngineState = engine.snapshotState()
    override fun restoreState(state: PaperEngineState) = engine.restoreState(state)
}