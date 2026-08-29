"""Sentiment/context specialist.

This agent never invents news/social evidence and never acts as a trade veto.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

from core.signal_contract import SignalStatus, safe_float, utc_age_seconds


@dataclass
class SentimentResult:
    symbol: str
    timestamp: datetime
    overall_score: float
    sentiment_label: str
    confidence: float
    news_sentiment: float
    social_sentiment: float
    price_momentum: float
    fear_greed_index: float
    source_contributions: Dict[str, float]
    key_events: List[str]
    summary: str
    direction: str = "NEUTRAL"
    score: float = 0.0
    timeframe: str = "context"
    evidence: List[str] = field(default_factory=list)
    data_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    data_age_seconds: float = 0.0
    status: str = SignalStatus.OK.value
    limitations: List[str] = field(default_factory=list)


class SentimentAgent:
    """Advisory context. It may support a thesis but cannot veto it."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self.max_age_seconds = float(cfg.get("max_age_seconds", 300))
        self.max_contribution = float(cfg.get("max_contribution", 0.20))

    def analyze(self, symbol: str, market_data: Optional[Dict[str, Any]] = None) -> SentimentResult:
        data = market_data or {}; symbol = symbol.upper()
        timestamp = data.get("timestamp", datetime.now(timezone.utc)); age = utc_age_seconds(timestamp)
        fear_greed = data.get("fear_greed_index")
        news = data.get("news_sentiment")
        social = data.get("social_sentiment")
        evidence = []
        values = []

        # Only consume externally supplied context. Never replace unavailable news/social with 0 as evidence.
        if news is not None:
            n = float(np.clip(safe_float(news), -1, 1)); values.append(n * 0.55); evidence.append(f"news={n:+.2f}")
        if social is not None:
            s = float(np.clip(safe_float(social), -1, 1)); values.append(s * 0.35); evidence.append(f"social={s:+.2f}")
        fg_score = 0.0
        if fear_greed is not None:
            raw = safe_float(fear_greed)
            fg_score = (raw - 50) / 50 if 0 <= raw <= 100 else float(np.clip(raw, -1, 1))
            values.append(fg_score * 0.25); evidence.append(f"fear_greed={raw:.0f}")

        if age > self.max_age_seconds:
            return self._result(symbol, 0.0, 0.0, "STALE_CONTEXT", age, SignalStatus.DEGRADED.value, evidence)
        if not values:
            return self._result(symbol, 0.0, 0.0, "NO_EXTERNAL_SENTIMENT_DATA", age, SignalStatus.UNAVAILABLE.value, evidence)

        score = float(np.clip(sum(values), -self.max_contribution, self.max_contribution))
        direction = "BULLISH" if score >= 0.08 else "BEARISH" if score <= -0.08 else "NEUTRAL"
        confidence = float(np.clip(0.35 + 0.35 * min(abs(score) / self.max_contribution, 1) + 0.15 * min(len(values)/3, 1), 0.30, 0.70))
        return self._result(symbol, score, confidence, "OK", age, SignalStatus.OK.value, evidence, direction, fg_score)

    def _result(self, symbol, score, confidence, reason, age, status, evidence, direction=None, fg=0.0):
        direction = direction or ("BULLISH" if score > 0.08 else "BEARISH" if score < -0.08 else "NEUTRAL")
        label = direction
        return SentimentResult(
            symbol=symbol, timestamp=datetime.now(timezone.utc), overall_score=score,
            sentiment_label=label, confidence=confidence, news_sentiment=0.0,
            social_sentiment=0.0, price_momentum=0.0, fear_greed_index=fg,
            source_contributions={}, key_events=[],
            summary=f"Sentiment context {symbol}: {reason}; advisory only.", direction=direction,
            score=score, evidence=evidence + [reason], data_timestamp=datetime.now(timezone.utc),
            data_age_seconds=age, status=status,
            limitations=["No fabricated news/social signal", "Cannot veto technical or momentum evidence"],
        )
