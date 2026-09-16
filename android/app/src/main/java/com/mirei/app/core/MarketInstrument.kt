package com.mirei.app.core

enum class Exchange(val id: String, val label: String, val enabledForSixHourTest: Boolean) {
    INDODAX("indodax", "Indodax", true),
    YAHOO_FINANCE("yahoo_finance", "Saham & Forex (Yahoo Finance, delayed)", true),
    BYBIT("bybit", "Bybit", false),
    STOCKBIT("stockbit", "Stockbit", false),
    BINANCE("binance", "Binance", false),
    BINGX("bingx", "BingX", false),
    BITGET("bitget", "Bitget", false),
    GATE("gate", "Gate", false),
    HTX("htx", "HTX", false),
    HYPERLIQUID("hyperliquid", "Hyperliquid", false),
    KRAKEN("kraken", "Kraken", false),
    OKX("okx", "OKX", false),
}

enum class AssetClass(val label: String) { CRYPTO("Crypto"), STOCKS("Saham"), FOREX("Forex"), COMMODITIES("Komoditas") }

data class ExecutionCostProfile(
    val buyFeePercent: Double, val sellFeePercent: Double, val spreadPercent: Double, val slippagePercent: Double,
    val executionLatencyMs: Long = 250L, val minimumOrderIdr: Double = 0.0,
) {
    init { require(buyFeePercent >= 0.0); require(sellFeePercent >= 0.0); require(spreadPercent >= 0.0); require(slippagePercent >= 0.0); require(executionLatencyMs >= 0L); require(minimumOrderIdr >= 0.0) }
    companion object {
        val INDODAX_IDR_TAKER = ExecutionCostProfile(0.2111, 0.4211, 0.0, 0.05, 750L, 25_000.0)
        val GENERIC_FOREX = ExecutionCostProfile(0.0, 0.0, 0.015, 0.01, 350L)
        val GENERIC_COMMODITY = ExecutionCostProfile(0.0, 0.0, 0.04, 0.02, 500L)
        val GENERIC_STOCK = ExecutionCostProfile(0.0, 0.0, 0.02, 0.02, 500L)
    }
}

data class MarketInstrument(
    val symbol: String, val name: String, val assetClass: AssetClass, val quoteCurrency: String,
    val accountCurrency: String = "IDR", val providerId: String, val providerSymbol: String = symbol,
    val executionCosts: ExecutionCostProfile = ExecutionCostProfile.INDODAX_IDR_TAKER, val tradingHours: String = "24/7",
    val paperEnabled: Boolean = true, val liveAdapterReady: Boolean = false,
) {
    val providers: List<String> get() = listOf(providerId)
}
