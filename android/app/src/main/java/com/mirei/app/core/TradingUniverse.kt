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
    /** Metadata only: no live order adapter is enabled by Mirei paper runtime. */
    val liveAdapterReady: Boolean = false,
    /** True only where the current paper market-data/runtime path is implemented. */
    val paperRuntimeReady: Boolean = assetClass == AssetClass.CRYPTO && quote == "IDR" && providers.contains("Indodax"),
)

/**
 * Expansion catalog. Non-crypto entries are intentionally metadata/future-provider
 * definitions; MireiForegroundService currently remains Indodax crypto paper-only.
 */
object TradingUniverse {
    val instruments: List<TradingInstrument> = listOf(
        TradingInstrument("BTC/IDR", "Bitcoin / Rupiah", AssetClass.CRYPTO, "IDR", listOf("Indodax", "Bybit", "OKX")),
        TradingInstrument("ETH/IDR", "Ethereum / Rupiah", AssetClass.CRYPTO, "IDR", listOf("Indodax", "Bybit", "OKX")),
        TradingInstrument("HYPE/IDR", "Hyperliquid / Rupiah", AssetClass.CRYPTO, "IDR", listOf("Indodax")),
        TradingInstrument("FARTCOIN/IDR", "Fartcoin / Rupiah", AssetClass.CRYPTO, "IDR", listOf("Indodax")),
        TradingInstrument("SOL/IDR", "Solana / Rupiah", AssetClass.CRYPTO, "IDR", listOf("Indodax", "Bybit", "OKX")),
        TradingInstrument("XRP/IDR", "XRP / Rupiah", AssetClass.CRYPTO, "IDR", listOf("Indodax")),
        TradingInstrument("DOGE/IDR", "Dogecoin / Rupiah", AssetClass.CRYPTO, "IDR", listOf("Indodax")),
        TradingInstrument("ADA/IDR", "Cardano / Rupiah", AssetClass.CRYPTO, "IDR", listOf("Indodax")),
        TradingInstrument("SUI/IDR", "Sui / Rupiah", AssetClass.CRYPTO, "IDR", listOf("Indodax")),
        TradingInstrument("TRX/IDR", "TRON / Rupiah", AssetClass.CRYPTO, "IDR", listOf("Indodax")),
        TradingInstrument("AAPL", "Apple", AssetClass.STOCKS, "USD", listOf("Alpaca")),
        TradingInstrument("TSLA", "Tesla", AssetClass.STOCKS, "USD", listOf("Alpaca")),
        TradingInstrument("EUR_USD", "Euro / US Dollar", AssetClass.FOREX, "USD", listOf("OANDA")),
        TradingInstrument("GBP_USD", "British Pound / US Dollar", AssetClass.FOREX, "USD", listOf("OANDA")),
        TradingInstrument("XAU_USD", "Gold / US Dollar", AssetClass.COMMODITIES, "USD", listOf("OANDA")),
        TradingInstrument("WTI", "WTI Crude Oil", AssetClass.COMMODITIES, "USD", listOf("OANDA", "Broker connector")),
    )

    fun byClass(assetClass: AssetClass): List<TradingInstrument> = instruments.filter { it.assetClass == assetClass }
    fun paperReady(): List<TradingInstrument> = instruments.filter { it.paperRuntimeReady }
}
