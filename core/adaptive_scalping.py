"""Rule-based adaptive scalping gate.

This is deliberately deterministic and transparent. It does not promise profit or
force trades. It lowers entry friction only when multiple independent market
signals agree, while increasing caution in high-volatility or low-quality data.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class ScalpingSignal:
    action: str
    score: float
    confidence: float
    position_multiplier: float
    reason: str


class AdaptiveScalpingEngine:
    def __init__(self, config: Dict | None = None):
        cfg = config or {}
        self.base_threshold = float(cfg.get("base_threshold", 0.25))
        self.momentum_threshold = float(cfg.get("momentum_threshold", 0.18))
        self.min_confidence = float(cfg.get("min_confidence", 0.48))
        self.max_position_multiplier = float(cfg.get("max_position_multiplier", 1.0))

    def evaluate(self, *, technical: float, sentiment: float, forecast: float,
                 mimic: float, momentum: float, volatility: float,
                 data_quality: float = 1.0) -> ScalpingSignal:
        values = [technical, sentiment, forecast, mimic]
        score = 0.35 * technical + 0.10 * sentiment + 0.20 * forecast + 0.35 * mimic
        agreement = sum(1 for value in values if value > 0.12) if score > 0 else sum(1 for value in values if value < -0.12)
        confidence = max(0.0, min(1.0, 0.45 + abs(score) * 0.45 + agreement * 0.04 + abs(momentum) * 0.10))
        confidence *= max(0.0, min(1.0, data_quality))
        high_volatility = volatility >= 0.05
        threshold = self.momentum_threshold if abs(momentum) >= 0.35 else self.base_threshold
        if high_volatility:
            threshold += 0.08
        if confidence < self.min_confidence or abs(score) < threshold:
            return ScalpingSignal("HOLD", score, confidence, 0.0, "insufficient confirmation")
        if score > 0 and momentum >= -0.10:
            multiplier = min(self.max_position_multiplier, max(0.25, confidence))
            return ScalpingSignal("BUY", score, confidence, multiplier, "multi-signal bullish confirmation")
        if score < 0 and momentum <= 0.10:
            multiplier = min(self.max_position_multiplier, max(0.25, confidence))
            return ScalpingSignal("SELL", score, confidence, multiplier, "multi-signal bearish confirmation")
        return ScalpingSignal("HOLD", score, confidence, 0.0, "momentum conflicts with direction")
