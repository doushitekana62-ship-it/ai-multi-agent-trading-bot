from dataclasses import dataclass

@dataclass(frozen=True)
class Forecast:
    symbol: str
    price: float
    suggested_tp: float
    suggested_sl: float
    confidence: float
    action: str
    indicators: dict

class ForecastAgent:
    """Market-only analysis. Never places orders."""
    def __init__(self, min_confidence: float = 0.62):
        self.min_confidence = min_confidence

    @staticmethod
    def _sma(values, n):
        n = min(n, len(values))
        return sum(values[-n:]) / n

    @staticmethod
    def _atr(values, n=14):
        changes = [abs(values[i] - values[i-1]) for i in range(1, len(values))]
        sample = changes[-n:]
        return sum(sample) / len(sample) if sample else 0.0

    @staticmethod
    def _rsi(values, n=14):
        changes = [values[i] - values[i-1] for i in range(1, len(values))][-n:]
        gains = sum(max(x, 0) for x in changes)
        losses = sum(max(-x, 0) for x in changes)
        if losses == 0:
            return 100.0 if gains else 50.0
        return 100 - (100 / (1 + gains / losses))

    def analyze(self, symbol: str, prices: list[float]) -> Forecast | None:
        if len(prices) < 5 or prices[-1] <= 0:
            return None
        price = prices[-1]
        fast, slow = self._sma(prices, 5), self._sma(prices, 20)
        atr, rsi = self._atr(prices), self._rsi(prices)
        trend = (fast - slow) / price
        momentum = (price - prices[-5]) / prices[-5]
        trend_score = min(1.0, max(0.0, 0.5 + trend * 80))
        momentum_score = min(1.0, max(0.0, 0.5 + momentum * 60))
        rsi_score = 1.0 if 45 <= rsi <= 68 else (0.7 if 35 <= rsi < 45 else 0.35)
        confidence = 0.45 * trend_score + 0.35 * momentum_score + 0.20 * rsi_score
        tp_pct = min(0.012, max(0.008, (atr / price) * 1.5 if atr else 0.008))
        sl_pct = min(0.008, max(0.005, (atr / price) if atr else 0.005))
        action = "buy" if confidence >= self.min_confidence and fast > slow and 40 <= rsi <= 70 else "hold"
        return Forecast(symbol, price, price * (1 + tp_pct), price * (1 - sl_pct), confidence, action,
                        {"sma_fast": fast, "sma_slow": slow, "atr": atr, "atr_percent": atr / price * 100,
                         "rsi": rsi, "momentum_percent": momentum * 100})
