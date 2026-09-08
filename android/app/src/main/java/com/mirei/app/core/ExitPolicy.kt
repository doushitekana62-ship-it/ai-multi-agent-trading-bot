package com.mirei.app.core

data class ExitPlan(
    val stopLossPrice: Double,
    val takeProfitPrice: Double,
    val trailingStopPrice: Double?,
    val breakevenApplied: Boolean,
    val partialCloseFraction: Double,
    val reason: String,
)

class ExitPolicy(private val config: TradingConfig) {
    fun evaluate(
        entryPrice: Double,
        currentPrice: Double,
        initialStopLossPrice: Double,
        initialTakeProfitPrice: Double,
        atrPercent: Double,
        recentSwingLow: Double?,
    ): ExitPlan {
        require(entryPrice > 0.0)
        require(currentPrice > 0.0)
        val baseRiskPercent = ((entryPrice - initialStopLossPrice) / entryPrice * 100.0).coerceAtLeast(0.01)
        val profitPercent = (currentPrice / entryPrice - 1.0) * 100.0
        val activated = profitPercent >= baseRiskPercent * config.trailingActivationR

        if (!activated) {
            return ExitPlan(
                initialStopLossPrice,
                initialTakeProfitPrice,
                null,
                false,
                0.0,
                "initial_protection",
            )
        }

        val atrTrail = currentPrice * (atrPercent.coerceIn(0.05, 2.0) / 100.0)
        val swingTrail = recentSwingLow?.takeIf { it > 0.0 && it < currentPrice }
        val candidate = maxOf(entryPrice, currentPrice - atrTrail, swingTrail ?: 0.0)

        return ExitPlan(
            stopLossPrice = candidate,
            takeProfitPrice = maxOf(initialTakeProfitPrice, currentPrice * 1.0025),
            trailingStopPrice = candidate,
            breakevenApplied = candidate >= entryPrice,
            partialCloseFraction = when {
                profitPercent >= baseRiskPercent * 2.0 -> 0.5
                profitPercent >= baseRiskPercent -> 0.25
                else -> 0.0
            },
            reason = "trailing_1R",
        )
    }
}
