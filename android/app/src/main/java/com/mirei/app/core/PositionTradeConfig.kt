package com.mirei.app.core

/** Manual SL/TP contract for one paper instrument. */
data class PositionTradeConfig(
    val stopLossPercent: Double? = null,
    val manualNetProfitTargetIdr: Double? = null,
    val riskReferenceMode: RiskReferenceMode? = null,
) {
    init {
        if (stopLossPercent != null) require(stopLossPercent > 0.0)
        if (manualNetProfitTargetIdr != null) require(manualNetProfitTargetIdr > 0.0)
    }
}
