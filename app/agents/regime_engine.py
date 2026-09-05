from dataclasses import dataclass
from math import sqrt


@dataclass(frozen=True)
class MarketRegime:
    name: str
    ema20: float
    ema50: float
    ema200: float
    atr_percent: float
    realized_vol_percent: float
    trend_strength: float
    data_quality: float


class RegimeEngine:
    """Classifies market state from the price stream. It never places orders."""

    @staticmethod
    def _ema(values: list[float], period: int) -> float:
        if not values:
            return 0.0
        alpha = 2 / (period + 1)
        ema = values[0]
        for value in values[1:]:
            ema = alpha * value + (1 - alpha) * ema
        return ema

    @staticmethod
    def _atr(values: list[float], period: int = 14) -> float:
        changes = [abs(values[i] - values[i - 1]) for i in range(1, len(values))]
        sample = changes[-period:]
        return sum(sample) / len(sample) if sample else 0.0

    @staticmethod
    def _realized_vol(values: list[float], period: int = 30) -> float:
        returns = [(values[i] / values[i - 1]) - 1 for i in range(1, len(values)) if values[i - 1] > 0]
        returns = returns[-period:]
        if len(returns) < 2:
            return 0.0
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        return sqrt(variance)

    def classify(self, prices: list[float], data_age_seconds: float = 0.0) -> MarketRegime | None:
        if len(prices) < 30 or prices[-1] <= 0:
            return None
        price = prices[-1]
        ema20 = self._ema(prices, 20)
        ema50 = self._ema(prices, 50)
        ema200 = self._ema(prices, 200)
        atr = self._atr(prices)
        atr_pct = atr / price * 100 if price else 0.0
        rv_pct = self._realized_vol(prices) * 100
        trend_strength = min(1.0, abs(ema20 - ema50) / price * 200)
        quality = 1.0 if data_age_seconds <= 15 else max(0.0, 1 - (data_age_seconds - 15) / 60)

        if quality < 0.5:
            name = "DATA_UNSAFE"
        elif atr_pct >= 1.5 or rv_pct >= 1.0:
            name = "HIGH_VOLATILITY"
        elif ema20 > ema50 > ema200 and trend_strength >= 0.15:
            name = "TREND_UP"
        elif ema20 < ema50 < ema200 and trend_strength >= 0.15:
            name = "TREND_DOWN"
        else:
            name = "RANGE"
        return MarketRegime(name, ema20, ema50, ema200, atr_pct, rv_pct, trend_strength, quality)
