package com.mirei.app.execution

class LiveBroker : BrokerPort {
    override val mode: BrokerMode = BrokerMode.LIVE
    override val executionEnabled: Boolean = false
    private fun locked(): Nothing = error("live_execution_locked_until_broker_safety_contract_is_complete")
    override fun positionCount(): Int = locked()
    override fun positions(): List<PaperPosition> = locked()
    override fun availableBalanceIdr(): Double = locked()
    override fun open(exchangeId: String, symbol: String, plan: com.mirei.app.core.EntryPlan, nowMs: Long, entryReason: String): ExecutionResult = locked()
    override fun close(positionId: String, marketPrice: Double, reason: String, nowMs: Long): ExecutionResult = locked()
    override fun snapshotState(): PaperEngineState = locked()
    override fun restoreState(state: PaperEngineState) = locked()
}