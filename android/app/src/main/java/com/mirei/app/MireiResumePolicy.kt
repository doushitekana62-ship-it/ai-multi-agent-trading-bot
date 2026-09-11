package com.mirei.app

/** UI-only rule for exposing a continuation action for a persisted paper session. */
object MireiResumePolicy {
    fun canResume(sessionCreatedAtEpochMs: Long): Boolean = sessionCreatedAtEpochMs > 0L
}
