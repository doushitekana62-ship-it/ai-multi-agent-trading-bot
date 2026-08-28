"""Cloudflare control-plane adapter for the full CPython AI engine.

The dashboard Worker stays lightweight. Heavy NumPy/Pandas/SciPy/scikit-learn
work executes inside the dedicated Cloudflare Container through an internal
Service Binding/RPC endpoint.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict


class CloudflareOrchestrator:
    """Expose the existing Orchestrator result contract through AI_ENGINE RPC."""

    def __init__(self, config: Dict[str, Any] | None = None, env: Any = None):
        self.config = config or {}
        self.env = env

    @staticmethod
    def _to_python(value):
        """Convert a Pyodide JS proxy/structured-clone result to Python."""
        try:
            converter = getattr(value, "to_py", None)
            if callable(converter):
                return converter()
        except Exception:
            pass
        return value

    @staticmethod
    def _timestamp(value):
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return datetime.now(timezone.utc)

    async def analyze(self, symbol: str, market_data: Dict[str, Any] | None = None):
        if self.env is None or not hasattr(self.env, "AI_ENGINE"):
            raise RuntimeError(
                "AI_ENGINE service binding is not configured on the dashboard Worker."
            )

        payload = {
            "symbol": str(symbol).upper(),
            "market_data": dict(market_data or {}),
        }

        try:
            raw = await self.env.AI_ENGINE.analyze(payload)
        except Exception as exc:
            raise RuntimeError(f"AI engine service call failed: {exc}") from exc

        data = self._to_python(raw)
        if not isinstance(data, dict):
            raise RuntimeError("AI engine returned an invalid response payload")
        if data.get("ok") is not True:
            raise RuntimeError(str(data.get("error") or data.get("detail") or "AI engine rejected request"))

        return SimpleNamespace(
            timestamp=self._timestamp(data.get("timestamp")),
            symbol=str(data.get("symbol") or symbol).upper(),
            current_price=float(data.get("current_price") or 0.0),
            final_action=str(data.get("final_action") or "HOLD"),
            final_confidence=float(data.get("final_confidence") or 0.0),
            consensus_action=data.get("consensus_action") or "HOLD",
            consensus_score=float(data.get("consensus_score") or 0.0),
            agent_votes=dict(data.get("agent_votes") or {}),
            market_scores=dict(data.get("market_scores") or {}),
            confidence_components=dict(data.get("confidence_components") or {}),
            position_size=float(data.get("position_size") or 0.0),
            stop_loss=data.get("stop_loss"),
            take_profit=data.get("take_profit"),
            execution_reason=data.get("execution_reason"),
            hold_reason=data.get("hold_reason"),
            summary=data.get("summary") or "AI engine completed analysis.",
        )
