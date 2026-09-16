package com.mirei.app.core

/** Per-instrument risk contract. It is intentionally independent from the session-wide trading mode. */
data class PositionTradeConfig(
    val mode: ScalpingMode? = null,
    val manualRiskMode: ManualRiskMode = ManualRiskMode.AUTO,
    val stopLossPercent: Double? = null,
    val takeProfitMode: TakeProfitMode = TakeProfitMode.MODE,
    val manualTakeProfitPercent: Double? = null,
    val manualNetProfitTargetIdr: Double? = null,
    val riskReferenceMode: RiskReferenceMode? = null,
) {
    init {
        if (stopLossPercent != null) require(stopLossPercent > 0.0)
        if (manualTakeProfitPercent != null) require(manualTakeProfitPercent > 0.0)
        if (manualNetProfitTargetIdr != null) require(manualNetProfitTargetIdr > 0.0)
        if (manualRiskMode == ManualRiskMode.MANUAL) {
            require(stopLossPercent != null && stopLossPercent > 0.0)
            require(
                (takeProfitMode == TakeProfitMode.MANUAL_PERCENT && manualTakeProfitPercent != null && manualTakeProfitPercent > stopLossPercent) ||
                    (takeProfitMode == TakeProfitMode.MANUAL_NET_IDR && manualNetProfitTargetIdr != null)
            )
        }
    }
}
