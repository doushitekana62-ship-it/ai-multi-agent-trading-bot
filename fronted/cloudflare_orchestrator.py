"""Cloudflare control-plane adapter for the canonical AI engine.

The external FastAPI engine is preferred. If it is unavailable, the fallback is
not a fake five-agent consensus: it is an explicitly degraded deterministic
market-data analysis using independent momentum, structure and volume evidence.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List

from js import fetch
from pyodide.ffi import to_js


class CloudflareOrchestrator:
    """API adapter; fallback remains evidence-driven and cannot bypass risk."""

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
        return max(low, min(high, float(value)))

    @staticmethod
    def _trade_timestamp(point):
        value = CloudflareOrchestrator._number(point.get("timestamp") or point.get("date"))
        return value / 1000.0 if value > 1_000_000_000_000 else value

    @classmethod
    def _build_ohlcv_from_trades(cls, points: List[Dict[str, Any]], now_ts: float | None = None) -> List[Dict[str, Any]]:
        now_ts = float(now_ts or datetime.now(timezone.utc).timestamp())
        current_bucket = int(now_ts // 60) * 60
        buckets: Dict[int, Dict[str, Any]] = {}
        for point in points or []:
            ts = cls._trade_timestamp(point)
            price = cls._number(point.get("price"))
            amount = max(0.0, cls._number(point.get("amount"), 0.0))
            if ts <= 0 or price <= 0:
                continue
            bucket = int(ts // 60) * 60
            if bucket < current_bucket - 180 * 60 or bucket > current_bucket:
                continue
            row = buckets.setdefault(bucket, {"timestamp": bucket * 1000, "open": price, "high": price, "low": price, "close": price, "volume": 0.0, "trades": 0})
            row["high"] = max(row["high"], price)
            row["low"] = min(row["low"], price)
            row["close"] = price
            row["volume"] += amount
            row["trades"] += 1
        return [buckets[k] for k in sorted(buckets)]

    @classmethod
    def _market_features(cls, market_data: Dict[str, Any]) -> Dict[str, Any]:
        candles = list(market_data.get("ohlcv") or [])
        if not candles:
            candles = cls._build_ohlcv_from_trades(list(market_data.get("recent_trades") or []))
            if candles:
                market_data["ohlcv"] = candles
        closes = [cls._number(c.get("close")) for c in candles if cls._number(c.get("close")) > 0]
        volumes = [max(0.0, cls._number(c.get("volume"))) for c in candles]

        def ret(n: int):
            return (closes[-1] / closes[-n - 1] - 1.0) * 100.0 if len(closes) > n and closes[-n - 1] > 0 else None

        m1 = market_data.get("move_1m_pct") if market_data.get("move_1m_pct") is not None else ret(1)
        m5 = market_data.get("move_5m_pct") if market_data.get("move_5m_pct") is not None else ret(5)
        m15 = market_data.get("move_15m_pct") if market_data.get("move_15m_pct") is not None else ret(15)
        m30 = market_data.get("move_30m_pct") if market_data.get("move_30m_pct") is not None else ret(30)

        momentum = cls._clip((cls._number(m1) / 0.05) * 0.45 + (cls._number(m5) / 0.15) * 0.35 + (cls._number(m15) / 0.30) * 0.20)
        structure = 0.0
        if len(candles) >= 10:
            recent = candles[-5:]; prior = candles[-10:-5]
            recent_high = max(cls._number(c.get("high")) for c in recent); prior_high = max(cls._number(c.get("high")) for c in prior)
            recent_low = min(cls._number(c.get("low")) for c in recent); prior_low = min(cls._number(c.get("low")) for c in prior)
            if recent_high > prior_high and recent_low > prior_low: structure = 1.0
            elif recent_high < prior_high and recent_low < prior_low: structure = -1.0
            elif recent_high > prior_high: structure = 0.35
            elif recent_low < prior_low: structure = -0.35

        volume = 0.0; volume_ratio = 1.0
        if len(volumes) >= 10:
            baseline = sum(volumes[-10:-1]) / 9.0
            volume_ratio = volumes[-1] / baseline if baseline > 0 else 1.0
            volume = cls._clip((volume_ratio - 1.0) / 0.75)

        pattern = 0.0; pattern_name = "NONE"
        if len(candles) >= 2:
            a, b = candles[-2], candles[-1]
            ao, ac = cls._number(a.get("open")), cls._number(a.get("close")); bo, bh, bl, bc = cls._number(b.get("open")), cls._number(b.get("high")), cls._number(b.get("low")), cls._number(b.get("close"))
            body = abs(bc - bo); rng = max(bh - bl, bc * 1e-9)
            if ac < ao and bc > bo and bo <= ac and bc >= ao and body >= rng * 0.30: pattern, pattern_name = 0.70, "BULLISH_ENGULFING"
            elif ac > ao and bc < bo and bo >= ac and bc <= ao and body >= rng * 0.30: pattern, pattern_name = -0.70, "BEARISH_ENGULFING"

        direction_sign = 1 if momentum > 0.12 else -1 if momentum < -0.12 else 0
        confirmations = sum([
            bool(direction_sign and momentum * direction_sign >= 0.20),
            bool(direction_sign and structure * direction_sign >= 0.20),
            bool(direction_sign and volume >= 0.10),
            bool(direction_sign and pattern * direction_sign >= 0.40),
        ])
        combined = cls._clip(momentum * 0.50 + structure * 0.30 + volume * 0.10 + pattern * 0.10)
        if direction_sign < 0 and combined > 0: combined = -abs(combined)
        if direction_sign > 0 and combined < 0: combined = abs(combined)
        opportunity = min(1.0, abs(combined) * 0.70 + min(confirmations / 3.0, 1.0) * 0.30)
        confidence = cls._clip(0.48 + abs(combined) * 0.22 + min(confirmations / 3.0, 1.0) * 0.22, 0.0, 0.82)
        return {"candles": candles, "move_1m_pct": m1, "move_5m_pct": m5, "move_15m_pct": m15, "move_30m_pct": m30, "momentum": momentum, "structure": structure, "volume": volume, "volume_ratio": volume_ratio, "pattern": pattern, "pattern_name": pattern_name, "confirmations": confirmations, "combined": combined, "opportunity": opportunity, "confidence": confidence}

    @classmethod
    def _local_fallback(cls, symbol: str, market_data: Dict[str, Any], reason: str):
        price = cls._number(market_data.get("current_price") or market_data.get("unified_price"))
        features = cls._market_features(market_data); combined = features["combined"]; confirmations = features["confirmations"]; opportunity = features["opportunity"]
        confidence = features["confidence"] * 0.92
        if confirmations >= 2 and opportunity >= 0.55 and confidence >= 0.60:
            action = "BUY" if combined > 0 else "SELL"
        else:
            action = "HOLD"
        votes = {"Momentum Analyst": "BUY" if features["momentum"] >= 0.20 else "SELL" if features["momentum"] <= -0.20 else "NEUTRAL", "Structure Analyst": "BUY" if features["structure"] >= 0.20 else "SELL" if features["structure"] <= -0.20 else "NEUTRAL", "Volume/Pattern Analyst": "BUY" if features["volume"] + features["pattern"] >= 0.20 else "SELL" if features["volume"] + features["pattern"] <= -0.20 else "NEUTRAL"}
        usable = [v for v in votes.values() if v in {"BUY", "SELL"}]
        opposing = "BUY" in usable and "SELL" in usable
        if opposing:
            action = "HOLD"; confidence *= 0.80
        details = {"momentum": {"score": features["momentum"], "status": "OK"}, "structure": {"score": features["structure"], "status": "OK"}, "volume_pattern": {"score": features["volume"] + features["pattern"], "status": "OK"}}
        return SimpleNamespace(
            timestamp=datetime.now(timezone.utc), symbol=str(symbol).upper(), current_price=price, final_action=action, final_confidence=confidence, consensus_action=action, consensus_score=combined,
            agent_votes=votes, market_scores={"momentum": features["momentum"], "structure": features["structure"], "volume": features["volume"], "pattern": features["pattern"], "consensus": combined},
            confidence_components={"opportunity_score": opportunity, "confirmations": float(confirmations), "data_quality": 1.0 if features["candles"] else 0.0, "ai_degraded": 1.0},
            position_size=min(0.06, max(0.0, confidence * 0.06)) if action in {"BUY", "SELL"} else 0.0,
            stop_loss=price * (0.985 if action == "BUY" else 1.015) if price > 0 and action in {"BUY", "SELL"} else None,
            take_profit=price * (1.025 if action == "BUY" else 0.975) if price > 0 and action in {"BUY", "SELL"} else None,
            execution_reason="DEGRADED_MARKET_FALLBACK_CANDIDATE" if action in {"BUY", "SELL"} else None,
            hold_reason="NO_DIRECTIONAL_EDGE" if action == "HOLD" else None,
            summary=f"Deterministic degraded analysis: {action}; score={combined:+.3f}; confirmations={confirmations}; pattern={features['pattern_name']}; AI unavailable={reason}.",
            engine_source="deterministic_market_fallback", engine_warning=reason, hold_agents=[name for name, vote in votes.items() if vote == "NEUTRAL"], opposing_agents=["BUY vs SELL evidence"] if opposing else [],
            hold_analysis={"fallback": True, "reason": reason, "independent_evidence": votes, "confirmations": confirmations, "opportunity_score": opportunity}, knowledge_topics=["momentum", "market structure", "volume", "candlestick"],
            candle_analysis={"available": bool(features["candles"]), "pattern": features["pattern_name"], "direction": "BUY" if features["pattern"] > 0 else "SELL" if features["pattern"] < 0 else "NEUTRAL"},
            library_alerts=[], library_version="deterministic-market-library-v2", cycle_status="AI_DEGRADED" if action == "HOLD" else "ANALYZED", agent_details=details,
            sentiment=SimpleNamespace(**details["volume_pattern"]), technical=SimpleNamespace(**details["structure"]), decision=SimpleNamespace(**{"score": combined}), forecast=SimpleNamespace(**details["momentum"]), reflection=None, mimic_analysis=None,
        )

    async def analyze(self, symbol: str, market_data: Dict[str, Any] | None = None):
        market_data = dict(market_data or {})
        base_url = str(getattr(self.env, "AI_ENGINE_URL", "") or "").strip().rstrip("/") if self.env is not None else ""
        shared_secret = str(getattr(self.env, "AI_ENGINE_SHARED_SECRET", "") or "").strip() if self.env is not None else ""
        if not market_data.get("ohlcv") and market_data.get("recent_trades"):
            market_data["ohlcv"] = self._build_ohlcv_from_trades(market_data.get("recent_trades") or [])
        if not base_url or len(shared_secret) < 32:
            return self._local_fallback(symbol, market_data, "AI_ENGINE_URL/shared secret unavailable")
        try:
            response = await fetch(f"{base_url}/engine/analyze", to_js({"method": "POST", "headers": {"Content-Type": "application/json", "Accept": "application/json", "X-AI-Engine-Key": shared_secret}, "body": json.dumps({"symbol": str(symbol).upper(), "market_data": market_data}, separators=(",", ":"))}))
            status_code = int(response.status); text = await response.text()
            try: data = json.loads(text)
            except Exception as exc: raise RuntimeError(f"AI engine returned non-JSON response (HTTP {status_code})") from exc
            if status_code < 200 or status_code >= 300 or data.get("ok") is not True:
                raise RuntimeError(data.get("detail") or data.get("error") or f"HTTP {status_code}")
            details = dict(data.get("agent_details") or {})
            def detail(name): return SimpleNamespace(**(details.get(name) or {}))
            return SimpleNamespace(
                timestamp=self._timestamp(data.get("timestamp")), symbol=str(data.get("symbol") or symbol).upper(), current_price=self._number(data.get("current_price")), final_action=str(data.get("final_action") or "HOLD"), final_confidence=self._number(data.get("final_confidence")),
                consensus_action=data.get("consensus_action") or "HOLD", consensus_score=self._number(data.get("consensus_score")), agent_votes=dict(data.get("agent_votes") or {}), market_scores=dict(data.get("market_scores") or {}), confidence_components=dict(data.get("confidence_components") or {}),
                position_size=self._number(data.get("position_size")), stop_loss=data.get("stop_loss"), take_profit=data.get("take_profit"), execution_reason=data.get("execution_reason"), hold_reason=data.get("hold_reason"), summary=data.get("summary") or "AI engine completed analysis.",
                engine_source="fastapi_cloud", engine_warning=None, hold_agents=list(data.get("hold_analysis", {}).get("hold_agents") or []), opposing_agents=list(data.get("hold_analysis", {}).get("opposing_agents") or []), hold_analysis=dict(data.get("hold_analysis") or {}),
                knowledge_topics=list(data.get("knowledge_topics") or []), candle_analysis=dict(data.get("candle_analysis") or {}), library_alerts=list(data.get("library_alerts") or [])[:4], library_version=str(data.get("library_version") or "unknown"), agent_details=details, cycle_status=str(data.get("cycle_status") or "ANALYZED"),
                sentiment=detail("sentiment"), technical=detail("technical"), decision=detail("decision"), forecast=detail("forecast"), reflection=detail("reflection"), mimic_analysis=detail("mimic_trader"),
            )
        except Exception as exc:
            return cls._local_fallback(symbol, market_data, f"FastAPI Cloud unavailable: {type(exc).__name__}")


__all__ = ["CloudflareOrchestrator"]