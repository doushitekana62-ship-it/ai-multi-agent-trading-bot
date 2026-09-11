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

        // SL 0 is the explicit unlimited-hold mode. It must not silently
        // activate a trailing stop because the synthetic risk distance is zero.
        if (initialStopLossPrice == 0.0) {
            return ExitPlan(
                stopLossPrice = 0.0,
                takeProfitPrice = initialTakeProfitPrice,
                trailingStopPrice = null,
                breakevenApplied = false,
                partialCloseFraction = 0.0,
                reason = "unlimited_hold_until_tp_or_manual_close",
            )
        }

        val baseRiskPercent = ((entryPrice - initialStopLossPrice) / entryPrice * 100.0).coerceAtLeast(0.01)
        val profitPercent = (currentPrice / entryPrice - 1.0) * 100.0
        // Use a small numeric tolerance so an exact 1R boundary such as
        // 100000 -> 100500 is not lost to floating-point representation.
        val activationR = baseRiskPercent * config.trailingActivationR
        val activated = profitPercent + 1e-9 >= activationR

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
            // TP remains the configured target. Trailing is protection, not a
            // mechanism for silently moving the user's TP farther away.
            takeProfitPrice = initialTakeProfitPrice,
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
