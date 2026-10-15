package com.mirei.app

/**
 * Build-mode guard shared by the Android service and dashboard.
 * Unknown modes fail closed; only the PAPER flavor may initialize the paper runtime.
 */
object BuildModePolicy {
    fun usesPaperRuntime(mode: String): Boolean = mode == "PAPER"
}
