from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ForecastSignal:
    action: str
    price: float
    suggested_tp: float
    suggested_sl: float
    confidence: float
    indicators: dict[str, float]


class ForecastAgent:
    """Legacy forecast layer: trend, momentum, volatility, volume and dynamic TP/SL."""

    @staticmethod
    def _rsi(close: pd.Series, period: int = 14) -> float:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(period).mean().iloc[-1]
        loss = (-delta.clip(upper=0)).rolling(period).mean().iloc[-1]
        if pd.isna(gain) or pd.isna(loss):
            return 50.0
        if loss == 0:
            return 100.0
        return float(100 - (100 / (1 + gain / loss)))

    @staticmethod
    def _atr(dataframe: pd.DataFrame, period: int = 14) -> float:
        high = dataframe["high"].astype(float)
        low = dataframe["low"].astype(float)
        close = dataframe["close"].astype(float)
        previous = close.shift(1)
        true_range = pd.concat(
            [(high - low), (high - previous).abs(), (low - previous).abs()], axis=1
        ).max(axis=1)
        value = true_range.rolling(period).mean().iloc[-1]
        return float(value) if pd.notna(value) else float((high.iloc[-1] - low.iloc[-1]))

    def analyze(self, dataframe: pd.DataFrame) -> ForecastSignal | None:
        if dataframe is None or len(dataframe) < 30:
            return None
        close = dataframe["close"].astype(float)
        price = float(close.iloc[-1])
        if price <= 0:
            return None

        ema9 = float(close.ewm(span=9, adjust=False).mean().iloc[-1])
        ema21 = float(close.ewm(span=21, adjust=False).mean().iloc[-1])
        ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
        rsi = self._rsi(close)
        atr = max(self._atr(dataframe), price * 0.001)
        atr_percent = atr / price * 100
        momentum_percent = float((price / close.iloc[-4] - 1) * 100) if close.iloc[-4] > 0 else 0.0

        volume = dataframe["volume"].astype(float)
        volume_mean = volume.rolling(20).mean().iloc[-1]
        volume_ratio = float(volume.iloc[-1] / volume_mean) if volume_mean and pd.notna(volume_mean) else 1.0

        trend_up = ema9 > ema21 > ema50
        momentum_ok = 52 <= rsi <= 68
        action = "buy" if trend_up and momentum_ok and momentum_percent >= 0 else "hold"

        tp_distance = min(max(atr * 1.8, price * 0.012), price * 0.025)
        sl_distance = min(max(atr * 1.0, price * 0.008), price * 0.012)
        confidence = 0.0
        confidence += 0.30 if trend_up else 0.0
        confidence += 0.20 if momentum_ok else 0.0
        confidence += 0.20 if momentum_percent > 0 else 0.0
        confidence += 0.15 if volume_ratio >= 1.0 else 0.0
        confidence += 0.15 if 0.1 <= atr_percent <= 1.5 else 0.0

        return ForecastSignal(
            action=action,
            price=price,
            suggested_tp=price + tp_distance,
            suggested_sl=price - sl_distance,
            confidence=round(confidence, 4),
            indicators={
                "ema9": ema9,
                "ema21": ema21,
                "ema50": ema50,
                "rsi": rsi,
                "atr": atr,
                "atr_percent": atr_percent,
                "momentum_percent": momentum_percent,
                "volume_ratio": volume_ratio,
            },
        )
