"""Rule-based adaptive scalping gate.

Sentiment is advisory only. Technical structure, forecast, mimic-trader context
and short-term momentum remain the primary directional inputs.
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
        self.base_threshold = float(cfg.get("base_threshold", 0.18))
        self.momentum_threshold = float(cfg.get("momentum_threshold", 0.14))
        self.min_confidence = float(cfg.get("min_confidence", 0.48))
        self.max_position_multiplier = float(cfg.get("max_position_multiplier", 1.0))
        self.sentiment_weight = float(cfg.get("sentiment_weight", 0.06))
        self.technical_weight = float(cfg.get("technical_weight", 0.38))
        self.forecast_weight = float(cfg.get("forecast_weight", 0.24))
        self.mimic_weight = float(cfg.get("mimic_weight", 0.32))

    def evaluate(self, *, technical: float, sentiment: float, forecast: float,
                 mimic: float, momentum: float, volatility: float,
                 data_quality: float = 1.0) -> ScalpingSignal:
        score = (
            self.technical_weight * technical
            + self.sentiment_weight * sentiment
            + self.forecast_weight * forecast
            + self.mimic_weight * mimic
        )
        primary_values = [technical, forecast, mimic]
        bullish_primary = sum(1 for value in primary_values if value > 0.10)
        bearish_primary = sum(1 for value in primary_values if value < -0.10)
        agreement = max(bullish_primary, bearish_primary)
        confidence = max(
            0.0,
            min(
                1.0,
                0.46 + abs(score) * 0.48 + agreement * 0.045 + abs(momentum) * 0.10,
            ),
        )
        confidence *= max(0.0, min(1.0, data_quality))
        high_volatility = volatility >= 0.05
        threshold = self.momentum_threshold if abs(momentum) >= 0.35 else self.base_threshold
        if high_volatility:
            threshold += 0.08
        if confidence < self.min_confidence or abs(score) < threshold:
            return ScalpingSignal("HOLD", score, confidence, 0.0, "insufficient primary confirmation")
        if score > 0 and momentum >= -0.10 and bullish_primary >= 2:
            multiplier = min(self.max_position_multiplier, max(0.25, confidence))
            return ScalpingSignal("BUY", score, confidence, multiplier, "technical/forecast/trader bullish confirmation")
        if score < 0 and momentum <= 0.10 and bearish_primary >= 2:
            multiplier = min(self.max_position_multiplier, max(0.25, confidence))
            return ScalpingSignal("SELL", score, confidence, multiplier, "technical/forecast/trader bearish confirmation")
        return ScalpingSignal("HOLD", score, confidence, 0.0, "primary signals conflict with direction")
