"""Cloudflare control-plane adapter for the external CPython AI engine."""
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
        price = cls._number(market_data.get("current_price") or market_data.get("unified_price"))
        high = cls._number(market_data.get("high_24h")); low = cls._number(market_data.get("low_24h"))
        move = cls._number(market_data.get("change_percent_24h")); volume = cls._number(market_data.get("volume_24h"))
        range_position = cls._clip(((price - low) / (high - low)) * 100.0, 0.0, 100.0) if high > low > 0 and price > 0 else 50.0
        momentum = cls._clip(move / 0.20); range_signal = (range_position - 50.0) / 50.0
        volume_confirmation = 0.15 if volume > 0 else 0.0
        sentiment = "BUY" if momentum >= 0.35 else "SELL" if momentum <= -0.35 else "HOLD"
        technical_score = cls._clip(momentum * 0.65 + range_signal * 0.35)
        technical = "BUY" if technical_score >= 0.25 else "SELL" if technical_score <= -0.25 else "HOLD"
        decision_score = cls._clip(technical_score * 0.60 + momentum * 0.25 + volume_confirmation * (1 if momentum > 0 else -1 if momentum < 0 else 0))
        decision = "BUY" if decision_score >= 0.30 else "SELL" if decision_score <= -0.30 else "HOLD"
        forecast_score = cls._clip(momentum * 0.70 + range_signal * 0.30)
        forecast = "BUY" if forecast_score >= 0.30 else "SELL" if forecast_score <= -0.30 else "HOLD"
        votes = {"Sentiment Agent": sentiment, "Technical Agent": technical, "Decision Agent": decision, "Forecast Agent": forecast, "Reflector Agent": "HOLD"}
        scores = {"sentiment": cls._clip(momentum), "technical": technical_score, "decision": decision_score, "forecast": forecast_score, "mimic_trader": decision_score}
        weights = {"sentiment": 0.18, "technical": 0.34, "decision": 0.25, "forecast": 0.15, "mimic_trader": 0.08}
        directional_score = cls._clip(sum(scores[key] * weights[key] for key in weights))
        action = "BUY" if directional_score >= 0.25 else "SELL" if directional_score <= -0.25 else "HOLD"
        confidence = cls._clip(0.45 + abs(directional_score) * 0.70, 0.40, 0.85)
        if abs(move) < 0.03:
            confidence = min(confidence, 0.60); action = "HOLD"
        hold_agents = [name for name, vote in votes.items() if vote == "HOLD"]
        directional_agents = [name for name, vote in votes.items() if vote in {"BUY", "SELL", "STRONG_BUY", "STRONG_SELL"}]
        opposing_agents = [name for name, vote in votes.items() if action in {"BUY", "SELL"} and vote not in {"HOLD", action}]
        position_size = min(0.10, max(0.01, confidence * 0.10)) if action in {"BUY", "SELL"} else 0.0
        stop_loss = take_profit = None
        if price > 0 and action == "BUY": stop_loss, take_profit = price * 0.97, price * 1.03
        if price > 0 and action == "SELL": stop_loss, take_profit = price * 1.03, price * 0.97
        hold_analysis = {"hold_agents": hold_agents, "directional_agents": directional_agents, "opposing_agents": opposing_agents, "dominant_hold_agent": max(hold_agents, key=lambda n: {"Sentiment Agent": .18, "Technical Agent": .30, "Decision Agent": .25, "Forecast Agent": .12, "Reflector Agent": 0}.get(n, 0), default=None), "fallback": True}
        return SimpleNamespace(
            timestamp=datetime.now(timezone.utc), symbol=str(symbol).upper(), current_price=price,
            final_action=action, final_confidence=confidence, consensus_action=action, consensus_score=directional_score,
            agent_votes=votes, market_scores={**scores, "consensus": directional_score},
            confidence_components={"directional_score": directional_score, "directional_strength": abs(directional_score), "hold_vote_count": float(len(hold_agents)), "directional_vote_count": float(len(directional_agents)), "opposing_vote_count": float(len(opposing_agents)), "fallback": 1.0},
            position_size=position_size, stop_loss=stop_loss, take_profit=take_profit,
            execution_reason="Trading Librarian confirmation unavailable; fallback is advisory only." if action != "HOLD" else None,
            hold_reason=f"Flat/noisy market: recent move={move:.4f}% and directional score={directional_score:.3f}." if action == "HOLD" else None,
            summary=f"Local paper fallback: {action}; score={directional_score:.3f}; move={move:.4f}%; range={range_position:.1f}%.",
            engine_source="local_five_agent_fallback", engine_warning=reason,
            hold_agents=hold_agents, opposing_agents=opposing_agents, hold_analysis=hold_analysis,
            knowledge_topics=[], candle_analysis={"available": False, "pattern": "UNAVAILABLE", "direction": "NEUTRAL"}, library_alerts=[], library_version="unavailable",
        )

    async def analyze(self, symbol: str, market_data: Dict[str, Any] | None = None):
        market_data = dict(market_data or {})
        base_url = str(getattr(self.env, "AI_ENGINE_URL", "") or "").strip().rstrip("/") if self.env is not None else ""
        shared_secret = str(getattr(self.env, "AI_ENGINE_SHARED_SECRET", "") or "").strip() if self.env is not None else ""
        if not base_url or len(shared_secret) < 32:
            return self._local_fallback(symbol, market_data, "AI_ENGINE_URL/shared secret unavailable")
        try:
            response = await fetch(f"{base_url}/engine/analyze", to_js({"method": "POST", "headers": {"Content-Type": "application/json", "Accept": "application/json", "X-AI-Engine-Key": shared_secret}, "body": json.dumps({"symbol": str(symbol).upper(), "market_data": market_data}, separators=(",", ":"))}))
            status_code = int(response.status); text = await response.text()
            try: data = json.loads(text)
            except Exception as exc: raise RuntimeError(f"AI engine returned non-JSON response (HTTP {status_code})") from exc
            if status_code < 200 or status_code >= 300 or data.get("ok") is not True:
                raise RuntimeError(f"AI engine rejected analysis: {data.get('detail') or data.get('error') or f'HTTP {status_code}'}")
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
            )
        except Exception as exc:
            return self._local_fallback(symbol, market_data, f"FastAPI Cloud unavailable: {type(exc).__name__}")


__all__ = ["CloudflareOrchestrator"]
