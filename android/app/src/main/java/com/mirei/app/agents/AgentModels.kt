package com.mirei.app.agents

import com.mirei.app.core.MarketSnapshot

sealed interface AgentSignal {
    data class Score(val value: Double) : AgentSignal
    data class Vote(val action: AgentAction) : AgentSignal
    data class Note(val text: String) : AgentSignal
}

enum class AgentAction { BUY, HOLD, CLOSE }

enum class AgentType {
    MARKET,
    CANDLE,
    FORECAST,
    SENTIMENT,
    RISK,
    LEARNING,
}

data class AgentObservation(
    val agent: AgentType,
    val action: AgentAction,
    val confidence: Double,
    val rationale: String,
)

data class MireiDecision(
    val action: AgentAction,
    val confidence: Double,
    val observations: List<AgentObservation>,
    val requiresHumanDecision: Boolean,
    val rationale: String,
)

interface MireiAgent {
    val type: AgentType
    fun evaluate(snapshot: MarketSnapshot): AgentObservation
}
