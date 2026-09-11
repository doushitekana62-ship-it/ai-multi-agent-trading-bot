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
                requiresHumanDecision = false,
                rationale = "no_agent_observation_hold",
            )
        }

        val voteCounts = observations.groupingBy { it.action }.eachCount()
        val highestVotes = voteCounts.values.maxOrNull() ?: 0
        val winners = voteCounts.filterValues { it == highestVotes }.keys
        val action = if (winners.size == 1) winners.first() else AgentAction.HOLD
        val winnerObservations = observations.filter { it.action == action }
        val confidence = if (action == AgentAction.HOLD && winners.size > 1) {
            observations.map { it.confidence.coerceIn(0.0, 1.0) }.average()
        } else {
            winnerObservations.map { it.confidence.coerceIn(0.0, 1.0) }.average()
        }
        val rationale = when {
            winners.size > 1 -> "agent_vote_tie_hold"
            highestVotes == observations.size -> "agent_unanimous_vote"
            else -> "agent_majority_vote"
        }

        // Keep DecisionMode in the API for compatibility. In autonomous Suggestion,
        // disagreement is resolved by deterministic voting rather than waiting for a
        // human who may not be watching the application continuously.
        return MireiDecision(
            action = action,
            confidence = confidence,
            observations = observations,
            requiresHumanDecision = false,
            rationale = rationale,
        )
    }
}
