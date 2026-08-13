"""
Agent 1: Analisis Sentimen Pasar
Bertugas menganalisis sentimen dari berita, media sosial, dan data pasar
untuk menentukan apakah pasar sedang bullish, bearish, atau netral.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import re
from dataclasses import dataclass, asdict

# Import untuk API dan data
import requests
from textblob import TextBlob
import yfinance as yf
import pandas as pd
import numpy as np

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class SentimentResult:
    """Data class untuk hasil analisis sentimen"""
    symbol: str
    timestamp: datetime
    overall_score: float  # -1 (very bearish) to +1 (very bullish)
    sentiment_label: str  # "BULLISH", "BEARISH", or "NEUTRAL"
    confidence: float  # 0 to 1
    news_sentiment: float
    social_sentiment: float
    price_momentum: float
    fear_greed_index: float
    source_contributions: Dict[str, float]
    key_events: List[str]
    summary: str

class SentimentAgent:
    """
    Agent Sentimen Pasar dengan kemampuan multi-source analysis
    """
    
    def __init__(self, config: Dict = None):
        """
        Initialize Sentiment Agent
        
        Args:
            config: Konfigurasi untuk agent (API keys, thresholds, dll)
        """
        self.config = config or {}
        
        # API Keys dari environment
        self.news_api_key = os.getenv('NEWS_API_KEY', 'demo')
        self.twitter_api_key = os.getenv('TWITTER_API_KEY', '')
        self.reddit_client_id = os.getenv('REDDIT_CLIENT_ID', '')
        self.reddit_client_secret = os.getenv('REDDIT_CLIENT_SECRET', '')
        
        # Threshold dan weights
        self.weights = {
            'news': 0.30,
            'social': 0.20,
            'price_momentum': 0.25,
            'fear_greed': 0.15,
            'volume': 0.10
        }
        
        # Cache untuk mengurangi API calls
        self.cache = {}
        self.cache_duration = timedelta(minutes=5)
        
        # Daftar negative/positive keywords
        self.positive_keywords = [
            'bullish', 'rally', 'surge', 'gain', 'profit', 'positive', 
            'growth', 'breakthrough', 'success', 'adoption', 'innovation',
            'upgrade', 'upbeat', 'optimistic', 'outperform', 'beat'
        ]
        self.negative_keywords = [
            'bearish', 'crash', 'drop', 'loss', 'negative', 'decline',
            'regulatory', 'ban', 'restriction', 'delay', 'failure',
            'bear', 'slump', 'plunge', 'concern', 'risk', 'warning'
        ]
        
        logger.info("Sentiment Agent initialized successfully")
    
    def analyze(self, symbol: str, market_data: Dict = None) -> SentimentResult:
        """
        Main method untuk melakukan analisis sentimen
        
        Args:
            symbol: Simbol aset (e.g., 'AAPL', 'BTC-USD')
            market_data: Data pasar opsional untuk memperkaya analisis
        
        Returns:
            SentimentResult: Hasil analisis sentimen lengkap
        """
        logger.info(f"Analyzing sentiment for {symbol}")
        
        # Check cache
        cache_key = f"sentiment_{symbol}"
        if cache_key in self.cache:
            cached_result, cache_time = self.cache[cache_key]
            if datetime.now() - cache_time < self.cache_duration:
                logger.info(f"Using cached sentiment for {symbol}")
                return cached_result
        
        # Collect data dari berbagai sumber
        try:
            # 1. News Analysis
            news_sentiment = self._analyze_news(symbol)
            
            # 2. Social Media Analysis
            social_sentiment = self._analyze_social_media(symbol)
            
            # 3. Price Momentum
            price_momentum = self._analyze_price_momentum(symbol, market_data)
            
            # 4. Fear & Greed Index
            fear_greed = self._get_fear_greed_index()
            
            # 5. Volume Analysis
            volume_sentiment = self._analyze_volume(symbol, market_data)
            
            # Combine semua sources
            overall_score = self._combine_sentiments({
                'news': news_sentiment,
                'social': social_sentiment,
                'price_momentum': price_momentum,
                'fear_greed': fear_greed,
                'volume': volume_sentiment
            })
            
            # Generate label dan confidence
            sentiment_label = self._get_sentiment_label(overall_score)
            confidence = self._calculate_confidence({
                'news': news_sentiment,
                'social': social_sentiment,
                'price_momentum': price_momentum,
                'fear_greed': fear_greed,
                'volume': volume_sentiment
            })
            
            # Identifikasi key events
            key_events = self._extract_key_events(symbol)
            
            # Buat summary
            summary = self._generate_summary(symbol, overall_score, sentiment_label, key_events)
            
            # Buat result object
            result = SentimentResult(
                symbol=symbol,
                timestamp=datetime.now(),
                overall_score=overall_score,
                sentiment_label=sentiment_label,
                confidence=confidence,
                news_sentiment=news_sentiment,
                social_sentiment=social_sentiment,
                price_momentum=price_momentum,
                fear_greed_index=fear_greed,
                source_contributions={
                    'news': news_sentiment * self.weights['news'],
                    'social': social_sentiment * self.weights['social'],
                    'price_momentum': price_momentum * self.weights['price_momentum'],
                    'fear_greed': fear_greed * self.weights['fear_greed'],
                    'volume': volume_sentiment * self.weights['volume']
                },
                key_events=key_events,
                summary=summary
            )
            
            # Simpan di cache
            self.cache[cache_key] = (result, datetime.now())
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing sentiment for {symbol}: {str(e)}")
            # Return default neutral sentiment
            return self._get_default_sentiment(symbol)
    
    def _analyze_news(self, symbol: str) -> float:
        """
        Analisis sentimen dari berita menggunakan News API
        
        Returns:
            float: Sentiment score antara -1 sampai 1
        """
        try:
            # Simulasi fetching news - Implementasi real dengan NewsAPI
            headlines = self._fetch_news_headlines(symbol)
            
            if not headlines:
                return 0.0
            
            sentiments = []
            for headline in headlines[:10]:  # Ambil 10 berita teratas
                # Gunakan TextBlob untuk sentiment analysis
                blob = TextBlob(headline)
                # TextBlob polarity: -1 to 1
                polarity = blob.sentiment.polarity
                
                # Adjust berdasarkan keyword matching
                headline_lower = headline.lower()
                if any(word in headline_lower for word in self.positive_keywords):
                    polarity = min(1.0, polarity + 0.3)
                elif any(word in headline_lower for word in self.negative_keywords):
                    polarity = max(-1.0, polarity - 0.3)
                
                sentiments.append(polarity)
            
            if sentiments:
                avg_sentiment = np.mean(sentiments)
                return np.clip(avg_sentiment, -1.0, 1.0)
            return 0.0
            
        except Exception as e:
            logger.error(f"Error analyzing news for {symbol}: {e}")
            return 0.0
    
    def _analyze_social_media(self, symbol: str) -> float:
        """
        Analisis sentimen dari media sosial (Twitter, Reddit)
        
        Returns:
            float: Sentiment score antara -1 sampai 1
        """
        try:
            # Simulasi - Implementasi real dengan Twitter API atau Reddit API
            # Disini kita menggunakan pendekatan sederhana
            social_posts = self._fetch_social_posts(symbol)
            
            if not social_posts:
                return 0.0
            
            sentiments = []
            for post in social_posts[:20]:  # Ambil 20 post teratas
                blob = TextBlob(post)
                polarity = blob.sentiment.polarity
                
                # Adjust untuk crypto-specific terms
                post_lower = post.lower()
                if 'moon' in post_lower or 'to the moon' in post_lower:
                    polarity += 0.5
                elif 'dump' in post_lower or 'dead' in post_lower:
                    polarity -= 0.5
                
                sentiments.append(np.clip(polarity, -1.0, 1.0))
            
            if sentiments:
                avg_sentiment = np.mean(sentiments)
                return np.clip(avg_sentiment, -1.0, 1.0)
            return 0.0
            
        except Exception as e:
            logger.error(f"Error analyzing social media for {symbol}: {e}")
            return 0.0
    
    def _analyze_price_momentum(self, symbol: str, market_data: Dict = None) -> float:
        """
        Analisis momentum harga dari data pasar
        
        Returns:
            float: Momentum score antara -1 sampai 1
        """
        try:
            if market_data and 'prices' in market_data:
                prices = market_data['prices']
            else:
                # Fetch data dari Yahoo Finance
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period='5d', interval='1h')
                prices = hist['Close'].values
            
            if len(prices) < 2:
                return 0.0
            
            # Hitung momentum menggunakan berbagai timeframes
            # 1. Short-term (1 jam)
            short_term = self._calculate_momentum(prices, window=6)  # 6 jam
            
            # 2. Medium-term (24 jam)
            medium_term = self._calculate_momentum(prices, window=24)
            
            # 3. Long-term (72 jam)
            long_term = self._calculate_momentum(prices, window=72)
            
            # Weighted average
            momentum = (short_term * 0.5 + medium_term * 0.3 + long_term * 0.2)
            
            # Map ke range -1 sampai 1
            momentum_score = np.clip(momentum, -1.0, 1.0)
            
            # Additional signal dari RSI
            rsi = self._calculate_rsi(prices)
            if rsi > 70:  # Overbought
                momentum_score = min(0.3, momentum_score)  # Reduce positive momentum
            elif rsi < 30:  # Oversold
                momentum_score = max(-0.3, momentum_score)  # Reduce negative momentum
            
            return momentum_score
            
        except Exception as e:
            logger.error(f"Error analyzing price momentum for {symbol}: {e}")
            return 0.0
    
    def _get_fear_greed_index(self) -> float:
        """
        Mendapatkan Fear & Greed Index dari pasar kripto
        
        Returns:
            float: Score antara -1 (extreme fear) sampai 1 (extreme greed)
        """
        try:
            # Simulasi - Biasanya mengambil dari API CNN Fear & Greed
            # Dalam implementasi real, fetch dari: https://fear-and-greed-index.p.rapidapi.com/v1/fgi
            
            # Simulasi dengan random (nanti diganti dengan API real)
            import random
            fg_value = random.uniform(-1, 1)
            
            return fg_value
            
        except Exception as e:
            logger.error(f"Error fetching Fear & Greed index: {e}")
            return 0.0
    
    def _analyze_volume(self, symbol: str, market_data: Dict = None) -> float:
        """
        Analisis volume trading untuk konfirmasi sentimen
        
        Returns:
            float: Volume sentiment antara -1 sampai 1
        """
        try:
            if market_data and 'volume' in market_data:
                volume = market_data['volume']
            else:
                # Fetch dari Yahoo Finance
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period='5d')
                volume = hist['Volume'].values
            
            if len(volume) < 2:
                return 0.0
            
            # Bandingkan volume hari ini dengan rata-rata
            avg_volume = np.mean(volume[:-1])  # Rata-rata hari sebelumnya
            current_volume = volume[-1]
            
            if avg_volume == 0:
                return 0.0
            
            # Jika volume naik signifikan, mengkonfirmasi sentimen
            volume_ratio = current_volume / avg_volume
            
            # Sentimen positif jika volume tinggi (bullish)
            # Sentimen negatif jika volume rendah (bearish)
            if volume_ratio > 1.5:
                return 0.5
            elif volume_ratio < 0.5:
                return -0.3
            else:
                return 0.0
            
        except Exception as e:
            logger.error(f"Error analyzing volume for {symbol}: {e}")
            return 0.0
    
    def _combine_sentiments(self, sentiments: Dict[str, float]) -> float:
        """
        Menggabungkan semua sentimen dengan bobot masing-masing
        
        Returns:
            float: Combined sentiment score (-1 to 1)
        """
        total_score = 0.0
        total_weight = 0.0
        
        for source, score in sentiments.items():
            weight = self.weights.get(source, 0.1)
            total_score += score * weight
            total_weight += weight
        
        if total_weight > 0:
            return np.clip(total_score / total_weight, -1.0, 1.0)
        return 0.0
    
    def _get_sentiment_label(self, score: float) -> str:
        """Konversi score ke label sentimen"""
        if score >= 0.3:
            return "BULLISH"
        elif score <= -0.3:
            return "BEARISH"
        else:
            return "NEUTRAL"
    
    def _calculate_confidence(self, sentiments: Dict[str, float]) -> float:
        """
        Menghitung confidence berdasarkan konsistensi sumber
        
        Returns:
            float: Confidence score (0-1)
        """
        scores = list(sentiments.values())
        if not scores:
            return 0.5
        
        # Semakin konsisten, semakin tinggi confidence
        std_dev = np.std(scores)
        avg_score = np.mean(scores)
        
        # Normalisasi confidence
        if std_dev < 0.2:
            confidence = 0.9  # Sangat konsisten
        elif std_dev < 0.4:
            confidence = 0.7
        elif std_dev < 0.6:
            confidence = 0.5
        else:
            confidence = 0.3
        
        # Adjust dengan absolut score
        confidence *= (0.5 + abs(avg_score) * 0.5)
        
        return np.clip(confidence, 0.0, 1.0)
    
    def _calculate_momentum(self, prices: np.ndarray, window: int) -> float:
        """Hitung momentum dengan moving average"""
        if len(prices) < window + 1:
            return 0.0
        
        current_price = prices[-1]
        past_price = prices[-window-1]
        
        if past_price == 0:
            return 0.0
        
        # Persentase perubahan
        change_pct = (current_price - past_price) / past_price
        
        # Map ke -1 sampai 1
        # Asumsi: ±5% change = ±1 sentiment
        momentum = np.clip(change_pct * 20, -1.0, 1.0)
        
        return momentum
    
    def _calculate_rsi(self, prices: np.ndarray, period: int = 14) -> float:
        """Hitung RSI (Relative Strength Index)"""
        if len(prices) < period + 1:
            return 50.0
        
        deltas = np.diff(prices)
        seed = deltas[:period+1]
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period
        rs = up / down if down != 0 else 100
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _fetch_news_headlines(self, symbol: str) -> List[str]:
        """
        Fetch berita terbaru untuk simbol tertentu
        
        Dalam implementasi real, gunakan NewsAPI
        """
        # Simulasi - Return sample headlines
        symbol_name = symbol.replace('-USD', '').replace('-USDT', '')
        sample_headlines = [
            f"{symbol_name} shows strong growth potential",
            f"Analysts positive on {symbol_name} outlook",
            f"{symbol_name} faces regulatory challenges",
            f"New partnership announced for {symbol_name}",
            f"Market reacts to {symbol_name} earnings report",
            f"{symbol_name} adoption increases globally",
            f"Technical analysis suggests {symbol_name} breakout",
            f"Institutional interest in {symbol_name} rising",
            f"{symbol_name} ecosystem expands",
            f"Community sentiment on {symbol_name} remains bullish"
        ]
        return sample_headlines[:10]
    
    def _fetch_social_posts(self, symbol: str) -> List[str]:
        """Fetch social media posts tentang simbol tertentu"""
        # Simulasi
        symbol_name = symbol.replace('-USD', '').replace('-USDT', '')
        sample_posts = [
            f"#Bullish on ${symbol_name}! 🚀",
            f"Just bought more ${symbol_name}",
            f"Why ${symbol_name} is undervalued",
            f"${symbol_name} to the moon! 🌙",
            f"Concerned about ${symbol_name} future",
            f"Great project, strong team #${symbol_name}",
            f"${symbol_name} just broke resistance!",
            f"Looking bearish on ${symbol_name} short-term",
            f"${symbol_name} will dominate 2024",
            f"Selling ${symbol_name}, it's overvalued"
        ]
        return sample_posts[:20]
    
    def _extract_key_events(self, symbol: str) -> List[str]:
        """Extract key events dari analisis"""
        events = []
        
        # Simulasi key events
        symbol_name = symbol.replace('-USD', '').replace('-USDT', '')
        possible_events = [
            f"Earnings report for {symbol_name} due soon",
            f"New development update from {symbol_name} team",
            f"Market volatility affecting {symbol_name}",
            f"Institutional adoption of {symbol_name} increasing",
            f"Regulatory news impacting {symbol_name}"
        ]
        
        # Randomly select events
        import random
        num_events = random.randint(1, 3)
        events = random.sample(possible_events, min(num_events, len(possible_events)))
        
        return events
    
    def _generate_summary(self, symbol: str, score: float, label: str, events: List[str]) -> str:
        """Generate ringkasan analisis"""
        symbol_name = symbol.replace('-USD', '').replace('-USDT', '')
        
        if label == "BULLISH":
            sentiment_desc = "positif"
            action = "bullish sentiment dengan potensi kenaikan"
        elif label == "BEARISH":
            sentiment_desc = "negatif"
            action = "bearish sentiment dengan potensi penurunan"
        else:
            sentiment_desc = "netral"
            action = "netral, perlu konfirmasi lebih lanjut"
        
        summary = (
            f"Analisis sentimen untuk {symbol_name} menunjukkan sentimen {sentiment_desc} "
            f"(score: {score:.2f}). Indikator pasar menunjukkan {action}. "
        )
        
        if events:
            summary += f"Event penting: {', '.join(events[:3])}. "
        
        return summary
    
    def _get_default_sentiment(self, symbol: str) -> SentimentResult:
        """Return default sentiment (neutral) jika terjadi error"""
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

# Example usage
if __name__ == "__main__":
    # Testing sentiment agent
    agent = SentimentAgent()
    
    # Test with BTC
    result = agent.analyze("BTC-USD")
    print("=" * 60)
    print(f"Sentiment Analysis Result for {result.symbol}")
    print("=" * 60)
    print(f"Overall Score: {result.overall_score:.3f}")
    print(f"Sentiment: {result.sentiment_label}")
    print(f"Confidence: {result.confidence:.2%}")
    print(f"\nSource Contributions:")
    for source, contribution in result.source_contributions.items():
        print(f"  {source}: {contribution:.3f}")
    print(f"\nKey Events:")
    for event in result.key_events:
        print(f"  - {event}")
    print(f"\nSummary: {result.summary}")
