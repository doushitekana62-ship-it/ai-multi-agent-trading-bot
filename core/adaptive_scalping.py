"""Compatibility wrapper for the canonical trader pipeline.

This module no longer creates an independent BUY/SELL decision. The canonical
DecisionAgent owns action generation. Legacy callers may inspect a read-only
scalping observation, but it must not be used as an execution override.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict

@dataclass(frozen=True)
class ScalpingSignal:
    action: str
    score: float
    confidence: float
    position_multiplier: float
    reason: str

class AdaptiveScalpingEngine:
    def __init__(self, config: Dict | None = None):
        self.config=config or {}
        self.min_confidence=float(self.config.get("min_confidence",0.75))

    def from_decision(self, decision: Any) -> ScalpingSignal:
        action=str(getattr(decision,"action","HOLD")).upper()
        score=float(getattr(decision,"action_score",0.0) or 0.0)
        confidence=float(getattr(decision,"confidence",0.0) or 0.0)
        if action not in {"BUY","SELL"}: action="HOLD"
        return ScalpingSignal(action,score,confidence,float(getattr(decision,"suggested_position_size",0.0) or 0.0),"delegated to canonical DecisionAgent")

    def evaluate(self, **kwargs) -> ScalpingSignal:
        """Legacy API: observation only; never creates an execution action."""
        values=[float(kwargs.get(k,0.0) or 0.0) for k in ("technical","forecast","momentum")]
        score=sum(values)/len(values) if values else 0.0
        confidence=float(kwargs.get("data_quality",0.0) or 0.0)
        return ScalpingSignal("HOLD",score,confidence,0.0,"DEPRECATED_SECONDARY_DECISION_PATH_DISABLED")
