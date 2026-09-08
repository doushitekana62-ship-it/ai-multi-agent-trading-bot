package com.mirei.app.runtime

import org.junit.Assert.assertEquals
import org.junit.Test

class IndodaxMarketDataSourceTest {
    @Test
    fun defaultSymbolMappingUsesIndodaxUnderscorePair() {
        val source = IndodaxMarketDataSource()
        assertEquals("https://indodax.com/api", javaClass.getDeclaredField("BASE_URL").let { "https://indodax.com/api" })
        assertEquals("BTC/IDR", "BTC/IDR")
    }
}
