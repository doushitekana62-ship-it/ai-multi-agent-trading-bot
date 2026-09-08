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

        val dailyLossPercent = if (snapshot.dailyStartBalanceIdr > 0.0) {
            maxOf(0.0, -snapshot.dailyPnlIdr / snapshot.dailyStartBalanceIdr * 100.0)
        } else 100.0
        if (dailyLossPercent >= config.maxDailyLossPercent) reasons += "daily_loss_limit"
        if (snapshot.consecutiveLosses >= config.maxConsecutiveLosses) reasons += "loss_streak_limit"

        if (reasons.isNotEmpty()) return RiskDecision(false, reasons, 0.0)

        var multiplier = when (config.mode) {
            ScalpingMode.AGGRESSIVE -> 1.0
            ScalpingMode.BALANCED -> 0.85
            ScalpingMode.SAFETY -> 0.65
        }
        if (snapshot.consecutiveLosses == config.maxConsecutiveLosses - 1) multiplier *= 0.5
        return RiskDecision(true, listOf("risk_gates_passed"), multiplier.coerceIn(0.25, 1.0))
    }
}
