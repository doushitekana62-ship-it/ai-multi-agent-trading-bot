"""Regime-aware scalping controller.

This layer converts multi-agent scores plus short-horizon market structure into a
scalping *setup*. It does not place orders and never overrides risk controls.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Sequence


@dataclass(frozen=True)
class ScalpingSetup:
    action: str
    setup: str
    score: float
    confidence: float
    position_multiplier: float
    stop_distance_pct: float
    take_profit_pct: float
    reason: str
    regime: str
    confirmations: int


class ScalpingController:
    """Generate conservative short-horizon setups from existing agent outputs."""

    def __init__(self, config: Optional[Dict] = None):
        cfg = config or {}
        self.min_score = float(cfg.get("min_score", 0.28))
        self.min_confidence = float(cfg.get("min_confidence", 0.55))
        self.min_confirmations = int(cfg.get("min_confirmations", 3))
        self.high_volatility = float(cfg.get("high_volatility", 0.05))
        self.max_position_multiplier = float(cfg.get("max_position_multiplier", 0.75))
        self.exit_score = float(cfg.get("exit_score", 0.50))
        self.exit_min_confirmations = int(cfg.get("exit_min_confirmations", 3))

    @staticmethod
    def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
        return max(low, min(high, float(value)))

    @staticmethod
    def _momentum_from_prices(prices: Sequence[float]) -> float:
        if len(prices) < 4 or prices[0] <= 0:
            return 0.0
        ret = (prices[-1] - prices[-4]) / prices[-4]
        return max(-1.0, min(1.0, ret / 0.01))

    @staticmethod
    def _trend_from_prices(prices: Sequence[float]) -> float:
        if len(prices) < 8:
            return 0.0
        fast = sum(prices[-4:]) / 4.0
        slow = sum(prices[-8:]) / 8.0
        if slow <= 0:
            return 0.0
        return max(-1.0, min(1.0, ((fast / slow) - 1.0) / 0.005))

    @staticmethod
    def _volume_confirmation(volumes: Sequence[float]) -> float:
        if len(volumes) < 6:
            return 0.0
        baseline = sum(volumes[-6:-1]) / 5.0
        if baseline <= 0:
            return 0.0
        return max(-1.0, min(1.0, (volumes[-1] / baseline - 1.0) / 0.5))

    def _score_components(self, *, technical: float, sentiment: float, forecast: float, mimic: float, decision: float, prices: Sequence[float]):
        momentum = self._momentum_from_prices(prices)
        trend = self._trend_from_prices(prices)
        score = (
            technical * 0.25
            + forecast * 0.15
            + mimic * 0.15
            + decision * 0.15
            + sentiment * 0.05
            + momentum * 0.15
            + trend * 0.10
        )
        return score, momentum, trend

    def should_exit_long(self, *, technical: float, sentiment: float, forecast: float, mimic: float,
                         decision: float = 0.0, volatility: float = 0.02, data_quality: float = 1.0,
                         prices: Optional[Sequence[float]] = None, volumes: Optional[Sequence[float]] = None):
        """Dedicated risk-reducing exit signal for an existing spot BUY position.

        This path cannot create a short position. It only authorizes closing an
        existing long when bearish evidence is decisive. Exit confirmation is
        intentionally less strict than a fresh entry-quality setup.
        """
        if data_quality < 0.70:
            return False, "exit blocked by degraded market data"
        prices = list(prices or [])
        volumes = list(volumes or [])
        technical = self._clamp(technical)
        sentiment = self._clamp(sentiment)
        forecast = self._clamp(forecast)
        mimic = self._clamp(mimic)
        decision = self._clamp(decision)
        score, momentum, trend = self._score_components(
            technical=technical, sentiment=sentiment, forecast=forecast,
            mimic=mimic, decision=decision, prices=prices,
        )
        volume = self._volume_confirmation(volumes)
        confirmations = sum([
            technical <= -0.20,
            forecast <= -0.15,
            mimic <= -0.20,
            decision <= -0.10,
            momentum <= -0.20,
            trend <= -0.15,
        ])
        if volume < -0.25 and (momentum < -0.20 or trend < -0.15):
            confirmations += 1
        required = self.exit_min_confirmations + (1 if volatility >= self.high_volatility else 0)
        if score <= -self.exit_score and confirmations >= required:
            return True, f"dedicated long exit: score={score:.3f}, confirmations={confirmations}/{required}"
        return False, f"no dedicated long exit: score={score:.3f}, confirmations={confirmations}/{required}"

    def evaluate(
        self,
        *,
        technical: float,
        sentiment: float,
        forecast: float,
        mimic: float,
        decision: float = 0.0,
        volatility: float = 0.02,
        data_quality: float = 1.0,
        prices: Optional[Sequence[float]] = None,
        volumes: Optional[Sequence[float]] = None,
    ) -> ScalpingSetup:
        prices = list(prices or [])
        volumes = list(volumes or [])
        technical = self._clamp(technical)
        sentiment = self._clamp(sentiment)
        forecast = self._clamp(forecast)
        mimic = self._clamp(mimic)
        decision = self._clamp(decision)
        quality = max(0.0, min(1.0, float(data_quality)))

        momentum = self._momentum_from_prices(prices)
        trend = self._trend_from_prices(prices)
        volume = self._volume_confirmation(volumes)
        score = (
            technical * 0.25
            + forecast * 0.15
            + mimic * 0.15
            + decision * 0.15
            + sentiment * 0.05
            + momentum * 0.15
            + trend * 0.10
        )

        direction = 1 if score > 0 else -1 if score < 0 else 0
        confirmations = 0
        if direction and technical * direction >= 0.20:
            confirmations += 1
        if direction and forecast * direction >= 0.15:
            confirmations += 1
        if direction and mimic * direction >= 0.20:
            confirmations += 1
        if direction and decision * direction >= 0.10:
            confirmations += 1
        if direction and momentum * direction >= 0.20:
            confirmations += 1
        if direction and trend * direction >= 0.15:
            confirmations += 1
        if direction and volume > 0.10:
            confirmations += 1

        regime = "SIDEWAYS"
        if abs(trend) >= 0.45 and abs(momentum) >= 0.25:
            regime = "TRENDING_UP" if direction > 0 else "TRENDING_DOWN"
        elif volatility >= self.high_volatility:
            regime = "HIGH_VOLATILITY"
        elif abs(momentum) >= 0.25:
            regime = "MOMENTUM"

        required_confirmations = self.min_confirmations + (1 if volatility >= self.high_volatility else 0)
        confidence = (
            0.35
            + abs(score) * 0.45
            + min(confirmations / 7.0, 1.0) * 0.20
        ) * quality
        if regime == "HIGH_VOLATILITY":
            confidence *= 0.92

        if (
            direction == 0
            or abs(score) < self.min_score
            or confidence < self.min_confidence
            or confirmations < required_confirmations
        ):
            return ScalpingSetup(
                "HOLD", "NO_SETUP", score, confidence, 0.0, 0.0, 0.0,
                f"no validated setup: score={score:.3f}, confirmations={confirmations}/{required_confirmations}",
                regime, confirmations,
            )

        action = "BUY" if direction > 0 else "SELL"
        setup = "MOMENTUM" if regime in {"MOMENTUM", "TRENDING_UP", "TRENDING_DOWN"} else "MEAN_REVERSION"
        if direction > 0 and trend < -0.20:
            setup = "REVERSAL"
        if direction < 0 and trend > 0.20:
            setup = "REVERSAL"

        vol = max(0.0025, min(0.04, abs(float(volatility))))
        stop = max(0.003, min(0.025, vol * 1.25))
        target = max(stop * 1.5, min(0.05, stop * 2.0))
        multiplier = min(self.max_position_multiplier, max(0.20, confidence))
        if regime == "HIGH_VOLATILITY":
            multiplier *= 0.60

        return ScalpingSetup(
            action,
            setup,
            score,
            confidence,
            multiplier,
            stop,
            target,
            f"validated {setup.lower()} setup with {confirmations} confirmations",
            regime,
            confirmations,
        )
