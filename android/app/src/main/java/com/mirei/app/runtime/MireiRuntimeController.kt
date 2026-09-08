package com.mirei.app.runtime

import com.mirei.app.core.MireiState

class MireiRuntimeController {
    var state: MireiState = MireiState.STOP
        private set

    fun start() {
        if (state == MireiState.ERROR || state == MireiState.RECOVERY) state = MireiState.RECOVERY
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
        state = MireiState.RECOVERY
        state = MireiState.HOLD
    }
}
