package com.mirei.app.runtime

import org.junit.Assert.assertNotEquals
import org.junit.Test

class MireiForegroundServiceTest {
    @Test
    fun statusActionIsDistinctFromControlActions() {
        assertNotEquals(MireiForegroundService.ACTION_START, MireiForegroundService.ACTION_STATUS)
        assertNotEquals(MireiForegroundService.ACTION_STOP, MireiForegroundService.ACTION_STATUS)
    }
}
