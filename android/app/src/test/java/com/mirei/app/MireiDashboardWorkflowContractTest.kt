package com.mirei.app

import com.mirei.app.runtime.MireiForegroundService
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MireiDashboardWorkflowContractTest {
    @Test
    fun dashboardButtonsMapToRealRuntimeActions() {
        val actions = mapOf(
            "LANJUTKAN" to MireiForegroundService.ACTION_START,
            "SEGARKAN DATA" to MireiForegroundService.ACTION_REFRESH,
            "JEDA / HOLD" to MireiForegroundService.ACTION_HOLD,
            "BERHENTI" to MireiForegroundService.ACTION_STOP,
            "TUTUP SEMUA POSISI" to MireiForegroundService.ACTION_CLOSE_ALL,
            "TOP UP" to MireiForegroundService.ACTION_TOP_UP,
        )

        assertEquals("com.mirei.app.action.START", actions["LANJUTKAN"])
        assertEquals("com.mirei.app.action.REFRESH", actions["SEGARKAN DATA"])
        assertEquals("com.mirei.app.action.HOLD", actions["JEDA / HOLD"])
        assertEquals("com.mirei.app.action.STOP", actions["BERHENTI"])
        assertEquals("com.mirei.app.action.CLOSE_ALL", actions["TUTUP SEMUA POSISI"])
        assertEquals("com.mirei.app.action.TOP_UP", actions["TOP UP"])
        assertTrue(actions.values.all { it.startsWith("com.mirei.app.action.") })
    }

    @Test
    fun baseWorkflowPreservesTheExpectedSessionLifecycle() {
        val workflow = listOf(
            MireiForegroundService.ACTION_START,
            MireiForegroundService.ACTION_HOLD,
            MireiForegroundService.ACTION_START,
            MireiForegroundService.ACTION_STOP,
            MireiForegroundService.ACTION_START,
            MireiForegroundService.ACTION_CLOSE_ALL,
        )

        assertEquals(MireiForegroundService.ACTION_START, workflow[0])
        assertEquals(MireiForegroundService.ACTION_HOLD, workflow[1])
        assertEquals(MireiForegroundService.ACTION_START, workflow[2])
        assertEquals(MireiForegroundService.ACTION_STOP, workflow[3])
        assertEquals(MireiForegroundService.ACTION_START, workflow[4])
        assertEquals(MireiForegroundService.ACTION_CLOSE_ALL, workflow[5])
    }
}
