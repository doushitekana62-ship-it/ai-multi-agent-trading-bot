package com.mirei.app.core

/**
 * Canonical market catalog used by Mirei. The provider is explicit so the app
 * never assumes that an exchange offers an asset class it does not actually
 * expose.
 */
object TradingUniverse {
    val instruments: List<MarketInstrument> = listOf(
        MarketInstrument("BTC/IDR", "Bitcoin / Rupiah", AssetClass.CRYPTO, "IDR", providerId = "indodax", executionCosts = ExecutionCostProfile.INDODAX_IDR_TAKER),
        MarketInstrument("ETH/IDR", "Ethereum / Rupiah", AssetClass.CRYPTO, "IDR", providerId = "indodax", executionCosts = ExecutionCostProfile.INDODAX_IDR_TAKER),
        MarketInstrument("HYPE/IDR", "Hyperliquid / Rupiah", AssetClass.CRYPTO, "IDR", providerId = "indodax", executionCosts = ExecutionCostProfile.INDODAX_IDR_TAKER),
        MarketInstrument("FARTCOIN/IDR", "Fartcoin / Rupiah", AssetClass.CRYPTO, "IDR", providerId = "indodax", executionCosts = ExecutionCostProfile.INDODAX_IDR_TAKER),
        MarketInstrument("SOL/IDR", "Solana / Rupiah", AssetClass.CRYPTO, "IDR", providerId = "indodax", executionCosts = ExecutionCostProfile.INDODAX_IDR_TAKER),
        MarketInstrument("XRP/IDR", "XRP / Rupiah", AssetClass.CRYPTO, "IDR", providerId = "indodax", executionCosts = ExecutionCostProfile.INDODAX_IDR_TAKER),
        MarketInstrument("DOGE/IDR", "Dogecoin / Rupiah", AssetClass.CRYPTO, "IDR", providerId = "indodax", executionCosts = ExecutionCostProfile.INDODAX_IDR_TAKER),
        MarketInstrument("ADA/IDR", "Cardano / Rupiah", AssetClass.CRYPTO, "IDR", providerId = "indodax", executionCosts = ExecutionCostProfile.INDODAX_IDR_TAKER),
        MarketInstrument("SUI/IDR", "Sui / Rupiah", AssetClass.CRYPTO, "IDR", providerId = "indodax", executionCosts = ExecutionCostProfile.INDODAX_IDR_TAKER),
        MarketInstrument("TRX/IDR", "TRON / Rupiah", AssetClass.CRYPTO, "IDR", providerId = "indodax", executionCosts = ExecutionCostProfile.INDODAX_IDR_TAKER),

        // Public-data paper instruments. These are deliberately not described as
        // live broker connectivity; they are market-data providers only.
        MarketInstrument("AAPL", "Apple", AssetClass.STOCKS, "USD", providerId = "yahoo_finance", executionCosts = ExecutionCostProfile.GENERIC_STOCK, tradingHours = "US session"),
        MarketInstrument("TSLA", "Tesla", AssetClass.STOCKS, "USD", providerId = "yahoo_finance", executionCosts = ExecutionCostProfile.GENERIC_STOCK, tradingHours = "US session"),
        MarketInstrument("EUR/USD", "Euro / US Dollar", AssetClass.FOREX, "USD", providerId = "yahoo_finance", providerSymbol = "EURUSD=X", executionCosts = ExecutionCostProfile.GENERIC_FOREX),
        MarketInstrument("GBP/USD", "British Pound / US Dollar", AssetClass.FOREX, "USD", providerId = "yahoo_finance", providerSymbol = "GBPUSD=X", executionCosts = ExecutionCostProfile.GENERIC_FOREX),
        MarketInstrument("XAU/USD", "Gold / US Dollar", AssetClass.COMMODITIES, "USD", providerId = "yahoo_finance", providerSymbol = "XAUUSD=X", executionCosts = ExecutionCostProfile.GENERIC_COMMODITY),
        MarketInstrument("WTI", "WTI Crude Oil", AssetClass.COMMODITIES, "USD", providerId = "yahoo_finance", providerSymbol = "CL=F", executionCosts = ExecutionCostProfile.GENERIC_COMMODITY),
    )

    fun byClass(assetClass: AssetClass): List<MarketInstrument> = instruments.filter { it.assetClass == assetClass }
    fun bySymbol(symbol: String): MarketInstrument? = instruments.firstOrNull { it.symbol.equals(symbol, ignoreCase = true) }
    fun paperReady(): List<MarketInstrument> = instruments.filter { it.paperEnabled }
}
