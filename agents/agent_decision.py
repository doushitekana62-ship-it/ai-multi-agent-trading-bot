"""Trader / Decision Synthesizer.

This is the only specialist-facing component allowed to turn analytical
 evidence into BUY/SELL/HOLD. Risk is deliberately excluded from directional
 scoring and remains a deterministic downstream gate.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

from core.signal_contract import AnalyticalSignal, SignalDirection, SignalStatus, safe_float

logger = logging.getLogger(__name__)


@dataclass
class DecisionResult:
    symbol: str
    timestamp: datetime
    action: str
    action_score: float
    confidence: float
    sentiment_score: float
    technical_score: float
    risk_score: float
    market_context_score: float
    reasoning: List[str]
    factors_considered: Dict[str, Any]
    alternative_actions: List[str]
    suggested_position_size: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    time_horizon: str
    final_decision: str
    summary: str
    direction: str = "NEUTRAL"
    evidence: List[str] = None
    conflict_score: float = 0.0
    opportunity_score: float = 0.0
    status: str = SignalStatus.OK.value
    cycle_status: str = "ANALYZED"
    no_trade_reason: str = ""

    def __post_init__(self):
        if self.evidence is None:
            self.evidence = []


class DecisionAgent:
    """Single Trader layer: evidence -> candidate action.

    It does not approve risk, size a portfolio authoritatively, or execute.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self.min_candidate_score = float(cfg.get("min_candidate_score", 0.55))
        self.min_confidence = float(cfg.get("min_confidence", 0.60))
        self.execution_confidence = float(cfg.get("execution_confidence", 0.75))
        self.min_confirmations = int(cfg.get("min_confirmations", 2))
        self.max_conflict = float(cfg.get("max_conflict", 0.45))
        self.history: List[DecisionResult] = []

    def analyze(
        self,
        symbol: str,
        sentiment_result: Any = None,
        technical_result: Any = None,
        market_data: Optional[Dict[str, Any]] = None,
        forecast_result: Any = None,
        debate: Optional[Dict[str, Any]] = None,
        evidence: Optional[List[AnalyticalSignal]] = None,
    ) -> DecisionResult:
        symbol = str(symbol).upper()
        market_data = market_data or {}
        signals = evidence or self._build_signals(sentiment_result, technical_result, forecast_result, market_data)
        usable = [s for s in signals if isinstance(s, AnalyticalSignal) and s.usable()]

        current_price = safe_float(market_data.get("unified_price", market_data.get("current_price")))
        if not usable:
            return self._result(symbol, current_price, "HOLD", 0.0, 0.0,
                                "NO_USABLE_ANALYTICAL_EVIDENCE", signals)

        bull = sum(max(0.0, s.score) * s.confidence for s in usable)
        bear = sum(max(0.0, -s.score) * s.confidence for s in usable)
        total = bull + bear
        directional = (bull - bear) / total if total else 0.0
        agreement = self._agreement(usable)
        conflict = 1.0 - agreement

        # Independent confirmations: only materially directional evidence counts.
        bullish_confirmations = sum(1 for s in usable if s.score >= 0.20)
        bearish_confirmations = sum(1 for s in usable if s.score <= -0.20)
        confirmations = max(bullish_confirmations, bearish_confirmations)

        debate_penalty = float((debate or {}).get("conflict_score", 0.0))
        conflict_score = max(conflict, debate_penalty)
        opportunity = min(1.0, abs(directional) * 0.70 + min(confirmations / 3.0, 1.0) * 0.20 + agreement * 0.10)
        confidence = float(np.clip(
            0.45 * agreement + 0.35 * min(abs(directional) * 1.5, 1.0) + 0.20 * min(confirmations / 3.0, 1.0),
            0.0, 0.95
        ))

        if conflict_score > self.max_conflict:
            action = "HOLD"
            reason = "MATERIAL_AGENT_CONFLICT"
        elif opportunity < self.min_candidate_score or confirmations < self.min_confirmations:
            action = "HOLD"
            reason = "NO_DIRECTIONAL_EDGE"
        elif confidence < self.min_confidence:
            action = "HOLD"
            reason = "INSUFFICIENT_CONFIDENCE"
        elif directional >= 0.70:
            action = "BUY"
            reason = "BULLISH_EDGE"
        elif directional <= -0.70:
            action = "SELL"
            reason = "BEARISH_EDGE"
        elif directional > 0:
            action = "BUY"
            reason = "BULLISH_EDGE"
        else:
            action = "SELL"
            reason = "BEARISH_EDGE"

        direction = "BULLISH" if directional > 0.10 else "BEARISH" if directional < -0.10 else "NEUTRAL"
        evidence_text = []
        for s in usable:
            evidence_text.append(f"{s.agent}: {s.direction} score={s.score:+.2f} conf={s.confidence:.0%}")
        if debate:
            evidence_text.extend([str(x) for x in debate.get("contradictions", [])[:3]])

        # Position size here is only a proposal; deterministic risk owns final sizing.
        proposed_size = 0.0 if action == "HOLD" else min(0.10, abs(directional) * confidence * 0.15)
        result = DecisionResult(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            action=action,
            action_score=float(np.clip(directional, -1, 1)),
            confidence=confidence,
            sentiment_score=self._score_of(sentiment_result),
            technical_score=self._score_of(technical_result),
            risk_score=0.0,
            market_context_score=self._market_context_score(market_data),
            reasoning=[reason] + evidence_text[:8],
            factors_considered={
                "directional_score": directional,
                "agreement": agreement,
                "conflict_score": conflict_score,
                "confirmations": confirmations,
                "opportunity_score": opportunity,
                "usable_agents": [s.agent for s in usable],
            },
            alternative_actions=[x for x in ("BUY", "SELL", "HOLD") if x != action],
            suggested_position_size=proposed_size,
            stop_loss=None,
            take_profit=None,
            time_horizon=str(market_data.get("timeframe", "scalp")),
            final_decision=action,
            summary=f"Trader {symbol}: {action}, edge={directional:+.2f}, confidence={confidence:.0%}, conflict={conflict_score:.0%}",
            direction=direction,
            evidence=evidence_text,
            conflict_score=conflict_score,
            opportunity_score=opportunity,
            status=SignalStatus.OK.value,
            cycle_status="NO_EDGE" if action == "HOLD" else "ANALYZED",
            no_trade_reason=reason if action == "HOLD" else "",
        )
        self.history.append(result)
        self.history = self.history[-100:]
        return result

    def _build_signals(self, sentiment, technical, forecast, market_data):
        signals = []
        for name, result in (("technical", technical), ("forecast", forecast), ("sentiment", sentiment)):
            if result is None:
                continue
            score = self._score_of(result)
            confidence = safe_float(getattr(result, "confidence", 0.0))
            status = getattr(result, "status", SignalStatus.OK.value)
            if status == "UNAVAILABLE":
                continue
            direction = getattr(result, "direction", None)
            if not direction:
                direction = "BULLISH" if score > 0.10 else "BEARISH" if score < -0.10 else "NEUTRAL"
            signals.append(AnalyticalSignal(
                agent=name, symbol=getattr(result, "symbol", market_data.get("symbol", "")),
                direction=direction, score=score, confidence=confidence,
                timeframe=str(getattr(result, "timeframe", market_data.get("timeframe", "1m"))),
                evidence=list(getattr(result, "evidence", []) or []),
                data_timestamp=getattr(result, "timestamp", datetime.now(timezone.utc)),
                data_age_seconds=safe_float(getattr(result, "data_age_seconds", 0.0)),
                status=status,
            ))
        return signals

    @staticmethod
    def _score_of(result):
        return safe_float(getattr(result, "overall_score", getattr(result, "forecast_score", getattr(result, "score", 0.0)))) if result else 0.0

    @staticmethod
    def _market_context_score(data):
        m1 = safe_float(data.get("movement_1m"))
        m5 = safe_float(data.get("movement_5m"))
        return float(np.clip(m1 * 15 + m5 * 5, -1, 1))

    @staticmethod
    def _agreement(signals):
        if not signals:
            return 0.0
        weights = [max(0.01, s.confidence * abs(s.score)) for s in signals]
        signed = [1 if s.score > 0.05 else -1 if s.score < -0.05 else 0 for s in signals]
        total = sum(weights)
        if total <= 0:
            return 0.0
        dominant = max(sum(w for w, x in zip(weights, signed) if x == 1), sum(w for w, x in zip(weights, signed) if x == -1))
        return float(np.clip(dominant / total, 0.0, 1.0))

    def _result(self, symbol, price, action, score, confidence, reason, signals):
        return DecisionResult(symbol=symbol, timestamp=datetime.now(timezone.utc), action=action,
            action_score=score, confidence=confidence, sentiment_score=0.0, technical_score=0.0,
            risk_score=0.0, market_context_score=0.0, reasoning=[reason], factors_considered={},
            alternative_actions=["BUY", "SELL"], suggested_position_size=0.0, stop_loss=None,
            take_profit=None, time_horizon="scalp", final_decision=action,
            summary=f"Trader {symbol}: {action} — {reason}", direction="NEUTRAL",
            evidence=[], status=SignalStatus.UNAVAILABLE.value, cycle_status="DATA_UNAVAILABLE",
            no_trade_reason=reason)
