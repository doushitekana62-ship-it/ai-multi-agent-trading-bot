package com.mirei.app.core

enum class AssetClass(val label: String) {
    CRYPTO("Crypto"),
    STOCKS("Saham"),
    FOREX("Forex"),
    COMMODITIES("Komoditas")
}

data class TradingInstrument(
    val symbol: String,
    val name: String,
    val assetClass: AssetClass,
    val quote: String,
    val providers: List<String>,
    val liveAdapterReady: Boolean = false,
)

object TradingUniverse {
    val instruments: List<TradingInstrument> = listOf(
        TradingInstrument("BTC/IDR", "Bitcoin / Rupiah", AssetClass.CRYPTO, "IDR", listOf("Indodax", "Bybit", "OKX"), true),
        TradingInstrument("ETH/IDR", "Ethereum / Rupiah", AssetClass.CRYPTO, "IDR", listOf("Indodax", "Bybit", "OKX"), true),
        TradingInstrument("SOL/IDR", "Solana / Rupiah", AssetClass.CRYPTO, "IDR", listOf("Indodax", "Bybit", "OKX"), true),
        TradingInstrument("AAPL", "Apple", AssetClass.STOCKS, "USD", listOf("Alpaca")),
        TradingInstrument("TSLA", "Tesla", AssetClass.STOCKS, "USD", listOf("Alpaca")),
        TradingInstrument("EUR_USD", "Euro / US Dollar", AssetClass.FOREX, "USD", listOf("OANDA")),
        TradingInstrument("GBP_USD", "British Pound / US Dollar", AssetClass.FOREX, "USD", listOf("OANDA")),
        TradingInstrument("XAU_USD", "Gold / US Dollar", AssetClass.COMMODITIES, "USD", listOf("OANDA")),
        TradingInstrument("WTI", "WTI Crude Oil", AssetClass.COMMODITIES, "USD", listOf("OANDA", "Broker connector")),
    )

    fun byClass(assetClass: AssetClass): List<TradingInstrument> = instruments.filter { it.assetClass == assetClass }
}
