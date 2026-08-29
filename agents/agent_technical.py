"""Technical / market-structure specialist.

Owns OHLCV structure and indicators. It never emits an execution action.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

from core.signal_contract import SignalStatus, safe_float, utc_age_seconds


@dataclass
class TechnicalResult:
    symbol: str
    timestamp: datetime
    current_price: float
    overall_score: float
    confidence: float
    support_levels: List[float] = field(default_factory=list)
    resistance_levels: List[float] = field(default_factory=list)
    rsi: float = 50.0
    macd: Dict[str, float] = field(default_factory=dict)
    bollinger_bands: Dict[str, float] = field(default_factory=dict)
    moving_averages: Dict[str, float] = field(default_factory=dict)
    detected_patterns: List[Dict[str, Any]] = field(default_factory=list)
    pattern_score: float = 0.0
    volume_score: float = 0.0
    volume_trend: str = "NEUTRAL"
    trend: str = "NEUTRAL"
    summary: str = ""
    recommendations: List[str] = field(default_factory=list)
    direction: str = "NEUTRAL"
    score: float = 0.0
    timeframe: str = "1m"
    evidence: List[str] = field(default_factory=list)
    data_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    data_age_seconds: float = 0.0
    status: str = SignalStatus.OK.value
    limitations: List[str] = field(default_factory=list)


class TechnicalAgent:
    """Structure-first technical analyst for short-horizon trading."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self.rsi_period = int(cfg.get("rsi_period", 14))
        self.ma_periods = cfg.get("ma_periods", [10, 20, 50, 200])
        self.max_age_seconds = float(cfg.get("max_age_seconds", 90))

    def analyze(self, symbol: str, market_data: Optional[Dict[str, Any]] = None) -> TechnicalResult:
        data = market_data or {}
        symbol = symbol.upper()
        price = safe_float(data.get("unified_price", data.get("current_price")))
        candles = self._candles(data)
        closes = np.array([x["close"] for x in candles], dtype=float)
        highs = np.array([x["high"] for x in candles], dtype=float)
        lows = np.array([x["low"] for x in candles], dtype=float)
        volumes = np.array([x["volume"] for x in candles], dtype=float)
        timeframe = str(data.get("timeframe", "1m"))
        timestamp = data.get("timestamp", datetime.now(timezone.utc))
        age = utc_age_seconds(timestamp)

        if price <= 0 or len(closes) < 5:
            return self._unavailable(symbol, price, timeframe, "INSUFFICIENT_OHLCV")
        if age > self.max_age_seconds:
            return self._unavailable(symbol, price, timeframe, "STALE_MARKET_SNAPSHOT", age, SignalStatus.DEGRADED.value)

        rsi = self._rsi(closes)
        ma20 = float(np.mean(closes[-20:])) if len(closes) >= 20 else float(closes[-1])
        ma50 = float(np.mean(closes[-50:])) if len(closes) >= 50 else ma20
        ret1 = self._return(closes, 1)
        ret5 = self._return(closes, min(5, len(closes)-1))
        ret15 = self._return(closes, min(15, len(closes)-1))
        trend_score = float(np.clip(ret1 * 18 + ret5 * 7 + ret15 * 3, -1, 1))
        structure_score = self._structure_score(closes, highs, lows)
        volume_score, volume_trend = self._volume(volumes)

        # RSI is a context modifier, not a contrarian veto. In a trend, RSI > 50
        # confirms bullish momentum rather than automatically creating a sell signal.
        rsi_score = 0.0
        if rsi >= 55:
            rsi_score = min(0.35, (rsi - 50) / 50)
        elif rsi <= 45:
            rsi_score = max(-0.35, (rsi - 50) / 50)

        # Price above/below MA20 is structural context; distance is bounded.
        ma_score = float(np.clip((price / ma20 - 1.0) * 20.0, -0.5, 0.5)) if ma20 else 0.0
        score = float(np.clip(0.40 * trend_score + 0.25 * structure_score + 0.15 * rsi_score + 0.10 * ma_score + 0.10 * volume_score, -1, 1))
        direction = "BULLISH" if score >= 0.15 else "BEARISH" if score <= -0.15 else "NEUTRAL"
        confidence = float(np.clip(0.45 + 0.35 * abs(score) + 0.20 * min(len(closes) / 100, 1.0), 0.35, 0.90))

        supports, resistances = self._levels(closes, highs, lows)
        patterns = self._patterns(candles)
        evidence = [
            f"1m return={ret1:+.3%}", f"5m return={ret5:+.3%}", f"15m return={ret15:+.3%}",
            f"structure={structure_score:+.2f}", f"RSI={rsi:.1f}", f"volume={volume_trend}",
            f"price_vs_MA20={(price/ma20-1):+.2%}" if ma20 else "MA20 unavailable",
        ]
        return TechnicalResult(
            symbol=symbol, timestamp=datetime.now(timezone.utc), current_price=price,
            overall_score=score, confidence=confidence, support_levels=supports,
            resistance_levels=resistances, rsi=rsi,
            macd={"histogram": ret1 - self._return(closes, min(5, len(closes)-1))},
            bollinger_bands=self._bb(closes),
            moving_averages={"MA20": ma20, "MA50": ma50}, detected_patterns=patterns,
            pattern_score=structure_score, volume_score=volume_score, volume_trend=volume_trend,
            trend=direction, summary=f"Technical {symbol}: {direction} score={score:+.2f} confidence={confidence:.0%}",
            recommendations=["Structure and momentum are evidence; final action belongs to Trader."],
            direction=direction, score=score, timeframe=timeframe, evidence=evidence,
            data_timestamp=timestamp if isinstance(timestamp, datetime) else datetime.now(timezone.utc),
            data_age_seconds=age, status=SignalStatus.OK.value,
            limitations=["Technical analysis is advisory and does not approve execution."],
        )

    @staticmethod
    def _candles(data):
        raw = data.get("ohlcv", [])
        if not raw and data.get("_unified_snapshot") is not None:
            raw = getattr(data["_unified_snapshot"], "ohlcv_data", [])
        out = []
        for c in raw or []:
            try:
                get = c.get if isinstance(c, dict) else lambda k, d=0: getattr(c, k, d)
                o, h, l, cl = map(float, (get("open"), get("high"), get("low"), get("close")))
                v = safe_float(get("volume"))
                if h >= max(o, cl) and l <= min(o, cl) and cl > 0:
                    out.append({"open": o, "high": h, "low": l, "close": cl, "volume": v})
            except (TypeError, ValueError):
                continue
        return out

    @staticmethod
    def _return(prices, n):
        if n <= 0 or len(prices) <= n or prices[-n-1] <= 0:
            return 0.0
        return float(prices[-1] / prices[-n-1] - 1.0)

    def _rsi(self, prices):
        if len(prices) <= self.rsi_period:
            return 50.0
        changes = np.diff(prices[-self.rsi_period-1:])
        gains = changes[changes > 0].sum() / self.rsi_period
        losses = -changes[changes < 0].sum() / self.rsi_period
        if losses == 0:
            return 100.0 if gains > 0 else 50.0
        return float(100 - 100 / (1 + gains / losses))

    @staticmethod
    def _structure_score(closes, highs, lows):
        if len(closes) < 6:
            return 0.0
        recent_high = np.max(highs[-5:]); prior_high = np.max(highs[-10:-5])
        recent_low = np.min(lows[-5:]); prior_low = np.min(lows[-10:-5])
        higher_high = recent_high > prior_high
        higher_low = recent_low > prior_low
        lower_high = recent_high < prior_high
        lower_low = recent_low < prior_low
        if higher_high and higher_low:
            return 1.0
        if lower_high and lower_low:
            return -1.0
        return 0.25 if higher_high or higher_low else -0.25 if lower_high or lower_low else 0.0

    @staticmethod
    def _volume(volumes):
        if len(volumes) < 10:
            return 0.0, "UNAVAILABLE"
        old = float(np.mean(volumes[-10:-5])); new = float(np.mean(volumes[-5:]))
        if old <= 0:
            return 0.0, "NEUTRAL"
        ratio = new / old
        if ratio >= 1.5:
            return 0.30, "EXPANDING"
        if ratio <= 0.67:
            return -0.10, "CONTRACTING"
        return 0.0, "STABLE"

    @staticmethod
    def _levels(closes, highs, lows):
        support = [float(np.min(lows[-20:]))] if len(lows) >= 20 else [float(np.min(lows))]
        resistance = [float(np.max(highs[-20:]))] if len(highs) >= 20 else [float(np.max(highs))]
        return support, resistance

    @staticmethod
    def _bb(closes):
        n = min(20, len(closes)); recent = closes[-n:]; mid = float(np.mean(recent)); sd = float(np.std(recent))
        return {"upper": mid + 2*sd, "middle": mid, "lower": mid - 2*sd}

    @staticmethod
    def _patterns(candles):
        if len(candles) < 2:
            return []
        a, b = candles[-2], candles[-1]
        out = []
        if b["close"] > b["open"] and a["close"] < a["open"] and b["close"] >= a["open"] and b["open"] <= a["close"]:
            out.append({"name": "bullish_engulfing", "signal": "BULLISH", "confidence": 0.75})
        elif b["close"] < b["open"] and a["close"] > a["open"] and b["close"] <= a["open"] and b["open"] >= a["close"]:
            out.append({"name": "bearish_engulfing", "signal": "BEARISH", "confidence": 0.75})
        return out

    def _unavailable(self, symbol, price, timeframe, reason, age=0.0, status=SignalStatus.UNAVAILABLE.value):
        return TechnicalResult(symbol, datetime.now(timezone.utc), price, 0.0, 0.0,
            timeframe=timeframe, evidence=[reason], data_age_seconds=age, status=status,
            direction="NEUTRAL", score=0.0, summary=f"Technical unavailable: {reason}",
            limitations=[reason])
