"""Cloudflare control-plane adapter for the full CPython AI engine.

Heavy scientific dependencies are intentionally kept out of Python Workers.
The Worker calls the optional Cloudflare Container AI engine over HTTP. This
keeps Durable Object state/scheduling in the Worker while the existing full
multi-agent Orchestrator remains unchanged in the container.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict

import httpx


class CloudflareOrchestrator:
    """Thin HTTP adapter exposing the existing Orchestrator result contract."""

    def __init__(self, config: Dict[str, Any] | None = None, env: Any = None):
        self.config = config or {}
        self.env = env
        self.engine_url = str(
            getattr(env, "AI_ENGINE_URL", "")
            or self.config.get("ai_engine_url", "")
        ).strip().rstrip("/")
        self.engine_key = str(
            getattr(env, "AI_ENGINE_KEY", "")
            or self.config.get("ai_engine_key", "")
        ).strip()

    async def analyze(self, symbol: str, market_data: Dict[str, Any] | None = None):
        if not self.engine_url:
            raise RuntimeError(
                "AI_ENGINE_URL is not configured. Deploy the full AI engine "
                "Container and set AI_ENGINE_URL on the Worker."
            )

        headers = {"content-type": "application/json"}
        if self.engine_key:
            headers["x-ai-engine-key"] = self.engine_key

        payload = {
            "symbol": str(symbol).upper(),
            "market_data": dict(market_data or {}),
        }

        timeout = httpx.Timeout(45.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{self.engine_url}/analyze",
                json=payload,
                headers=headers,
            )

        if response.status_code >= 400:
            detail = response.text[:1000]
            raise RuntimeError(
                f"AI engine returned HTTP {response.status_code}: {detail}"
            )

        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(str(data.get("error") or "AI engine rejected request"))

        timestamp = data.get("timestamp")
        try:
            parsed_timestamp = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            parsed_timestamp = datetime.now(timezone.utc)

        return SimpleNamespace(
            timestamp=parsed_timestamp,
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
