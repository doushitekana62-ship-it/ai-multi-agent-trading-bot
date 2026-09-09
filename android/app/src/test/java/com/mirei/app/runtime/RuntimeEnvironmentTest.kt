package com.mirei.app.runtime

import org.junit.Assert.assertTrue
import org.junit.Test

class RuntimeEnvironmentTest {
    @Test
    fun defaultsAreHealthyForDeterministicUnitRuntime() {
        val environment = RuntimeEnvironment()
        assertTrue(environment.internetAvailable)
        assertTrue(environment.exchangeHealthy)
    }
}
