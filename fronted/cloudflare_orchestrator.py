"""Cloudflare control-plane adapter for the external CPython AI engine.

FastAPI Cloud is preferred for the full CPython multi-agent Orchestrator. The
Worker also contains a lightweight deterministic five-agent fallback so paper
trading remains functional when the external service is not configured or is
temporarily unavailable. The fallback never places real orders.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict

from js import fetch
from pyodide.ffi import to_js


class CloudflareOrchestrator:
    """Run the preferred AI engine with a safe Worker-local paper fallback."""

    def __init__(self, config: Dict[str, Any] | None = None, env: Any = None):
        self.config = config or {}
        self.env = env

    @staticmethod
    def _timestamp(value):
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return datetime.now(timezone.utc)

    @staticmethod
    def _number(value, default=0.0):
        try:
            number = float(value)
            if number != number or number in (float("inf"), float("-inf")):
                return default
            return number
        except (TypeError, ValueError):
            return default

    @classmethod
    def _local_fallback(cls, symbol: str, market_data: Dict[str, Any], reason: str):
        """Return a bounded paper-only ensemble without external dependencies."""
        price = cls._number(
            market_data.get("current_price") or market_data.get("unified_price")
        )
        high = cls._number(market_data.get("high_24h"))
        low = cls._number(market_data.get("low_24h"))
        move = cls._number(market_data.get("change_percent_24h"))
        if high > low > 0 and price > 0:
            range_position = max(0.0, min(100.0, ((price - low) / (high - low)) * 100.0))
        else:
            range_position = 50.0

        # Five lightweight roles use only the real market payload supplied by
        # INDODAX. They are intentionally conservative and never bypass paper mode.
        sentiment = "BUY" if move >= 0.20 else "SELL" if move <= -0.20 else "HOLD"
        technical = "BUY" if range_position >= 70.0 else "SELL" if range_position <= 30.0 else "HOLD"
        decision_score = (move / 2.0) + ((range_position - 50.0) / 50.0) * 0.5
        decision = "BUY" if decision_score >= 0.35 else "SELL" if decision_score <= -0.35 else "HOLD"
        forecast = "BUY" if move >= 0.10 else "SELL" if move <= -0.10 else "HOLD"
        reflector = "HOLD" if abs(decision_score) < 0.50 else decision

        votes = {
            "Sentiment Agent": sentiment,
            "Technical Agent": technical,
            "Decision Agent": decision,
            "Forecast Agent": forecast,
            "Reflector Agent": reflector,
        }
        counts = {
            action: sum(1 for vote in votes.values() if vote == action)
            for action in ("BUY", "SELL", "HOLD")
        }
        action = max(counts, key=counts.get)
        agreement = counts[action] / len(votes)
        confidence = max(0.40, min(0.85, 0.40 + agreement * 0.45))

        if action == "BUY":
            position_size = min(0.20, max(0.01, confidence * 0.20))
            stop_loss = price * 0.95 if price > 0 else None
            take_profit = price * 1.05 if price > 0 else None
        elif action == "SELL":
            position_size = min(0.20, max(0.01, confidence * 0.20))
            stop_loss = price * 1.05 if price > 0 else None
            take_profit = price * 0.95 if price > 0 else None
        else:
            position_size = 0.0
            stop_loss = None
            take_profit = None

        scores = {
            "sentiment": max(-1.0, min(1.0, move / 2.0)),
            "technical": max(-1.0, min(1.0, (range_position - 50.0) / 50.0)),
            "decision": max(-1.0, min(1.0, decision_score)),
            "forecast": max(-1.0, min(1.0, move / 1.5)),
            "mimic_trader": max(-1.0, min(1.0, decision_score)),
            "consensus": (1.0 if action == "BUY" else -1.0 if action == "SELL" else 0.0) * agreement,
        }
        summary = (
            f"Local paper fallback: {action} with {agreement:.0%} five-agent agreement; "
            f"recent move={move:.3f}%, range position={range_position:.1f}%."
        )
        return SimpleNamespace(
            timestamp=datetime.now(timezone.utc),
            symbol=str(symbol).upper(),
            current_price=price,
            final_action=action,
            final_confidence=confidence,
            consensus_action=action,
            consensus_score=(1.0 if action == "BUY" else -1.0 if action == "SELL" else 0.0) * agreement,
            agent_votes=votes,
            market_scores=scores,
            confidence_components={"agreement": agreement, "fallback": 1.0},
            position_size=position_size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            execution_reason=(
                "Local paper fallback selected a conservative signal from public market data."
                if action != "HOLD" else None
            ),
            hold_reason=(
                "Local paper fallback found insufficient directional agreement."
                if action == "HOLD" else None
            ),
            summary=summary,
            engine_source="local_five_agent_fallback",
            engine_warning=reason,
        )

    async def analyze(self, symbol: str, market_data: Dict[str, Any] | None = None):
        market_data = dict(market_data or {})
        base_url = str(getattr(self.env, "AI_ENGINE_URL", "") or "").strip().rstrip("/") if self.env is not None else ""
        shared_secret = str(getattr(self.env, "AI_ENGINE_SHARED_SECRET", "") or "").strip() if self.env is not None else ""

        if not base_url or len(shared_secret) < 32:
            return self._local_fallback(symbol, market_data, "AI_ENGINE_URL/shared secret unavailable")

        payload = {
            "symbol": str(symbol).upper(),
            "market_data": market_data,
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
                raise RuntimeError(f"AI engine returned non-JSON response (HTTP {status_code})") from exc

            if status_code < 200 or status_code >= 300 or data.get("ok") is not True:
                detail = data.get("detail") or data.get("error") or f"HTTP {status_code}"
                raise RuntimeError(f"AI engine rejected analysis: {detail}")

            return SimpleNamespace(
                timestamp=self._timestamp(data.get("timestamp")),
                symbol=str(data.get("symbol") or symbol).upper(),
                current_price=self._number(data.get("current_price")),
                final_action=str(data.get("final_action") or "HOLD"),
                final_confidence=self._number(data.get("final_confidence")),
                consensus_action=data.get("consensus_action") or "HOLD",
                consensus_score=self._number(data.get("consensus_score")),
                agent_votes=dict(data.get("agent_votes") or {}),
                market_scores=dict(data.get("market_scores") or {}),
                confidence_components=dict(data.get("confidence_components") or {}),
                position_size=self._number(data.get("position_size")),
                stop_loss=data.get("stop_loss"),
                take_profit=data.get("take_profit"),
                execution_reason=data.get("execution_reason"),
                hold_reason=data.get("hold_reason"),
                summary=data.get("summary") or "AI engine completed analysis.",
                engine_source="fastapi_cloud",
                engine_warning=None,
            )
        except Exception as exc:
            return self._local_fallback(symbol, market_data, f"FastAPI Cloud unavailable: {type(exc).__name__}")


__all__ = ["CloudflareOrchestrator"]
