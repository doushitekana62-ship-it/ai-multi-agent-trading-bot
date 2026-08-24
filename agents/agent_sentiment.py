"""
Agent 1: Analisis Sentimen Pasar
Dengan dukungan Unified Market Data
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

import numpy as np
from textblob import TextBlob

logger = logging.getLogger(__name__)


@dataclass
class SentimentResult:
    """Data class untuk hasil analisis sentimen."""
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
    """
    Agent Sentimen Pasar dengan Unified Market Data.
    
    SEKARANG: Menggunakan data dari UnifiedMarketSnapshot,
    bukan fetching data sendiri.
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        
        # Weights - Total = 1.00
        self.weights = {
            "news": 0.30,
            "social": 0.20,
            "price_momentum": 0.25,
            "fear_greed": 0.15,
            "volume": 0.10,
        }
        
        # Keywords
        self.positive_keywords = [
            "bullish", "rally", "surge", "gain", "profit", "positive",
            "growth", "breakthrough", "success", "adoption", "innovation",
            "upgrade", "upbeat", "optimistic", "outperform", "beat"
        ]
        
        self.negative_keywords = [
            "bearish", "crash", "drop", "loss", "negative", "decline",
            "regulatory", "ban", "restriction", "delay", "failure",
            "bear", "slump", "plunge", "concern", "risk", "warning"
        ]
        
        # Cache
        self.cache = {}
        self.cache_duration = timedelta(minutes=5)
        
        logger.info("Sentiment Agent initialized with Unified Market Data support")

    def analyze(
        self,
        symbol: str,
        market_data: Optional[Dict[str, Any]] = None
    ) -> SentimentResult:
        """
        Analisis sentimen menggunakan Unified Market Data.
        
        Args:
            symbol: Simbol aset (BTC-USD, ETH-USD, dll)
            market_data: Data dari UnifiedMarketSnapshot
        """
        logger.info(f"Analyzing sentiment for {symbol}")
        
        symbol = symbol.upper()
        market_data = market_data or {}
        
        # ============================================================
        # FIX 1: GUNAKAN UNIFIED DATA
        # ============================================================
        
        # Extract unified price
        current_price = market_data.get("unified_price")
        if current_price is None:
            current_price = market_data.get("current_price", 0)
        
        try:
            current_price = float(current_price)
        except (TypeError, ValueError):
            current_price = 0
        
        # Extract OHLCV dari snapshot
        ohlcv_data = market_data.get("ohlcv", [])
        if not ohlcv_data and "_unified_snapshot" in market_data:
            snapshot = market_data["_unified_snapshot"]
            if hasattr(snapshot, "ohlcv_data"):
                ohlcv_data = [o.to_dict() if hasattr(o, "to_dict") else o for o in snapshot.ohlcv_data]
        
        # Extract volume dari snapshot
        volume_24h = market_data.get("volume_24h")
        if volume_24h is None and "_unified_snapshot" in market_data:
            snapshot = market_data["_unified_snapshot"]
            if hasattr(snapshot, "volume_24h"):
                volume_24h = snapshot.volume_24h
        
        # Extract Fear & Greed dari snapshot
        fear_greed = market_data.get("fear_greed_index")
        if fear_greed is None and "_unified_snapshot" in market_data:
            snapshot = market_data["_unified_snapshot"]
            if hasattr(snapshot, "fear_greed_index"):
                fear_greed = snapshot.fear_greed_index
        
        # Extract timeframe
        timeframe = market_data.get("timeframe", "1h")
        
        # ============================================================
        # ANALISIS BERDASARKAN UNIFIED DATA
        # ============================================================
        
        try:
            # 1. Price Momentum dari unified data
            price_momentum = self._analyze_momentum_from_ohlcv(ohlcv_data, current_price)
            
            # 2. Fear & Greed dari snapshot (atau default)
            fear_greed_score = self._normalize_fear_greed(fear_greed)
            
            # 3. Volume dari snapshot
            volume_sentiment = self._analyze_volume_from_data(ohlcv_data, volume_24h)
            
            # 4. News Sentiment (masih placeholder, tapi bisa dikembangkan)
            news_sentiment = self._analyze_news(symbol)
            
            # 5. Social Sentiment (placeholder)
            social_sentiment = self._analyze_social_media(symbol)
            
            # ============================================================
            # KOMBINASI
            # ============================================================
            
            sentiment_sources = {
                "news": news_sentiment,
                "social": social_sentiment,
                "price_momentum": price_momentum,
                "fear_greed": fear_greed_score,
                "volume": volume_sentiment,
            }
            
            overall_score = self._combine_sentiments(sentiment_sources)
            sentiment_label = self._get_sentiment_label(overall_score)
            confidence = self._calculate_confidence(sentiment_sources)
            
            source_contributions = {
                source: score * self.weights.get(source, 0.0)
                for source, score in sentiment_sources.items()
            }
            
            summary = self._generate_summary(
                symbol, overall_score, sentiment_label, []
            )
            
            return SentimentResult(
                symbol=symbol,
                timestamp=datetime.now(),
                overall_score=overall_score,
                sentiment_label=sentiment_label,
                confidence=confidence,
                news_sentiment=news_sentiment,
                social_sentiment=social_sentiment,
                price_momentum=price_momentum,
                fear_greed_index=fear_greed_score,
                source_contributions=source_contributions,
                key_events=[],
                summary=summary
            )
            
        except Exception as e:
            logger.exception(f"Error analyzing sentiment for {symbol}: {e}")
            return self._get_default_sentiment(symbol)

    # ============================================================
    # ANALISIS DARI UNIFIED DATA
    # ============================================================
    
    def _analyze_momentum_from_ohlcv(
        self,
        ohlcv_data: List[Dict],
        current_price: float
    ) -> float:
        """Analisis momentum dari OHLCV data."""
        if not ohlcv_data or len(ohlcv_data) < 2:
            return 0.0
        
        # Extract closing prices
        closes = []
        for candle in ohlcv_data:
            try:
                if isinstance(candle, dict):
                    closes.append(float(candle.get("close", 0)))
                elif hasattr(candle, "close"):
                    closes.append(float(candle.close))
            except (TypeError, ValueError):
                continue
        
        if len(closes) < 2:
            return 0.0
        
        closes = np.asarray(closes)
        
        # Short term (6 periods)
        short_term = self._calculate_momentum(closes, window=6)
        
        # Medium term (24 periods)
        medium_term = self._calculate_momentum(closes, window=24)
        
        # Long term (72 periods)
        long_term = self._calculate_momentum(closes, window=min(72, len(closes)))
        
        # Weighted
        momentum = short_term * 0.50 + medium_term * 0.30 + long_term * 0.20
        
        return float(np.clip(momentum, -1.0, 1.0))
    
    def _analyze_volume_from_data(
        self,
        ohlcv_data: List[Dict],
        volume_24h: Optional[float]
    ) -> float:
        """Analisis volume dari data."""
        if volume_24h is not None and volume_24h > 0:
            # Jika ada volume 24h, gunakan
            return min(0.3, volume_24h / 10000000)  # Normalize
        
        if not ohlcv_data:
            return 0.0
        
        # Extract volumes
        volumes = []
        for candle in ohlcv_data:
            try:
                if isinstance(candle, dict):
                    volumes.append(float(candle.get("volume", 0)))
                elif hasattr(candle, "volume"):
                    volumes.append(float(candle.volume))
            except (TypeError, ValueError):
                continue
        
        if len(volumes) < 2:
            return 0.0
        
        recent_avg = sum(volumes[-5:]) / 5 if len(volumes) >= 5 else sum(volumes) / len(volumes)
        older_avg = sum(volumes[-10:-5]) / 5 if len(volumes) >= 10 else recent_avg
        
        if older_avg == 0:
            return 0.0
        
        ratio = recent_avg / older_avg
        
        if ratio > 1.5:
            return 0.5
        elif ratio < 0.5:
            return -0.3
        else:
            return 0.0
    
    def _normalize_fear_greed(self, value: Optional[float]) -> float:
        """Normalize Fear & Greed ke range -1 sampai 1."""
        if value is None:
            return 0.0
        
        try:
            value = float(value)
        except (TypeError, ValueError):
            return 0.0
        
        # Fear & Greed biasanya 0-100, map ke -1 sampai 1
        if 0 <= value <= 100:
            return (value - 50) / 50
        else:
            return np.clip(value, -1.0, 1.0)

    # ============================================================
    # HELPER METHODS
    # ============================================================
    
    def _calculate_momentum(self, prices: np.ndarray, window: int) -> float:
        """Calculate momentum."""
        if len(prices) < window + 1:
            return 0.0
        
        current = prices[-1]
        past = prices[-window - 1] if len(prices) > window else prices[0]
        
        if past == 0:
            return 0.0
        
        change_pct = (current - past) / past
        return np.clip(change_pct * 20, -1.0, 1.0)
    
    def _combine_sentiments(self, sentiments: Dict[str, float]) -> float:
        """Combine all sources with weights."""
        total_score = 0.0
        total_weight = 0.0
        
        for source, score in sentiments.items():
            weight = self.weights.get(source, 0.0)
            if weight <= 0:
                continue
            try:
                score = float(np.clip(score, -1.0, 1.0))
            except (ValueError, TypeError):
                score = 0.0
            total_score += score * weight
            total_weight += weight
        
        if total_weight <= 0:
            return 0.0
        
        return float(np.clip(total_score / total_weight, -1.0, 1.0))
    
    def _get_sentiment_label(self, score: float) -> str:
        """Convert score to label."""
        if score >= 0.3:
            return "BULLISH"
        elif score <= -0.3:
            return "BEARISH"
        return "NEUTRAL"
    
    def _calculate_confidence(self, sentiments: Dict[str, float]) -> float:
        """Calculate confidence based on consistency."""
        scores = []
        for value in sentiments.values():
            try:
                scores.append(float(value))
            except (ValueError, TypeError):
                scores.append(0.0)
        
        if not scores:
            return 0.5
        
        std_dev = np.std(scores)
        avg_score = np.mean(scores)
        
        if std_dev < 0.2:
            confidence = 0.9
        elif std_dev < 0.4:
            confidence = 0.7
        elif std_dev < 0.6:
            confidence = 0.5
        else:
            confidence = 0.3
        
        confidence *= (0.5 + abs(avg_score) * 0.5)
        return float(np.clip(confidence, 0.0, 1.0))
    
    def _analyze_news(self, symbol: str) -> float:
        """Analyze news sentiment (placeholder)."""
        # TODO: Integrate with real news API
        return 0.0
    
    def _analyze_social_media(self, symbol: str) -> float:
        """Analyze social media sentiment (placeholder)."""
        # TODO: Integrate with real social media API
        return 0.0
    
    def _generate_summary(self, symbol: str, score: float, label: str, events: List[str]) -> str:
        """Generate summary."""
        symbol_name = symbol.replace("-USD", "").replace("-USDT", "")
        
        if label == "BULLISH":
            desc = "positif"
            action = "bullish sentiment dengan potensi kenaikan"
        elif label == "BEARISH":
            desc = "negatif"
            action = "bearish sentiment dengan potensi penurunan"
        else:
            desc = "netral"
            action = "netral, perlu konfirmasi lebih lanjut"
        
        summary = f"Analisis sentimen untuk {symbol_name} menunjukkan sentimen {desc} (score: {score:.2f}). Indikator pasar menunjukkan {action}."
        
        if events:
            summary += f" Event penting: {', '.join(events[:3])}."
        
        return summary
    
    def _get_default_sentiment(self, symbol: str) -> SentimentResult:
        """Default neutral result."""
        return SentimentResult(
            symbol=symbol,
            timestamp=datetime.now(),
            overall_score=0.0,
            sentiment_label="NEUTRAL",
            confidence=0.3,
            news_sentiment=0.0,
            social_sentiment=0.0,
            price_momentum=0.0,
            fear_greed_index=0.0,
            source_contributions={},
            key_events=[],
            summary=f"Unable to analyze sentiment for {symbol}. Default to neutral."
        )
