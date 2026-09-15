package com.mirei.app.core

enum class AssetClass(val label: String) {
    CRYPTO("Crypto"),
    STOCKS("Saham"),
    FOREX("Forex"),
    COMMODITIES("Komoditas")
}

data class ExecutionCostProfile(
    val buyFeePercent: Double,
    val sellFeePercent: Double,
    val spreadPercent: Double,
    val slippagePercent: Double,
    val executionLatencyMs: Long = 250L,
    val minimumOrderIdr: Double = 0.0,
) {
    init {
        require(buyFeePercent >= 0.0)
        require(sellFeePercent >= 0.0)
        require(spreadPercent >= 0.0)
        require(slippagePercent >= 0.0)
        require(executionLatencyMs >= 0L)
        require(minimumOrderIdr >= 0.0)
    }

    companion object {
        /** Current paper default for an INDODAX IDR market-order/taker simulation.
         *  The sell side includes the current PPh component and CFX component;
         *  exact account fees remain exchange-account dependent and should be
         *  refreshed from the exchange fee configuration when available.
         */
        val INDODAX_IDR_TAKER = ExecutionCostProfile(
            buyFeePercent = 0.2111,
            sellFeePercent = 0.4211,
            spreadPercent = 0.0,
            slippagePercent = 0.05,
            executionLatencyMs = 750L,
            minimumOrderIdr = 25_000.0,
        )

        val GENERIC_FOREX = ExecutionCostProfile(
            buyFeePercent = 0.0,
            sellFeePercent = 0.0,
            spreadPercent = 0.015,
            slippagePercent = 0.01,
            executionLatencyMs = 350L,
        )

        val GENERIC_COMMODITY = ExecutionCostProfile(
            buyFeePercent = 0.0,
            sellFeePercent = 0.0,
            spreadPercent = 0.04,
            slippagePercent = 0.02,
            executionLatencyMs = 500L,
        )

        val GENERIC_STOCK = ExecutionCostProfile(
            buyFeePercent = 0.0,
            sellFeePercent = 0.0,
            spreadPercent = 0.02,
            slippagePercent = 0.02,
            executionLatencyMs = 500L,
        )
    }
}

data class MarketInstrument(
    val symbol: String,
    val name: String,
    val assetClass: AssetClass,
    val quoteCurrency: String,
    val accountCurrency: String = "IDR",
    val providerId: String,
    val providerSymbol: String = symbol,
    val executionCosts: ExecutionCostProfile = ExecutionCostProfile.INDODAX_IDR_TAKER,
    val tradingHours: String = "24/7",
    val paperEnabled: Boolean = true,
    val liveAdapterReady: Boolean = false,
)
