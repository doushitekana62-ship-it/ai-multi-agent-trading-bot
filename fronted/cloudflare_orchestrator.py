"""Cloudflare control-plane adapter for the external CPython AI engine.

The Cloudflare Worker remains lightweight. Heavy NumPy/Pandas/SciPy/
scikit-learn work runs in the FastAPI Cloud service, while Durable Object
continues to own the manual paper-trading gate and persistent paper state.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict

from js import fetch
from pyodide.ffi import to_js


class CloudflareOrchestrator:
    """Call FastAPI Cloud and preserve the existing Orchestrator result contract."""

    def __init__(self, config: Dict[str, Any] | None = None, env: Any = None):
        self.config = config or {}
        self.env = env

    @staticmethod
    def _timestamp(value):
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return datetime.now(timezone.utc)

    async def analyze(self, symbol: str, market_data: Dict[str, Any] | None = None):
        if self.env is None:
            raise RuntimeError("Worker environment is unavailable")

        base_url = str(getattr(self.env, "AI_ENGINE_URL", "") or "").strip().rstrip("/")
        if not base_url:
            raise RuntimeError(
                "AI_ENGINE_URL is not configured. Set it to the FastAPI Cloud AI engine URL."
            )

        shared_secret = str(getattr(self.env, "AI_ENGINE_SHARED_SECRET", "") or "").strip()
        if len(shared_secret) < 32:
            raise RuntimeError(
                "AI_ENGINE_SHARED_SECRET is not configured on the dashboard Worker."
            )

        payload = {
            "symbol": str(symbol).upper(),
            "market_data": dict(market_data or {}),
        }

        try:
            response = await fetch(
                f"{base_url}/engine/analyze",
                to_js({
                    "method": "POST",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "X-AI-Engine-Key": shared_secret,
                    },
                    "body": json.dumps(payload, separators=(",", ":")),
                }),
            )
            status_code = int(response.status)
            text = await response.text()
            try:
                data = json.loads(text)
            except Exception as exc:
                raise RuntimeError(
                    f"AI engine returned non-JSON response (HTTP {status_code})"
                ) from exc
        except Exception as exc:
            if isinstance(exc, RuntimeError):
                raise
            raise RuntimeError(f"AI engine HTTP request failed: {exc}") from exc

        if status_code < 200 or status_code >= 300 or data.get("ok") is not True:
            detail = data.get("detail") or data.get("error") or f"HTTP {status_code}"
            raise RuntimeError(f"AI engine rejected analysis: {detail}")

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
