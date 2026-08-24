"""Scalping entry adapter for the existing orchestration pipeline.

The adapter converts an existing OrchestratorResult into an entry candidate
without bypassing RiskEngine, DecisionEngine, or ExecutionGate. It is designed
to be inserted immediately before the integration engine's HOLD return.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from core.scalping_controller import ScalpingController, ScalpingSetup


class ScalpingEntryAdapter:
    """Evaluate a scalping setup when the normal orchestrator is HOLD."""

    def __init__(self, controller: Optional[ScalpingController] = None) -> None:
        self.controller = controller or ScalpingController()

    @staticmethod
    def _score(result: Any, component: str, attr: str, default: float = 0.0) -> float:
        obj = getattr(result, component, None)
        if obj is not None:
            try:
                return float(getattr(obj, attr, default))
            except (TypeError, ValueError):
                pass
        scores = getattr(result, "market_scores", {}) or {}
        try:
            return float(scores.get(component, default))
        except (TypeError, ValueError):
            return default

    def evaluate(
        self,
        orchestrator_result: Any,
        *,
        prices: Optional[Sequence[float]] = None,
        volumes: Optional[Sequence[float]] = None,
        volatility: float = 0.02,
        data_quality: float = 1.0,
    ) -> ScalpingSetup:
        """Return a setup; never executes an order and never overrides risk."""
        technical = self._score(orchestrator_result, "technical", "overall_score")
        sentiment = self._score(orchestrator_result, "sentiment", "overall_score")
        decision = self._score(orchestrator_result, "decision", "action_score")

        forecast = self._score(orchestrator_result, "forecast", "forecast_score")
        if forecast == 0.0:
            forecast_obj = getattr(orchestrator_result, "forecast", None)
            trend = str(getattr(forecast_obj, "primary_trend", "")).upper() if forecast_obj else ""
            forecast = 0.5 if trend == "BULLISH" else -0.5 if trend == "BEARISH" else 0.0

        mimic = 0.0
        mimic_obj = getattr(orchestrator_result, "mimic_analysis", None)
        if mimic_obj is not None:
            mimic = float(getattr(mimic_obj, "net_score", 0.0) or 0.0)

        return self.controller.evaluate(
            technical=technical,
            sentiment=sentiment,
            forecast=forecast,
            mimic=mimic,
            decision=decision,
            volatility=volatility,
            data_quality=data_quality,
            prices=prices,
            volumes=volumes,
        )

    def promote_only_when_hold(
        self,
        orchestrator_result: Any,
        *,
        prices: Optional[Sequence[float]] = None,
        volumes: Optional[Sequence[float]] = None,
        volatility: float = 0.02,
        data_quality: float = 1.0,
    ) -> Dict[str, Any]:
        """Produce an entry candidate without changing the orchestrator result."""
        original = str(getattr(orchestrator_result, "final_action", "HOLD")).upper()
        setup = self.evaluate(
            orchestrator_result,
            prices=prices,
            volumes=volumes,
            volatility=volatility,
            data_quality=data_quality,
        )

        promoted = original
        if original == "HOLD" and setup.action in {"BUY", "SELL"}:
            promoted = setup.action

        return {
            "original_action": original,
            "action": promoted,
            "promoted": promoted != original,
            "setup": setup,
            "reason": setup.reason,
        }
