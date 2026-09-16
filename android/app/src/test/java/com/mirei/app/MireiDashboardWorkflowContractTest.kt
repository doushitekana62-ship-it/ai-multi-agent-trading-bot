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
            "TERAPKAN PERUBAHAN RISIKO" to MireiForegroundService.ACTION_APPLY_RISK,
            "VERIFIKASI MANUAL / RE-ENTRY" to MireiForegroundService.ACTION_HUMAN_VERIFY,
            "RESET SESI" to MireiForegroundService.ACTION_RESET_SESSION,
            "RESET JAM" to MireiForegroundService.ACTION_RESET_CLOCK,
            "HAPUS RIWAYAT" to MireiForegroundService.ACTION_DELETE_HISTORY,
        )

        assertEquals("com.mirei.app.action.START", actions["LANJUTKAN"])
        assertEquals("com.mirei.app.action.REFRESH", actions["SEGARKAN DATA"])
        assertEquals("com.mirei.app.action.HOLD", actions["JEDA / HOLD"])
        assertEquals("com.mirei.app.action.STOP", actions["BERHENTI"])
        assertEquals("com.mirei.app.action.CLOSE_ALL", actions["TUTUP SEMUA POSISI"])
        assertEquals("com.mirei.app.action.APPLY_RISK", actions["TERAPKAN PERUBAHAN RISIKO"])
        assertEquals("com.mirei.app.action.HUMAN_VERIFY", actions["VERIFIKASI MANUAL / RE-ENTRY"])
        assertEquals("com.mirei.app.action.RESET_SESSION", actions["RESET SESI"])
        assertEquals("com.mirei.app.action.RESET_CLOCK", actions["RESET JAM"])
        assertEquals("com.mirei.app.action.DELETE_HISTORY", actions["HAPUS RIWAYAT"])
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
