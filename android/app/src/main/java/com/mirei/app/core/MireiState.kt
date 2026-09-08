package com.mirei.app.core

enum class MireiState {
    STOP,
    RUNNING,
    HOLD,
    CLOSE_ALL,
    ERROR,
    RECOVERY,
}

enum class DecisionMode {
    SUGGESTION,
    TAKE_OVER,
}

enum class ScalpingMode {
    AGGRESSIVE,
    BALANCED,
    SAFETY,
}
