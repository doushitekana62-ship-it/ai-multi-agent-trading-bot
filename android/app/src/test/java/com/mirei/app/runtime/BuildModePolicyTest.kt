package com.mirei.app.runtime

import com.mirei.app.BuildModePolicy

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class BuildModePolicyTest {
    @Test fun paperBuildMayInitializePaperRuntime() {
        assertTrue(BuildModePolicy.usesPaperRuntime("PAPER"))
    }

    @Test fun liveBuildMustNotInitializePaperRuntime() {
        assertFalse(BuildModePolicy.usesPaperRuntime("LIVE"))
    }

    @Test fun unknownBuildModeFailsClosed() {
        assertFalse(BuildModePolicy.usesPaperRuntime("UNKNOWN"))
        assertFalse(BuildModePolicy.usesPaperRuntime(""))
    }
}
