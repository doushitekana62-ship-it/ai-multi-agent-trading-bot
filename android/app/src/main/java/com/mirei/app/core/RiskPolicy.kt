package com.mirei.app.core

data class RiskSnapshot(
    val dailyPnlIdr: Double,
    val dailyStartBalanceIdr: Double,
    val equityIdr: Double,
    val openPositions: Int,
    val consecutiveLosses: Int,
    val marketDataFresh: Boolean,
    val exchangeHealthy: Boolean,
    val internetAvailable: Boolean,
)

data class RiskDecision(
    val allowedToOpen: Boolean,
    val reasons: List<String>,
    val positionMultiplier: Double = 1.0,
)

class RiskPolicy(private val config: TradingConfig) {
    fun evaluate(snapshot: RiskSnapshot): RiskDecision {
        val reasons = mutableListOf<String>()
        if (!snapshot.internetAvailable) reasons += "internet_unavailable"
        if (!snapshot.marketDataFresh) reasons += "market_data_stale"
        if (!snapshot.exchangeHealthy) reasons += "exchange_unhealthy"
        if (snapshot.openPositions >= config.maxOpenPositions) reasons += "position_limit"
        if (snapshot.dailyStartBalanceIdr <= 0.0 || snapshot.equityIdr <= 0.0) reasons += "invalid_equity"
        return if (reasons.isEmpty()) RiskDecision(true, listOf("mirei_reentry_gates_passed")) else RiskDecision(false, reasons, 0.0)
    }
}
