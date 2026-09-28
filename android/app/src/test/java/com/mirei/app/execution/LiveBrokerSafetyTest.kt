package com.mirei.app.execution

import com.mirei.app.core.EntryPlan
import org.junit.Assert.assertFalse
import org.junit.Test

class LiveBrokerSafetyTest {
    @Test fun liveBrokerIsLocked() {
        val broker = LiveBroker()
        assertFalse(broker.executionEnabled)
        org.junit.Assert.assertThrows(IllegalStateException::class.java) {
            broker.open("indodax", "BTC/IDR", EntryPlan(true, 100.0, 0.0, 110.0, 0.0, 50_000.0, emptyList()), 1L, "re_entry")
        }
    }
}