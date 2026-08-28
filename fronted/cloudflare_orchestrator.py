"""Cloudflare-safe adapter for the CPython multi-agent AI engine.

The preferred path is the external FastAPI engine, which runs the repository's
full Orchestrator and agents. A deterministic local ensemble is kept as a
runtime fallback so paper mode and the dashboard remain usable when the
external service is temporarily unavailable. The fallback never submits
orders and only consumes public market observations.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict

from js import fetch
from pyodide.ffi import to_js


AGENT_NAMES = [
    "Sentiment Agent",
    "Technical Agent",
    "Decision Agent",
    "Forecast Agent",
    "Reflector Agent",
]


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, _number(value)))


class CloudflareOrchestrator:
    """Call FastAPI Cloud first, then fall back to a local safe ensemble."""

    def __init__(self, config: Dict[str, Any] | None = None, env: Any = None):
        self.config = config or {}
        self.env = env

    @staticmethod
    def _timestamp(value):
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return datetime.now(timezone.utc)

    def _local_fallback(self, symbol: str, market_data: Dict[str, Any], reason: str):
        """Produce a transparent, deterministic five-agent market ensemble."""
        current = _number(
            market_data.get("current_price")
            or market_data.get("unified_price")
            or market_data.get("price")
        )
        high = _number(market_data.get("high_24h"))
        low = _number(market_data.get("low_24h"))
        recent = list(market_data.get("recent_trades") or [])
        ohlcv = list(market_data.get("ohlcv") or [])
        prices = [_number(p.get("price") or p.get("close")) for p in (recent or ohlcv)]
        prices = [p for p in prices if p > 0]
        if len(prices) >= 2:
            start = prices[0]
            end = prices[-1]
            momentum = ((end - start) / start) * 100.0 if start else 0.0
        else:
            momentum = _number(market_data.get("change_percent_24h"))

        if high > low and current > 0:
            range_position = ((current - low) / (high - low)) * 100.0
        else:
            range_position = 50.0

        buy_volume = 0.0
        sell_volume = 0.0
        for trade in recent:
            amount = abs(_number(trade.get("amount"), 1.0))
            side = str(trade.get("side") or trade.get("type") or "").lower()
            if side in {"buy", "b"}:
                buy_volume += amount
            elif side in {"sell", "s"}:
                sell_volume += amount
        total_side = buy_volume + sell_volume
        flow_bias = ((buy_volume - sell_volume) / total_side) if total_side else 0.0

        technical_score = _clamp(0.50 + (momentum / 2.0) + ((range_position - 50.0) / 200.0))
        sentiment_score = _clamp(0.50 + flow_bias * 0.45)
        forecast_score = _clamp(0.50 + (momentum / 3.0) + ((range_position - 50.0) / 250.0))

        def vote(score: float, threshold: float = 0.54) -> str:
            if score >= threshold:
                return "BUY"
            if score <= 1.0 - threshold:
                return "SELL"
            return "HOLD"

        votes = {
            "Sentiment Agent": vote(sentiment_score, 0.56),
            "Technical Agent": vote(technical_score, 0.54),
            "Forecast Agent": vote(forecast_score, 0.55),
        }
        weighted = (
            sentiment_score * 0.25
            + technical_score * 0.35
            + forecast_score * 0.25
            + range_position / 100.0 * 0.15
        )
        decision = "BUY" if weighted >= 0.57 else "SELL" if weighted <= 0.43 else "HOLD"
        consensus = sum(1 for value in votes.values() if value == decision) / len(votes)
        risk_penalty = 0.10 if range_position >= 95 or range_position <= 5 else 0.0
        confidence = _clamp(0.50 + abs(weighted - 0.50) * 1.4 + consensus * 0.20 - risk_penalty, 0.40, 0.90)
        if decision == "HOLD":
            confidence = max(0.45, confidence - 0.05)

        votes["Decision Agent"] = decision
        votes["Reflector Agent"] = "HOLD" if risk_penalty else decision
        if risk_penalty:
            decision = "HOLD"
            confidence = min(confidence, 0.60)

        position_size = 0.0 if decision == "HOLD" else min(0.20, 0.05 + confidence * 0.15)
        stop_loss = current * 0.985 if decision == "BUY" and current > 0 else current * 1.015 if decision == "SELL" and current > 0 else None
        take_profit = current * 1.025 if decision == "BUY" and current > 0 else current * 0.975 if decision == "SELL" and current > 0 else None
        summary = (
            f"Local five-agent fallback: momentum={momentum:.3f}%, "
            f"range_position={range_position:.1f}%, flow_bias={flow_bias:.3f}. "
            f"Decision={decision} with confidence={confidence:.2f}."
        )
        return SimpleNamespace(
            timestamp=datetime.now(timezone.utc),
            symbol=str(symbol).upper(),
            current_price=current,
            final_action=decision,
            final_confidence=confidence,
            consensus_action=decision,
            consensus_score=consensus,
            agent_votes=votes,
            market_scores={
                "technical": technical_score,
                "sentiment": sentiment_score,
                "forecast": forecast_score,
                "range_position": range_position / 100.0,
            },
            confidence_components={
                "agent_consensus": consensus,
                "market_strength": abs(weighted - 0.50) * 2.0,
                "risk_penalty": risk_penalty,
            },
            position_size=position_size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            execution_reason=summary if decision != "HOLD" else None,
            hold_reason=summary if decision == "HOLD" else None,
            summary=f"{summary} Fallback reason: {reason}.",
            engine_source="local_multi_agent_fallback",
            engine_error=reason,
        )

    async def analyze(self, symbol: str, market_data: Dict[str, Any] | None = None):
        if self.env is None:
            return self._local_fallback(symbol, dict(market_data or {}), "worker_environment_unavailable")

        base_url = str(getattr(self.env, "AI_ENGINE_URL", "") or "").strip().rstrip("/")
        shared_secret = str(getattr(self.env, "AI_ENGINE_SHARED_SECRET", "") or "").strip()
        if not base_url or len(shared_secret) < 32:
            return self._local_fallback(symbol, dict(market_data or {}), "external_ai_engine_not_configured")

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
            except Exception:
                data = {}
            if status_code < 200 or status_code >= 300 or data.get("ok") is not True:
                detail = data.get("detail") or data.get("error") or f"HTTP {status_code}"
                return self._local_fallback(symbol, dict(market_data or {}), f"external_ai_engine_rejected:{detail}")

            return SimpleNamespace(
                timestamp=self._timestamp(data.get("timestamp")),
                symbol=str(data.get("symbol") or symbol).upper(),
                current_price=_number(data.get("current_price")),
                final_action=str(data.get("final_action") or "HOLD"),
                final_confidence=_clamp(data.get("final_confidence")),
                consensus_action=data.get("consensus_action") or "HOLD",
                consensus_score=_number(data.get("consensus_score")),
                agent_votes=dict(data.get("agent_votes") or {}),
                market_scores=dict(data.get("market_scores") or {}),
                confidence_components=dict(data.get("confidence_components") or {}),
                position_size=_clamp(data.get("position_size"), 0.0, 0.20),
                stop_loss=data.get("stop_loss"),
                take_profit=data.get("take_profit"),
                execution_reason=data.get("execution_reason"),
                hold_reason=data.get("hold_reason"),
                summary=data.get("summary") or "AI engine completed analysis.",
                engine_source="fastapi_cloud_orchestrator",
                engine_error=None,
            )
        except Exception as exc:
            return self._local_fallback(symbol, dict(market_data or {}), f"external_ai_engine_error:{type(exc).__name__}")
