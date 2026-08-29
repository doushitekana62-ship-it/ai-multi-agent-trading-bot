"""Advisory market-sentiment agent backed by the unified Indodax snapshot."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


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


class SentimentAgent:
    """Sentiment informs direction but cannot veto the other agents."""

    def __init__(self, config: Optional[Dict] = None):
        cfg = config or {}
        self.weights = {
            "news": 0.30,
            "social": 0.20,
            "price_momentum": 0.25,
            "fear_greed": 0.15,
            "volume": 0.10,
        }
        self.advisory_scale = float(cfg.get("advisory_scale", 0.55))
        self.directional_floor = float(cfg.get("directional_floor", 0.35))
        self.cache = {}
        logger.info("Sentiment Agent initialized in advisory mode")

    def analyze(self, symbol: str, market_data: Optional[Dict[str, Any]] = None) -> SentimentResult:
        symbol = symbol.upper()
        market_data = market_data or {}
        current_price = self._number(market_data.get("unified_price", market_data.get("current_price", 0)))
        ohlcv_data = market_data.get("ohlcv", [])
        if not ohlcv_data and market_data.get("_unified_snapshot") is not None:
            snapshot = market_data["_unified_snapshot"]
            ohlcv_data = [o.to_dict() if hasattr(o, "to_dict") else o for o in getattr(snapshot, "ohlcv_data", [])]
        volume_24h = market_data.get("volume_24h")
        if volume_24h is None and market_data.get("_unified_snapshot") is not None:
            volume_24h = getattr(market_data["_unified_snapshot"], "volume_24h", None)
        fear_greed = market_data.get("fear_greed_index")
        if fear_greed is None and market_data.get("_unified_snapshot") is not None:
            fear_greed = getattr(market_data["_unified_snapshot"], "fear_greed_index", None)
        try:
            price_momentum = self._analyze_momentum_from_ohlcv(ohlcv_data, current_price)
            fear_greed_score = self._normalize_fear_greed(fear_greed)
            volume_sentiment = self._analyze_volume_from_data(ohlcv_data, volume_24h)
            sources = {
                "news": 0.0,
                "social": 0.0,
                "price_momentum": price_momentum,
                "fear_greed": fear_greed_score,
                "volume": volume_sentiment,
            }
            raw_score = self._combine_sentiments(sources)
            # Neutral sentiment is explicitly non-directional. Strong sentiment
            # is retained but scaled so it cannot dominate technical/forecast agents.
            overall_score = raw_score * self.advisory_scale if abs(raw_score) >= self.directional_floor else 0.0
            label = self._get_sentiment_label(overall_score)
            confidence = self._calculate_confidence(sources)
            contributions = {key: value * self.weights.get(key, 0.0) for key, value in sources.items()}
            return SentimentResult(
                symbol=symbol,
                timestamp=datetime.utcnow(),
                overall_score=float(np.clip(overall_score, -1.0, 1.0)),
                sentiment_label=label,
                confidence=confidence,
                news_sentiment=sources["news"],
                social_sentiment=sources["social"],
                price_momentum=price_momentum,
                fear_greed_index=fear_greed_score,
                source_contributions=contributions,
                key_events=[],
                summary=self._generate_summary(symbol, overall_score, label, []),
            )
        except Exception:
            logger.exception("Sentiment analysis failed for %s", symbol)
            return self._get_default_sentiment(symbol)

    @staticmethod
    def _number(value, default=0.0):
        try:
            number = float(value)
            return number if np.isfinite(number) else default
        except (TypeError, ValueError):
            return default

    def _analyze_momentum_from_ohlcv(self, ohlcv_data: List[Dict], current_price: float) -> float:
        closes = []
        for candle in ohlcv_data or []:
            try:
                closes.append(float(candle.get("close", 0) if isinstance(candle, dict) else candle.close))
            except (TypeError, ValueError, AttributeError):
                continue
        if len(closes) < 2:
            return 0.0
        prices = np.asarray(closes, dtype=float)
        short = self._calculate_momentum(prices, min(6, len(prices) - 1))
        medium = self._calculate_momentum(prices, min(24, len(prices) - 1))
        long = self._calculate_momentum(prices, min(72, len(prices) - 1))
        return float(np.clip(short * 0.50 + medium * 0.30 + long * 0.20, -1.0, 1.0))

    def _analyze_volume_from_data(self, ohlcv_data: List[Dict], volume_24h: Optional[float]) -> float:
        if volume_24h is not None and volume_24h > 0:
            return float(np.clip(volume_24h / 10_000_000, 0.0, 0.3))
        volumes = []
        for candle in ohlcv_data or []:
            try:
                volumes.append(float(candle.get("volume", 0) if isinstance(candle, dict) else candle.volume))
            except (TypeError, ValueError, AttributeError):
                continue
        if len(volumes) < 2:
            return 0.0
        recent = sum(volumes[-5:]) / min(5, len(volumes))
        older_slice = volumes[-10:-5]
        older = sum(older_slice) / len(older_slice) if older_slice else recent
        if older <= 0:
            return 0.0
        ratio = recent / older
        if ratio > 1.5:
            return 0.5
        if ratio < 0.5:
            return -0.3
        return 0.0

    def _normalize_fear_greed(self, value: Optional[float]) -> float:
        if value is None:
            return 0.0
        try:
            value = float(value)
        except (TypeError, ValueError):
            return 0.0
        return float(np.clip((value - 50.0) / 50.0, -1.0, 1.0)) if 0 <= value <= 100 else float(np.clip(value, -1.0, 1.0))

    def _calculate_momentum(self, prices: np.ndarray, window: int) -> float:
        if window <= 0 or len(prices) <= window:
            return 0.0
        past = float(prices[-window - 1])
        if past <= 0:
            return 0.0
        return float(np.clip(((float(prices[-1]) - past) / past) * 20.0, -1.0, 1.0))

    def _combine_sentiments(self, sentiments: Dict[str, float]) -> float:
        total = 0.0
        weight = 0.0
        for source, score in sentiments.items():
            w = self.weights.get(source, 0.0)
            if w <= 0:
                continue
            total += float(np.clip(score, -1.0, 1.0)) * w
            weight += w
        return float(np.clip(total / weight, -1.0, 1.0)) if weight else 0.0

    def _get_sentiment_label(self, score: float) -> str:
        if score >= 0.3:
            return "BULLISH"
        if score <= -0.3:
            return "BEARISH"
        return "NEUTRAL"

    def _calculate_confidence(self, sentiments: Dict[str, float]) -> float:
        scores = [self._number(value) for value in sentiments.values()]
        if not scores:
            return 0.5
        std_dev = float(np.std(scores)); avg = float(np.mean(scores))
        confidence = 0.9 if std_dev < 0.2 else 0.7 if std_dev < 0.4 else 0.5 if std_dev < 0.6 else 0.3
        return float(np.clip(confidence * (0.5 + abs(avg) * 0.5), 0.0, 1.0))

    def _generate_summary(self, symbol: str, score: float, label: str, events: List[str]) -> str:
        desc = "positif" if label == "BULLISH" else "negatif" if label == "BEARISH" else "netral"
        summary = f"Sentiment advisory untuk {symbol} menunjukkan sentimen {desc} (score: {score:.2f}). Sentiment tidak menjadi veto terhadap agent lain."
        if events:
            summary += f" Event penting: {', '.join(events[:3])}."
        return summary

    def _get_default_sentiment(self, symbol: str) -> SentimentResult:
        return SentimentResult(symbol, datetime.utcnow(), 0.0, "NEUTRAL", 0.3, 0.0, 0.0, 0.0, 0.0, {}, [], f"Sentiment advisory unavailable for {symbol}; neutral.")
