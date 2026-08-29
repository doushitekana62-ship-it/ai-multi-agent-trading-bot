"""Cloudflare control-plane adapter for the external CPython AI engine.

FastAPI Cloud is preferred for the full CPython multi-agent Orchestrator. The
Worker also contains a bounded deterministic paper fallback so paper trading
remains functional when the external service is not configured or unavailable.
The fallback treats HOLD as neutral evidence rather than a veto and exposes
which agents are suppressing a directional signal.
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

    @staticmethod
    def _clip(value, low=-1.0, high=1.0):
        return max(low, min(high, value))

    @classmethod
    def _local_fallback(cls, symbol: str, market_data: Dict[str, Any], reason: str):
        """Bounded paper-only ensemble derived from the Trading Librarian rules.

        The local engine is deliberately conservative: price momentum, range
        location and liquidity are used as confirmation. A HOLD vote contributes
        zero directional pressure instead of cancelling BUY/SELL votes.
        """
        price = cls._number(market_data.get("current_price") or market_data.get("unified_price"))
        high = cls._number(market_data.get("high_24h"))
        low = cls._number(market_data.get("low_24h"))
        move = cls._number(market_data.get("change_percent_24h"))
        volume = cls._number(market_data.get("volume_24h"))

        if high > low > 0 and price > 0:
            range_position = cls._clip(((price - low) / (high - low)) * 100.0, 0.0, 100.0)
        else:
            range_position = 50.0

        # Trading Librarian principles: momentum must be confirmed by structure
        # and volume; support/resistance context matters; avoid chasing noise.
        momentum = cls._clip(move / 0.20)
        range_signal = ((range_position - 50.0) / 50.0)
        volume_confirmation = 0.15 if volume > 0 else 0.0

        sentiment = "BUY" if momentum >= 0.35 else "SELL" if momentum <= -0.35 else "HOLD"
        technical_score = cls._clip(momentum * 0.65 + range_signal * 0.35)
        technical = "BUY" if technical_score >= 0.25 else "SELL" if technical_score <= -0.25 else "HOLD"

        decision_score = cls._clip(technical_score * 0.60 + momentum * 0.25 + volume_confirmation * (1 if momentum > 0 else -1 if momentum < 0 else 0))
        decision = "BUY" if decision_score >= 0.30 else "SELL" if decision_score <= -0.30 else "HOLD"

        forecast_score = cls._clip(momentum * 0.70 + range_signal * 0.30)
        forecast = "BUY" if forecast_score >= 0.30 else "SELL" if forecast_score <= -0.30 else "HOLD"

        # Reflector has no closed paper trades yet, so it is deliberately neutral.
        reflector = "HOLD"

        votes = {
            "Sentiment Agent": sentiment,
            "Technical Agent": technical,
            "Decision Agent": decision,
            "Forecast Agent": forecast,
            "Reflector Agent": reflector,
        }
        scores = {
            "sentiment": cls._clip(momentum),
            "technical": technical_score,
            "decision": decision_score,
            "forecast": forecast_score,
            "mimic_trader": decision_score,
        }

        # Directional aggregation. HOLD is neutral, not a sixth negative signal.
        weights = {"sentiment": 0.18, "technical": 0.34, "decision": 0.25, "forecast": 0.15, "mimic_trader": 0.08}
        directional_score = sum(scores[key] * weights[key] for key in weights)
        directional_score = cls._clip(directional_score)

        # Require a meaningful move or a strong structural location before a
        # paper order. A flat market should legitimately remain HOLD.
        if directional_score >= 0.25:
            action = "BUY"
        elif directional_score <= -0.25:
            action = "SELL"
        else:
            action = "HOLD"

        directional_strength = abs(directional_score)
        confidence = cls._clip(0.45 + directional_strength * 0.70, 0.40, 0.85)
        if abs(move) < 0.03:
            confidence = min(confidence, 0.60)
            action = "HOLD"

        directional_agents = [name for name, vote in votes.items() if vote in {"BUY", "SELL", "STRONG_BUY", "STRONG_SELL"}]
        hold_agents = [name for name, vote in votes.items() if vote == "HOLD"]
        opposing_agents = []
        if action in {"BUY", "SELL"}:
            opposing_agents = [name for name, vote in votes.items() if vote not in {"HOLD", action}]

        if action == "BUY":
            position_size = min(0.10, max(0.01, confidence * 0.10))
            stop_loss = price * 0.97 if price > 0 else None
            take_profit = price * 1.03 if price > 0 else None
        elif action == "SELL":
            position_size = min(0.10, max(0.01, confidence * 0.10))
            stop_loss = price * 1.03 if price > 0 else None
            take_profit = price * 0.97 if price > 0 else None
        else:
            position_size = 0.0
            stop_loss = None
            take_profit = None

        consensus_score = directional_score
        hold_reason = (
            f"Flat/noisy market: recent move={move:.4f}% and directional score={directional_score:.3f}."
            if action == "HOLD"
            else None
        )
        summary = (
            f"Local paper engine: {action}; directional score={directional_score:.3f}; "
            f"move={move:.4f}%; range={range_position:.1f}%."
        )

        return SimpleNamespace(
            timestamp=datetime.now(timezone.utc),
            symbol=str(symbol).upper(),
            current_price=price,
            final_action=action,
            final_confidence=confidence,
            consensus_action=action,
            consensus_score=consensus_score,
            agent_votes=votes,
            market_scores={**scores, "consensus": consensus_score},
            confidence_components={
                "directional_score": directional_score,
                "directional_strength": directional_strength,
                "hold_vote_count": float(len(hold_agents)),
                "directional_vote_count": float(len(directional_agents)),
                "opposing_vote_count": float(len(opposing_agents)),
                "fallback": 1.0,
            },
            position_size=position_size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            execution_reason=(
                "Trading Librarian confirmation: momentum/structure support the directional signal."
                if action != "HOLD" else None
            ),
            hold_reason=hold_reason,
            summary=summary,
            engine_source="local_five_agent_fallback",
            engine_warning=reason,
            hold_agents=hold_agents,
            opposing_agents=opposing_agents,
        )

    async def analyze(self, symbol: str, market_data: Dict[str, Any] | None = None):
        market_data = dict(market_data or {})
        base_url = str(getattr(self.env, "AI_ENGINE_URL", "") or "").strip().rstrip("/") if self.env is not None else ""
        shared_secret = str(getattr(self.env, "AI_ENGINE_SHARED_SECRET", "") or "").strip() if self.env is not None else ""

        if not base_url or len(shared_secret) < 32:
            return self._local_fallback(symbol, market_data, "AI_ENGINE_URL/shared secret unavailable")

        payload = {"symbol": str(symbol).upper(), "market_data": market_data}

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
                hold_agents=[],
                opposing_agents=[],
            )
        except Exception as exc:
            return self._local_fallback(symbol, market_data, f"FastAPI Cloud unavailable: {type(exc).__name__}")


__all__ = ["CloudflareOrchestrator"]
