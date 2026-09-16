package com.mirei.app.runtime

import com.mirei.app.core.MireiState

class MireiRuntimeController {
    var state: MireiState = MireiState.STOP
        private set

    fun start() {
        // Recovery is represented by the explicit error/hold transitions; start() is synchronous.
        // Do not assign RECOVERY and immediately overwrite it with RUNNING.
        state = MireiState.RUNNING
    }

    fun hold() {
        if (state != MireiState.CLOSE_ALL) state = MireiState.HOLD
    }

    fun stop() {
        state = MireiState.STOP
    }

    fun closeAll() {
        state = MireiState.CLOSE_ALL
    }

    fun onNetworkLost() {
        if (state == MireiState.RUNNING) state = MireiState.HOLD
    }

    fun onEngineError() {
        state = MireiState.ERROR
    }

    fun recoverToHold() {
        // There is no asynchronous observer between these assignments, so expose the stable state only.
        state = MireiState.HOLD
    }
}
