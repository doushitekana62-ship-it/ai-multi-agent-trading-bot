package com.mirei.app.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TradingUniverseTest {
    @Test
    fun currentPaperUniverseContainsAllSupportedIndodaxCryptoPairs() {
        val expected = setOf(
            "BTC/IDR", "ETH/IDR", "HYPE/IDR", "FARTCOIN/IDR", "SOL/IDR",
            "XRP/IDR", "DOGE/IDR", "ADA/IDR", "SUI/IDR", "TRX/IDR",
        )
        assertEquals(expected, TradingUniverse.paperReady().map { it.symbol }.toSet())
    }

    @Test
    fun expansionAssetClassesAreCataloguedButNotMarkedLiveReady() {
        assertTrue(TradingUniverse.byClass(AssetClass.STOCKS).isNotEmpty())
        assertTrue(TradingUniverse.byClass(AssetClass.FOREX).isNotEmpty())
        assertTrue(TradingUniverse.byClass(AssetClass.COMMODITIES).isNotEmpty())
        assertTrue(TradingUniverse.instruments.filter { it.assetClass != AssetClass.CRYPTO }.all { !it.liveAdapterReady })
        assertFalse(TradingUniverse.instruments.any { it.liveAdapterReady })
    }
}
