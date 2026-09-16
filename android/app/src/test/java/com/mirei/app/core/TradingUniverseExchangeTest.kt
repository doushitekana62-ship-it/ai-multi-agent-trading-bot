package com.mirei.app.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TradingUniverseExchangeTest {
    @Test
    fun yahooFinanceBranchKeepsExistingPaperInstrumentsSelectable() {
        assertTrue(Exchange.YAHOO_FINANCE.enabledForSixHourTest)
        val yahoo = TradingUniverse.paperReady().filter { it.providerId == Exchange.YAHOO_FINANCE.id }
        assertEquals(setOf("AAPL", "TSLA", "EUR/USD", "GBP/USD", "XAU/USD", "WTI"), yahoo.map { it.symbol }.toSet())
    }

    @Test
    fun unsupportedBrokerBranchesRemainDisabled() {
        assertTrue(Exchange.values().filter { !it.enabledForSixHourTest }.map { it.id }.containsAll(listOf("bybit", "stockbit")))
    }
}
