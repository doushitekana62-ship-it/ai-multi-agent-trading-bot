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

        val confidenceByAction = observations
            .groupBy { it.action }
            .mapValues { (_, values) -> values.sumOf { it.confidence.coerceIn(0.0, 1.0) } }
        val ranked = confidenceByAction.entries.sortedByDescending { it.value }
        val top = ranked.first()
        val second = ranked.getOrNull(1)
        val confidenceMargin = top.value - (second?.value ?: 0.0)
        val tieResolvedAction = if (winners.size > 1 && confidenceMargin >= 0.10) top.key else null
        val votedAction = when {
            winners.size == 1 -> winners.first()
            tieResolvedAction != null -> tieResolvedAction
            else -> AgentAction.HOLD
        }

        // A CLOSE signal is an exit instruction, not an automatic substitute
        // for the protective SL. Require broad bearish confirmation before the
        // decision can reach the execution layer. Weak/contradictory bearish
        // evidence becomes HOLD so a position can recover instead of being
        // closed at a small loss immediately after entry.
        val evidence = MireiAgentEvidenceLibrary.analyze(snapshot)
        val closeConfirmed = evidence.forecastDirectionScore <= -4.0 &&
            evidence.momentumScore <= -2.0 &&
            evidence.demandScore <= -3.0 &&
            snapshot.trendScorePercent < 0.0 &&
            snapshot.forecastConfidence >= 0.65
        val action = if (votedAction == AgentAction.CLOSE && !closeConfirmed) AgentAction.HOLD else votedAction

        val winnerObservations = observations.filter { it.action == action }
        val confidence = if (action == AgentAction.HOLD && votedAction == AgentAction.CLOSE) {
            observations.map { it.confidence.coerceIn(0.0, 1.0) }.average()
        } else if (action == AgentAction.HOLD && winners.size > 1 && tieResolvedAction == null) {
            observations.map { it.confidence.coerceIn(0.0, 1.0) }.average()
        } else {
            winnerObservations.map { it.confidence.coerceIn(0.0, 1.0) }.average()
        }
        val rationale = when {
            votedAction == AgentAction.CLOSE && !closeConfirmed -> "close_suppressed_insufficient_bearish_confirmation"
            winners.size == 1 && highestVotes == observations.size -> "agent_unanimous_vote"
            winners.size == 1 -> "agent_majority_vote"
            tieResolvedAction != null -> "agent_confidence_weighted_tie_resolved"
            else -> "agent_vote_tie_hold"
        }

        // Keep DecisionMode in the API for compatibility. Entry/risk gates
        // remain authoritative and can reject a BUY regardless of this panel.
        return MireiDecision(
            action = action,
            confidence = confidence,
            observations = observations,
            requiresHumanDecision = false,
            rationale = rationale,
        )
    }
}
