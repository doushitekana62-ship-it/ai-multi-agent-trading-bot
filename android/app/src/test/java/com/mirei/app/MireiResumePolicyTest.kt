package com.mirei.app

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MireiResumePolicyTest {
    @Test
    fun noPersistedSession_cannotResume() {
        assertFalse(MireiResumePolicy.canResume(0L))
    }

    @Test
    fun persistedSession_canResumeWithoutReconfiguration() {
        assertTrue(MireiResumePolicy.canResume(1L))
        assertTrue(MireiResumePolicy.canResume(System.currentTimeMillis()))
    }
}
