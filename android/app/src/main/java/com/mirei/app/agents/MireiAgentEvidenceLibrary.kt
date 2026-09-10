package com.mirei.app.agents

import com.mirei.app.core.MarketSnapshot
import kotlin.math.abs

/**
 * Shared semantic layer for the deterministic agents.
 *
 * The agents keep different roles, but they must reason over the same derived
 * evidence instead of independently interpreting the raw snapshot. This keeps
 * demand/sentiment and forecast direction aligned without making one agent
 * directly depend on another agent's runtime output.
 */
data class MireiAgentEvidence(
    val candleScore: Double,
    val momentumScore: Double,
    val demandScore: Double,
    val forecastDirectionScore: Double,
    val forecastAgreement: Double,
)

object MireiAgentEvidenceLibrary {
    fun analyze(snapshot: MarketSnapshot): MireiAgentEvidence {
        val rangePosition = if (snapshot.high24h > snapshot.low24h) {
            ((snapshot.price - snapshot.low24h) / (snapshot.high24h - snapshot.low24h) * 2.0 - 1.0)
                .coerceIn(-1.0, 1.0)
        } else {
            0.0
        }

        val candleScore = (
            snapshot.change1mPercent * 35.0 +
                snapshot.change5mPercent * 12.0 +
                snapshot.change15mPercent * 4.0
            ).coerceIn(-100.0, 100.0)

        val momentumScore = (
            snapshot.trendScorePercent * 0.70 +
                snapshot.momentumPercent * 10.0 +
                snapshot.change5mPercent * 5.0
            ).coerceIn(-100.0, 100.0)

        val demandScore = (
            snapshot.tradeFlowPercent * 0.60 +
                snapshot.change1mPercent * 8.0 +
                snapshot.change5mPercent * 3.0 +
                rangePosition * 10.0
            ).coerceIn(-100.0, 100.0)

        val forecastDirectionScore = (
            candleScore * 0.30 +
                momentumScore * 0.35 +
                demandScore * 0.35
            ).coerceIn(-100.0, 100.0)

        val components = doubleArrayOf(candleScore, momentumScore, demandScore)
        val agreement = (1.0 - components.map { abs(it - forecastDirectionScore) / 100.0 }.average())
            .coerceIn(0.0, 1.0)

        return MireiAgentEvidence(
            candleScore = candleScore,
            momentumScore = momentumScore,
            demandScore = demandScore,
            forecastDirectionScore = forecastDirectionScore,
            forecastAgreement = agreement,
        )
    }

    fun forecastConfidence(snapshot: MarketSnapshot, evidence: MireiAgentEvidence): Double {
        val directionalSupport = (0.50 + abs(evidence.forecastDirectionScore) / 200.0).coerceIn(0.50, 0.95)
        return (
            snapshot.forecastConfidence.coerceIn(0.50, 0.95) * 0.65 +
                directionalSupport * 0.25 +
                evidence.forecastAgreement * 0.10
            ).coerceIn(0.50, 0.95)
    }
}
