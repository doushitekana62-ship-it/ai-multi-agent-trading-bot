"""Canonical AI coordination pipeline.

Market data -> quality -> specialists -> bull/bear review -> one trader.
Risk and execution remain downstream deterministic controls.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

from agents.agent_decision import DecisionAgent, DecisionResult
from agents.agent_forecast import ForecastAgent, ForecastResult
from agents.agent_reflector import ReflectorAgent, ReflectionResult
from agents.agent_sentiment import SentimentAgent, SentimentResult
from agents.agent_technical import TechnicalAgent, TechnicalResult
from core.signal_contract import AnalyticalSignal, CycleStatus, SignalStatus, safe_float, utc_age_seconds
from core.unified_market_data import UnifiedMarketSnapshot, get_market_data_provider, create_snapshot_from_market_data

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorResult:
    timestamp: datetime
    symbol: str
    current_price: float
    unified_snapshot: Optional[UnifiedMarketSnapshot]
    sentiment: Optional[SentimentResult]
    technical: Optional[TechnicalResult]
    decision: Optional[DecisionResult]
    reflection: Optional[ReflectionResult]
    forecast: Optional[ForecastResult]
    consensus_action: str
    consensus_score: float
    agent_votes: Dict[str, str]
    final_action: str
    final_confidence: float
    position_size: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    decision_score: float
    confidence_components: Dict[str, float]
    market_scores: Dict[str, float]
    summary: str
    execution_reason: Optional[str] = None
    hold_reason: Optional[str] = None
    mimic_analysis: Any = None
    cycle_status: str = CycleStatus.ANALYZED.value
    conflict_review: Dict[str, Any] = field(default_factory=dict)
    signals: List[Dict[str, Any]] = field(default_factory=list)


class Orchestrator:
    """Single authoritative AI coordination point."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.market_data_provider = get_market_data_provider(self.config)
        self.use_unified_data = bool(self.config.get("use_unified_data", True))
        self.sentiment_agent = SentimentAgent(self.config.get("sentiment", {}))
        self.technical_agent = TechnicalAgent(self.config.get("technical", {}))
        self.forecast_agent = ForecastAgent(self.config.get("forecast", {}))
        self.decision_agent = DecisionAgent(self.config.get("decision", {}))
        self.reflector_agent = ReflectorAgent(self.config.get("reflector", {}))
        self.history: List[OrchestratorResult] = []
        self.max_history = int(self.config.get("max_history", 100))

    async def analyze(self, symbol: str, market_data: Optional[Dict[str, Any]] = None) -> OrchestratorResult:
        symbol = symbol.upper(); supplied = dict(market_data or {})
        if supplied.get("_force_action"):
            logger.warning("Force action is disabled in production orchestration; use replay tests instead.")

        snapshot = None
        if self.use_unified_data:
            snapshot = self.market_data_provider.get_snapshot(symbol)
            if snapshot is None or snapshot.is_stale(90):
                snapshot = self.market_data_provider.refresh_snapshot(symbol=symbol, timeframe=supplied.get("timeframe", "1m"), limit=180)
            if snapshot is None:
                snapshot = create_snapshot_from_market_data(self.market_data_provider, symbol, supplied)

        data = self._normalize_context(symbol, supplied, snapshot)
        quality, quality_reason = self._quality(data)
        if quality != SignalStatus.OK.value:
            return self._build_blocked(symbol, data, snapshot, quality_reason, quality)

        technical = self.technical_agent.analyze(symbol, data)
        forecast = self.forecast_agent.analyze(symbol, technical_result=technical, market_data=data)
        sentiment = self.sentiment_agent.analyze(symbol, data)
        signals = self._signals(symbol, technical, forecast, sentiment)
        debate = self._debate(signals, data)
        decision = self.decision_agent.analyze(symbol, sentiment, technical, data, forecast_result=forecast, debate=debate, evidence=signals)

        # No risk decision is made here. The returned action is a candidate only.
        action = decision.action
        cycle_status = CycleStatus.NO_EDGE.value if action == "HOLD" else CycleStatus.ANALYZED.value
        reason = decision.no_trade_reason or "CANDIDATE_READY_FOR_RISK_GATE"
        position_size = decision.suggested_position_size
        result = OrchestratorResult(
            timestamp=datetime.now(timezone.utc), symbol=symbol, current_price=data["unified_price"],
            unified_snapshot=snapshot, sentiment=sentiment, technical=technical, decision=decision,
            reflection=None, forecast=forecast, consensus_action=action, consensus_score=decision.action_score,
            agent_votes={s.agent: self._action_from_score(s.score) for s in signals if s.usable()},
            final_action=action, final_confidence=decision.confidence, position_size=position_size,
            stop_loss=None, take_profit=None, decision_score=decision.action_score,
            confidence_components={"evidence_agreement": 1.0 - decision.conflict_score, "candidate_confidence": decision.confidence},
            market_scores={s.agent: s.score for s in signals},
            summary=decision.summary, execution_reason=reason, hold_reason=reason if action == "HOLD" else None,
            cycle_status=cycle_status, conflict_review=debate, signals=[s.to_dict() for s in signals],
        )
        self.history.append(result); self.history = self.history[-self.max_history:]
        return result

    def _normalize_context(self, symbol, data, snapshot):
        if snapshot is not None:
            data["current_price"] = safe_float(snapshot.current_price)
            data["unified_price"] = safe_float(snapshot.current_price)
            data["_unified_snapshot"] = snapshot
            data["timestamp"] = snapshot.timestamp
            data.setdefault("ohlcv", [o.to_dict() if hasattr(o, "to_dict") else o for o in getattr(snapshot, "ohlcv_data", [])])
            data.setdefault("volume_24h", getattr(snapshot, "volume_24h", None))
            data.setdefault("volatility", getattr(snapshot, "volatility", None))
            data.setdefault("data_quality_score", getattr(snapshot, "data_quality_score", 0.0))
        data["symbol"] = symbol
        candles = data.get("ohlcv", []) or []
        closes=[]
        for c in candles:
            try: closes.append(safe_float(c.get("close") if isinstance(c,dict) else c.close))
            except AttributeError: pass
        for minutes, n in ((1,1),(5,5),(15,15),(30,30)):
            if len(closes) > n and closes[-n-1] > 0:
                data[f"movement_{minutes}m"] = closes[-1]/closes[-n-1]-1
            else:
                data[f"movement_{minutes}m"] = None
        return data

    def _quality(self, data):
        price=safe_float(data.get("unified_price")); ts=data.get("timestamp"); age=utc_age_seconds(ts)
        candles=data.get("ohlcv") or []
        missing=[f"movement_{x}m" for x in (1,5,15,30) if data.get(f"movement_{x}m") is None]
        if price <= 0 or len(candles) < 10: return SignalStatus.UNAVAILABLE.value, "INSUFFICIENT_MARKET_DATA"
        if age > 90: return SignalStatus.DEGRADED.value, "STALE_MARKET_DATA"
        if len(missing) >= 3: return SignalStatus.UNAVAILABLE.value, "SHORT_HORIZON_MOVEMENT_UNAVAILABLE"
        return SignalStatus.OK.value, "OK"

    @staticmethod
    def _signals(symbol, technical, forecast, sentiment):
        out=[]
        for name,r in (("technical",technical),("forecast",forecast),("sentiment",sentiment)):
            if r is None or getattr(r,"status",SignalStatus.UNAVAILABLE.value) == SignalStatus.UNAVAILABLE.value: continue
            score=safe_float(getattr(r,"overall_score",getattr(r,"forecast_score",0)))
            direction=getattr(r,"direction",None) or ("BULLISH" if score>0.1 else "BEARISH" if score<-0.1 else "NEUTRAL")
            out.append(AnalyticalSignal(agent=name,symbol=symbol,direction=direction,score=score,confidence=safe_float(getattr(r,"confidence",0)),timeframe=str(getattr(r,"timeframe","1m")),evidence=list(getattr(r,"evidence",[]) or []),data_timestamp=getattr(r,"timestamp",datetime.now(timezone.utc)),data_age_seconds=safe_float(getattr(r,"data_age_seconds",0)),status=getattr(r,"status",SignalStatus.OK.value)))
        return out

    @staticmethod
    def _debate(signals, data):
        usable=[s for s in signals if s.usable()]; bull=sorted([s for s in usable if s.score>0],key=lambda x:x.score*x.confidence,reverse=True); bear=sorted([s for s in usable if s.score<0],key=lambda x:-x.score*x.confidence,reverse=True)
        contradictions=[]
        if bull and bear: contradictions.append(f"Bull/bear conflict: {bull[0].agent} vs {bear[0].agent}")
        if not bull and not bear: contradictions.append("No directional evidence")
        conflict=0.0 if not bull or not bear else min(1.0,(bull[0].score*bull[0].confidence + (-bear[0].score)*bear[0].confidence)) / 2
        return {"bull_case":[f"{s.agent}: {s.score:+.2f} ({s.confidence:.0%})" for s in bull[:3]],"bear_case":[f"{s.agent}: {s.score:+.2f} ({s.confidence:.0%})" for s in bear[:3]],"contradictions":contradictions,"conflict_score":float(np.clip(conflict,0,1)),"missing_confirmation":[] if len(usable)>=2 else ["SECOND_INDEPENDENT_CONFIRMATION"]}

    @staticmethod
    def _action_from_score(score):
        return "BUY" if score>=0.20 else "SELL" if score<=-0.20 else "HOLD"

    def _build_blocked(self,symbol,data,snapshot,reason,status):
        now=datetime.now(timezone.utc); price=safe_float(data.get("unified_price"))
        return OrchestratorResult(now,symbol,price,snapshot,None,None,None,None,None,"HOLD",0.0,{},"HOLD",0.0,0.0,None,None,0.0,{}, {},f"Cycle blocked: {reason}",reason,None,None,status,{"contradictions":[reason]},[])
