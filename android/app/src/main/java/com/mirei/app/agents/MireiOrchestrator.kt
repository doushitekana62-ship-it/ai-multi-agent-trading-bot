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

        // A raw 2-vs-2 vote used to become HOLD unconditionally. That made a
        // balanced four-agent panel appear permanently inactive even when the
        // directional evidence had a clear confidence advantage. Resolve ties
        // with confidence-weighted voting, while retaining a margin so a weak
        // disagreement still remains HOLD.
        val confidenceByAction = observations
            .groupBy { it.action }
            .mapValues { (_, values) ->
                values.sumOf { it.confidence.coerceIn(0.0, 1.0) }
            }
        val ranked = confidenceByAction.entries.sortedByDescending { it.value }
        val top = ranked.first()
        val second = ranked.getOrNull(1)
        val confidenceMargin = top.value - (second?.value ?: 0.0)
        val tieResolvedAction = if (winners.size > 1 && confidenceMargin >= 0.10) {
            top.key
        } else {
            null
        }
        val action = when {
            winners.size == 1 -> winners.first()
            tieResolvedAction != null -> tieResolvedAction
            else -> AgentAction.HOLD
        }

        val winnerObservations = observations.filter { it.action == action }
        val confidence = if (action == AgentAction.HOLD && winners.size > 1 && tieResolvedAction == null) {
            observations.map { it.confidence.coerceIn(0.0, 1.0) }.average()
        } else {
            winnerObservations.map { it.confidence.coerceIn(0.0, 1.0) }.average()
        }
        val rationale = when {
            winners.size == 1 && highestVotes == observations.size -> "agent_unanimous_vote"
            winners.size == 1 -> "agent_majority_vote"
            tieResolvedAction != null -> "agent_confidence_weighted_tie_resolved"
            else -> "agent_vote_tie_hold"
        }

        // Keep DecisionMode in the API for compatibility. Disagreement is still
        // resolved deterministically; the entry/risk gates remain authoritative
        // and can reject a BUY regardless of this panel result.
        return MireiDecision(
            action = action,
            confidence = confidence,
            observations = observations,
            requiresHumanDecision = false,
            rationale = rationale,
        )
    }
}
