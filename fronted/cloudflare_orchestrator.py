"""Cloudflare control-plane adapter for the external CPython AI engine."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict

from js import fetch
from pyodide.ffi import to_js


class CloudflareOrchestrator:
    """Prefer FastAPI Cloud and use a deterministic, non-blocking fallback."""

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
            return number if number == number and number not in (float("inf"), float("-inf")) else default
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _clip(value, low=-1.0, high=1.0):
        return max(low, min(high, value))

    @classmethod
    def _local_fallback(cls, symbol: str, market_data: Dict[str, Any], reason: str):
        price = cls._number(market_data.get("current_price") or market_data.get("unified_price"))
        high = cls._number(market_data.get("high_24h")); low = cls._number(market_data.get("low_24h"))
        move = cls._number(market_data.get("short_term_move_percent", market_data.get("change_percent_24h")))
        volume = cls._number(market_data.get("volume_24h"))
        range_position = cls._clip(((price - low) / (high - low)) * 100.0, 0.0, 100.0) if high > low > 0 and price > 0 else 50.0
        momentum = cls._clip(move / 0.10)
        range_signal = (range_position - 50.0) / 50.0
        volume_confirmation = 0.12 if volume > 0 else 0.0

        # Sentiment is deliberately advisory: neutral sentiment contributes zero
        # and strong sentiment has only 8% of the directional score.
        sentiment_score = cls._clip(momentum * 0.55) if abs(momentum) >= 0.35 else 0.0
        technical_score = cls._clip(momentum * 0.70 + range_signal * 0.30)
        decision_score = cls._clip(technical_score * 0.65 + momentum * 0.25 + volume_confirmation * (1 if momentum > 0 else -1 if momentum < 0 else 0))
        forecast_score = cls._clip(momentum * 0.75 + range_signal * 0.25)
        mimic_score = decision_score
        scores = {"sentiment": sentiment_score, "technical": technical_score, "decision": decision_score, "forecast": forecast_score, "mimic_trader": mimic_score}
        weights = {"sentiment": 0.08, "technical": 0.34, "decision": 0.28, "forecast": 0.18, "mimic_trader": 0.12}
        consensus = cls._clip(sum(scores[key] * weights[key] for key in weights))
        action = "BUY" if consensus >= 0.22 else "SELL" if consensus <= -0.22 else "HOLD"
        if abs(move) < 0.01:
            action = "HOLD"
        confidence = cls._clip(0.46 + abs(consensus) * 0.70, 0.40, 0.90)
        votes = {
            "Sentiment Agent": "BUY" if sentiment_score >= 0.30 else "SELL" if sentiment_score <= -0.30 else "HOLD",
            "Technical Agent": "BUY" if technical_score >= 0.25 else "SELL" if technical_score <= -0.25 else "HOLD",
            "Decision Agent": "BUY" if decision_score >= 0.25 else "SELL" if decision_score <= -0.25 else "HOLD",
            "Forecast Agent": "BUY" if forecast_score >= 0.25 else "SELL" if forecast_score <= -0.25 else "HOLD",
            "Mimic Trader": "BUY" if mimic_score >= 0.25 else "SELL" if mimic_score <= -0.25 else "HOLD",
        }
        hold_agents = [name for name, vote in votes.items() if vote == "HOLD"]
        directional_agents = [name for name, vote in votes.items() if vote in {"BUY", "SELL"}]
        hold_analysis = {
            "hold_agents": hold_agents,
            "directional_agents": directional_agents,
            "opposing_agents": [],
            "dominant_hold_agent": max(hold_agents, key=lambda name: weights.get(name.lower().replace(" agent", "").replace("mimic trader", "mimic_trader"), 0), default=None),
            "sentiment_role": "advisory_non_blocking",
            "configured_weights": weights,
            "fallback": True,
        }
        position_size = min(0.10, max(0.01, confidence * 0.10)) if action in {"BUY", "SELL"} else 0.0
        stop_loss = take_profit = None
        if price > 0 and action == "BUY": stop_loss, take_profit = price * 0.97, price * 1.03
        if price > 0 and action == "SELL": stop_loss, take_profit = price * 1.03, price * 0.97
        return SimpleNamespace(
            timestamp=datetime.now(timezone.utc), symbol=str(symbol).upper(), current_price=price,
            final_action=action, final_confidence=confidence, consensus_action=action, consensus_score=consensus,
            agent_votes=votes, market_scores={**scores, "consensus": consensus},
            confidence_components={"directional_score": consensus, "directional_strength": abs(consensus), "hold_vote_count": float(len(hold_agents)), "directional_vote_count": float(len(directional_agents)), "opposing_vote_count": 0.0, "sentiment_role_advisory": 1.0, "fallback": 1.0},
            position_size=position_size, stop_loss=stop_loss, take_profit=take_profit,
            execution_reason=None, hold_reason=f"Directional score={consensus:.3f}; 30m/1m market pulse is monitored separately." if action == "HOLD" else None,
            summary=f"Local fallback: {action}; score={consensus:.3f}; move={move:.4f}%; source=INDODAX public data.",
            engine_source="local_five_agent_fallback", engine_warning=reason,
            hold_agents=hold_agents, opposing_agents=[], hold_analysis=hold_analysis,
            knowledge_topics=[], candle_analysis={"available": False, "pattern": "UNAVAILABLE", "direction": "NEUTRAL"}, library_alerts=[], library_version="unavailable",
        )

    async def analyze(self, symbol: str, market_data: Dict[str, Any] | None = None):
        market_data = dict(market_data or {})
        base_url = str(getattr(self.env, "AI_ENGINE_URL", "") or "").strip().rstrip("/") if self.env is not None else ""
        shared_secret = str(getattr(self.env, "AI_ENGINE_SHARED_SECRET", "") or "").strip() if self.env is not None else ""
        if not base_url or len(shared_secret) < 32:
            return self._local_fallback(symbol, market_data, "AI_ENGINE_URL/shared secret unavailable")
        try:
            response = await fetch(
                f"{base_url}/engine/analyze",
                to_js({
                    "method": "POST",
                    "headers": {"Content-Type": "application/json", "Accept": "application/json", "X-AI-Engine-Key": shared_secret},
                    "body": json.dumps({"symbol": str(symbol).upper(), "market_data": market_data}, separators=(",", ":")),
                }),
            )
            status_code = int(response.status); text = await response.text()
            try:
                data = json.loads(text)
            except Exception as exc:
                raise RuntimeError(f"AI engine returned non-JSON response (HTTP {status_code})") from exc
            if status_code < 200 or status_code >= 300 or data.get("ok") is not True:
                raise RuntimeError(data.get("detail") or data.get("error") or f"HTTP {status_code}")
            return SimpleNamespace(
                timestamp=self._timestamp(data.get("timestamp")), symbol=str(data.get("symbol") or symbol).upper(), current_price=self._number(data.get("current_price")),
                final_action=str(data.get("final_action") or "HOLD"), final_confidence=self._number(data.get("final_confidence")),
                consensus_action=data.get("consensus_action") or "HOLD", consensus_score=self._number(data.get("consensus_score")),
                agent_votes=dict(data.get("agent_votes") or {}), market_scores=dict(data.get("market_scores") or {}), confidence_components=dict(data.get("confidence_components") or {}),
                position_size=self._number(data.get("position_size")), stop_loss=data.get("stop_loss"), take_profit=data.get("take_profit"),
                execution_reason=data.get("execution_reason"), hold_reason=data.get("hold_reason"), summary=data.get("summary") or "AI engine completed analysis.",
                engine_source="fastapi_cloud", engine_warning=None, hold_agents=list(data.get("hold_analysis", {}).get("hold_agents") or []),
                opposing_agents=list(data.get("hold_analysis", {}).get("opposing_agents") or []), hold_analysis=dict(data.get("hold_analysis") or {}),
                knowledge_topics=list(data.get("knowledge_topics") or []), candle_analysis=dict(data.get("candle_analysis") or {}),
                library_alerts=list(data.get("library_alerts") or [])[:4], library_version=str(data.get("library_version") or "unknown"),
                agent_details=dict(data.get("agent_details") or {}),
            )
        except Exception as exc:
            return self._local_fallback(symbol, market_data, f"FastAPI Cloud unavailable: {type(exc).__name__}")


__all__ = ["CloudflareOrchestrator"]
