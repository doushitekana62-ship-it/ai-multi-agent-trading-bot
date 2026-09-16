package com.mirei.app.runtime

import com.mirei.app.core.Exchange
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test

class MireiForegroundServiceTest {
    @Test
    fun statusActionIsDistinctFromControlActions() {
        assertNotEquals(MireiForegroundService.ACTION_START, MireiForegroundService.ACTION_STATUS)
        assertNotEquals(MireiForegroundService.ACTION_STOP, MireiForegroundService.ACTION_STATUS)
    }

    @Test
    fun supportedExchangesStaySynchronizedWithExchangeEnum() {
        assertEquals(Exchange.values().map { it.id }, MireiForegroundService.SUPPORTED_EXCHANGES)
    }
}
