package com.mirei.app.agents

import com.mirei.app.core.DecisionMode
import com.mirei.app.core.MarketSnapshot

class MireiOrchestrator(
    private val agents: List<MireiAgent>,
    private val decisionMode: DecisionMode,
) {
    fun evaluate(snapshot: MarketSnapshot): MireiDecision {
        val observations = agents.map { it.evaluate(snapshot) }
        if (observations.isEmpty()) {
            return MireiDecision(
                action = AgentAction.HOLD,
                confidence = 0.0,
                observations = emptyList(),
                requiresHumanDecision = true,
                rationale = "no_agent_observation",
            )
        }

        val actions = observations.map { it.action }.toSet()
        val conflicting = actions.size > 1
        if (conflicting && decisionMode == DecisionMode.SUGGESTION) {
            return MireiDecision(
                action = AgentAction.HOLD,
                confidence = observations.minOf { it.confidence.coerceIn(0.0, 1.0) },
                observations = observations,
                requiresHumanDecision = true,
                rationale = "agent_conflict_requires_human_decision",
            )
        }

        val action = when {
            actions == setOf(AgentAction.CLOSE) -> AgentAction.CLOSE
            actions == setOf(AgentAction.BUY) -> AgentAction.BUY
            actions == setOf(AgentAction.HOLD) -> AgentAction.HOLD
            AgentAction.CLOSE in actions -> AgentAction.CLOSE
            AgentAction.BUY in actions -> AgentAction.BUY
            else -> AgentAction.HOLD
        }

        val confidence = observations.map { it.confidence.coerceIn(0.0, 1.0) }.average()
        return MireiDecision(
            action = action,
            confidence = confidence,
            observations = observations,
            requiresHumanDecision = false,
            rationale = "agent_consensus_or_take_over",
        )
    }
}
