package com.mirei.app.runtime

import org.junit.Assert.assertNotNull
import org.junit.Test

class IndodaxMarketDataSourceTest {
    @Test
    fun adapterCanBeConstructedWithoutCredentials() {
        assertNotNull(IndodaxMarketDataSource())
    }
}
