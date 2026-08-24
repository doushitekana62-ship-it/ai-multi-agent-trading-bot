"""
agents/agent_technical.py

Technical Agent - Menganalisis indikator teknikal.
Dengan dukungan Unified Market Data.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)


@dataclass
class TechnicalResult:
    """Result dari Technical Agent."""
    symbol: str
    timestamp: datetime
    current_price: float
    overall_score: float
    confidence: float
    support_levels: List[float] = field(default_factory=list)
    resistance_levels: List[float] = field(default_factory=list)
    rsi: float = 0.0
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


class TechnicalAgent:
    """
    Technical Analysis Agent.
    
    Menganalisis indikator teknikal dari market data.
    Menggunakan unified price jika tersedia.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.symbol = None
        self.current_price = 0.0
        
        # RSI parameters
        self.rsi_period = self.config.get("rsi_period", 14)
        self.overbought_threshold = self.config.get("overbought_threshold", 70)
        self.oversold_threshold = self.config.get("oversold_threshold", 30)
        
        # MACD parameters
        self.macd_fast = self.config.get("macd_fast", 12)
        self.macd_slow = self.config.get("macd_slow", 26)
        self.macd_signal = self.config.get("macd_signal", 9)
        
        # Bollinger Bands parameters
        self.bb_period = self.config.get("bb_period", 20)
        self.bb_std = self.config.get("bb_std", 2.0)
        
        # Moving Averages
        self.ma_periods = self.config.get("ma_periods", [10, 20, 50, 200])
        
        logger.info("Technical Agent initialized")

    def analyze(
        self,
        symbol: str,
        market_data: Optional[Dict[str, Any]] = None
    ) -> TechnicalResult:
        """
        Analyze technical indicators from market data.
        
        Args:
            symbol: Trading symbol
            market_data: Market data dengan unified price
        
        Returns:
            TechnicalResult
        """
        symbol = symbol.upper()
        market_data = market_data or {}
        self.symbol = symbol

        # ============================================================
        # UNIFIED PRICE - Gunakan dari market_data jika tersedia
        # ============================================================
        
        # Prioritaskan unified_price
        current_price = market_data.get("unified_price")
        if current_price is None:
            current_price = market_data.get("current_price", 0)
        
        try:
            current_price = float(current_price)
        except (TypeError, ValueError):
            current_price = 0
        
        self.current_price = current_price

        # ============================================================
        # EXTRACT OHLCV DATA
        # ============================================================
        
        ohlcv_data = market_data.get("ohlcv", [])
        if not ohlcv_data and "_unified_snapshot" in market_data:
            snapshot = market_data["_unified_snapshot"]
            if hasattr(snapshot, "ohlcv_data"):
                ohlcv_data = [o.to_dict() if hasattr(o, "to_dict") else o for o in snapshot.ohlcv_data]
        
        # Convert to price arrays
        closes = []
        highs = []
        lows = []
        volumes = []
        
        for candle in ohlcv_data:
            try:
                if isinstance(candle, dict):
                    closes.append(float(candle.get("close", 0)))
                    highs.append(float(candle.get("high", 0)))
                    lows.append(float(candle.get("low", 0)))
                    volumes.append(float(candle.get("volume", 0)))
                elif hasattr(candle, "close"):
                    closes.append(float(candle.close))
                    highs.append(float(candle.high))
                    lows.append(float(candle.low))
                    volumes.append(float(candle.volume))
            except (TypeError, ValueError):
                continue
        
        # ============================================================
        # CALCULATE INDICATORS
        # ============================================================
        
        # RSI
        rsi = self._calculate_rsi(closes) if len(closes) > self.rsi_period else 50.0
        
        # MACD
        macd = self._calculate_macd(closes) if len(closes) > self.macd_slow else {"macd": 0, "signal": 0, "histogram": 0}
        
        # Bollinger Bands
        bb = self._calculate_bollinger_bands(closes) if len(closes) > self.bb_period else {
            "upper": current_price * 1.02,
            "middle": current_price,
            "lower": current_price * 0.98,
            "position": "MIDDLE"
        }
        
        # Moving Averages
        ma = {}
        for period in self.ma_periods:
            if len(closes) >= period:
                ma[f"MA{period}"] = sum(closes[-period:]) / period
            else:
                ma[f"MA{period}"] = current_price
        
        # Support & Resistance
        supports, resistances = self._find_support_resistance(closes, highs, lows)
        
        # Volume Analysis
        volume_score, volume_trend = self._analyze_volume(volumes)
        
        # Pattern Detection
        patterns, pattern_score = self._detect_patterns(closes, highs, lows, volumes)
        
        # ============================================================
        # OVERALL SCORE
        # ============================================================
        
        # Weighted combination
        score = 0.0
        score += self._score_rsi(rsi) * 0.25
        score += self._score_macd(macd) * 0.25
        score += self._score_bb(bb, current_price) * 0.15
        score += self._score_ma(ma, current_price) * 0.15
        score += pattern_score * 0.10
        score += volume_score * 0.10
        
        # Clamp
        overall_score = max(-1.0, min(1.0, score))
        
        # Confidence based on data quality and indicator agreement
        data_points = len(closes)
        if data_points < 20:
            confidence = 0.3
        elif data_points < 50:
            confidence = 0.5
        elif data_points < 100:
            confidence = 0.7
        else:
            confidence = 0.8
        
        # Adjust confidence based on indicator agreement
        signals = []
        if rsi > self.overbought_threshold:
            signals.append("BEARISH")
        elif rsi < self.oversold_threshold:
            signals.append("BULLISH")
        else:
            signals.append("NEUTRAL")
        
        if macd.get("histogram", 0) > 0:
            signals.append("BULLISH")
        elif macd.get("histogram", 0) < 0:
            signals.append("BEARISH")
        else:
            signals.append("NEUTRAL")
        
        if current_price > ma.get("MA20", current_price):
            signals.append("BULLISH")
        elif current_price < ma.get("MA20", current_price):
            signals.append("BEARISH")
        else:
            signals.append("NEUTRAL")
        
        bullish_count = signals.count("BULLISH")
        bearish_count = signals.count("BEARISH")
        
        if bullish_count > bearish_count:
            trend = "BULLISH"
        elif bearish_count > bullish_count:
            trend = "BEARISH"
        else:
            trend = "NEUTRAL"
        
        # Confidence based on agreement
        if bullish_count >= 2 or bearish_count >= 2:
            confidence = min(confidence + 0.1, 0.9)
        elif bullish_count == 0 and bearish_count == 0:
            confidence = max(confidence - 0.1, 0.3)
        
        # ============================================================
        # BUILD RESULT
        # ============================================================
        
        # Generate summary
        summary = self._generate_summary(
            symbol, current_price, overall_score, confidence, trend, rsi, macd, bb
        )
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            overall_score, rsi, macd, bb, ma, current_price, trend
        )
        
        return TechnicalResult(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            current_price=current_price,
            overall_score=overall_score,
            confidence=confidence,
            support_levels=supports,
            resistance_levels=resistances,
            rsi=rsi,
            macd=macd,
            bollinger_bands=bb,
            moving_averages=ma,
            detected_patterns=patterns,
            pattern_score=pattern_score,
            volume_score=volume_score,
            volume_trend=volume_trend,
            trend=trend,
            summary=summary,
            recommendations=recommendations
        )

    # ============================================================
    # INDICATOR CALCULATIONS
    # ============================================================

    def _calculate_rsi(self, closes: List[float]) -> float:
        """Calculate RSI indicator."""
        if len(closes) < self.rsi_period + 1:
            return 50.0
        
        gains = 0.0
        losses = 0.0
        
        for i in range(1, self.rsi_period + 1):
            change = closes[-i] - closes[-i-1]
            if change > 0:
                gains += change
            else:
                losses += abs(change)
        
        avg_gain = gains / self.rsi_period
        avg_loss = losses / self.rsi_period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi

    def _calculate_macd(self, closes: List[float]) -> Dict[str, float]:
        """Calculate MACD indicator."""
        if len(closes) < self.macd_slow:
            return {"macd": 0, "signal": 0, "histogram": 0}
        
        # EMA calculation
        def ema(data, period):
            if len(data) < period:
                return 0
            multiplier = 2 / (period + 1)
            ema_value = sum(data[:period]) / period
            for price in data[period:]:
                ema_value = (price * multiplier) + (ema_value * (1 - multiplier))
            return ema_value
        
        fast_ema = ema(closes, self.macd_fast)
        slow_ema = ema(closes, self.macd_slow)
        macd_line = fast_ema - slow_ema
        
        # Signal line (EMA of MACD)
        macd_values = []
        for i in range(self.macd_slow, len(closes)):
            f_ema = ema(closes[:i+1], self.macd_fast)
            s_ema = ema(closes[:i+1], self.macd_slow)
            macd_values.append(f_ema - s_ema)
        
        signal_line = ema(macd_values, self.macd_signal) if len(macd_values) >= self.macd_signal else 0
        histogram = macd_line - signal_line
        
        return {
            "macd": macd_line,
            "signal": signal_line,
            "histogram": histogram
        }

    def _calculate_bollinger_bands(self, closes: List[float]) -> Dict[str, float]:
        """Calculate Bollinger Bands."""
        if len(closes) < self.bb_period:
            return {
                "upper": closes[-1] * 1.02 if closes else 0,
                "middle": closes[-1] if closes else 0,
                "lower": closes[-1] * 0.98 if closes else 0,
                "position": "MIDDLE"
            }
        
        recent = closes[-self.bb_period:]
        middle = sum(recent) / len(recent)
        
        variance = sum((x - middle) ** 2 for x in recent) / len(recent)
        std = math.sqrt(variance)
        
        upper = middle + (std * self.bb_std)
        lower = middle - (std * self.bb_std)
        
        current = closes[-1]
        if current > upper:
            position = "UPPER"
        elif current < lower:
            position = "LOWER"
        else:
            position = "MIDDLE"
        
        return {
            "upper": upper,
            "middle": middle,
            "lower": lower,
            "position": position
        }

    def _find_support_resistance(
        self,
        closes: List[float],
        highs: List[float],
        lows: List[float]
    ) -> Tuple[List[float], List[float]]:
        """Find support and resistance levels."""
        supports = []
        resistances = []
        
        if len(closes) < 20:
            if closes:
                supports.append(closes[-1] * 0.97)
                supports.append(closes[-1] * 0.94)
                resistances.append(closes[-1] * 1.03)
                resistances.append(closes[-1] * 1.06)
            return supports, resistances
        
        # Find local minima and maxima
        window = 5
        for i in range(window, len(closes) - window):
            # Local minima (support)
            is_min = True
            for j in range(1, window + 1):
                if closes[i] > closes[i - j] or closes[i] > closes[i + j]:
                    is_min = False
                    break
            if is_min:
                supports.append(closes[i])
            
            # Local maxima (resistance)
            is_max = True
            for j in range(1, window + 1):
                if closes[i] < closes[i - j] or closes[i] < closes[i + j]:
                    is_max = False
                    break
            if is_max:
                resistances.append(closes[i])
        
        # Filter and return unique levels
        supports = sorted(set(supports))[-5:] if supports else [closes[-1] * 0.97]
        resistances = sorted(set(resistances))[:5] if resistances else [closes[-1] * 1.03]
        
        return supports, resistances

    def _analyze_volume(self, volumes: List[float]) -> Tuple[float, str]:
        """Analyze volume trend."""
        if len(volumes) < 10:
            return 0.0, "NEUTRAL"
        
        recent_avg = sum(volumes[-5:]) / 5
        older_avg = sum(volumes[-10:-5]) / 5
        
        if older_avg == 0:
            return 0.0, "NEUTRAL"
        
        ratio = recent_avg / older_avg
        
        if ratio > 1.5:
            return 0.5, "INCREASING"
        elif ratio < 0.67:
            return -0.5, "DECREASING"
        else:
            return 0.0, "NEUTRAL"

    def _detect_patterns(
        self,
        closes: List[float],
        highs: List[float],
        lows: List[float],
        volumes: List[float]
    ) -> Tuple[List[Dict[str, Any]], float]:
        """Detect candlestick patterns."""
        patterns = []
        pattern_score = 0.0
        
        if len(closes) < 5:
            return patterns, 0.0
        
        # Simple pattern detection
        last_close = closes[-1]
        last_open = closes[-2] if len(closes) > 1 else last_close
        last_high = highs[-1] if highs else last_close
        last_low = lows[-1] if lows else last_close
        
        # Doji
        body = abs(last_close - last_open)
        total_range = last_high - last_low
        if total_range > 0 and body / total_range < 0.1:
            patterns.append({
                "name": "doji",
                "signal": "NEUTRAL",
                "confidence": 0.7,
                "strength": 0.3
            })
            pattern_score += 0.1
        
        # Engulfing (simplified)
        if len(closes) >= 3:
            prev_close = closes[-2]
            prev_open = closes[-3] if len(closes) > 2 else prev_close
            
            # Bullish engulfing
            if last_close > last_open and prev_close < prev_open and last_close > prev_open and last_open < prev_close:
                patterns.append({
                    "name": "engulfing",
                    "signal": "BULLISH",
                    "confidence": 0.8,
                    "strength": 0.8
                })
                pattern_score += 0.3
            
            # Bearish engulfing
            elif last_close < last_open and prev_close > prev_open and last_close < prev_open and last_open > prev_close:
                patterns.append({
                    "name": "engulfing",
                    "signal": "BEARISH",
                    "confidence": 0.8,
                    "strength": 0.8
                })
                pattern_score -= 0.3
        
        # Hammer (simplified)
        if total_range > 0:
            lower_shadow = min(last_open, last_close) - last_low
            upper_shadow = last_high - max(last_open, last_close)
            body_size = abs(last_close - last_open)
            
            if body_size > 0 and lower_shadow > body_size * 2 and upper_shadow < body_size * 0.5:
                patterns.append({
                    "name": "hammer",
                    "signal": "BULLISH",
                    "confidence": 0.6,
                    "strength": 0.5
                })
                pattern_score += 0.2
        
        return patterns, max(-1.0, min(1.0, pattern_score))

    # ============================================================
    # SCORING METHODS
    # ============================================================

    def _score_rsi(self, rsi: float) -> float:
        """Convert RSI to score."""
        if rsi >= self.overbought_threshold:
            return -0.5
        elif rsi <= self.oversold_threshold:
            return 0.5
        else:
            # Linear interpolation
            if rsi > 50:
                return -((rsi - 50) / (self.overbought_threshold - 50)) * 0.5
            else:
                return ((50 - rsi) / (50 - self.oversold_threshold)) * 0.5

    def _score_macd(self, macd: Dict[str, float]) -> float:
        """Convert MACD to score."""
        histogram = macd.get("histogram", 0)
        if histogram > 0:
            return min(0.5, histogram * 10)
        elif histogram < 0:
            return max(-0.5, histogram * 10)
        else:
            return 0.0

    def _score_bb(self, bb: Dict[str, float], price: float) -> float:
        """Convert Bollinger Bands position to score."""
        position = bb.get("position", "MIDDLE")
        if position == "LOWER":
            return 0.4
        elif position == "UPPER":
            return -0.4
        else:
            return 0.0

    def _score_ma(self, ma: Dict[str, float], price: float) -> float:
        """Convert Moving Averages to score."""
        if "MA20" not in ma:
            return 0.0
        
        ma20 = ma["MA20"]
        if price > ma20 * 1.02:
            return 0.3
        elif price < ma20 * 0.98:
            return -0.3
        else:
            return 0.0

    # ============================================================
    # SUMMARY & RECOMMENDATIONS
    # ============================================================

    def _generate_summary(
        self,
        symbol: str,
        price: float,
        score: float,
        confidence: float,
        trend: str,
        rsi: float,
        macd: Dict[str, float],
        bb: Dict[str, float]
    ) -> str:
        """Generate summary string."""
        direction = "bullish" if score > 0.2 else "bearish" if score < -0.2 else "neutral"
        
        summary = (
            f"Analisis teknikal {symbol} menunjukkan sinyal {direction} (score: {score:.2f}). "
            f"RSI: {rsi:.1f}, MACD histogram: {macd.get('histogram', 0):.2f}, "
            f"BB position: {bb.get('position', 'MIDDLE')}. "
            f"Confidence: {confidence:.1%}."
        )
        return summary

    def _generate_recommendations(
        self,
        score: float,
        rsi: float,
        macd: Dict[str, float],
        bb: Dict[str, float],
        ma: Dict[str, float],
        price: float,
        trend: str
    ) -> List[str]:
        """Generate trading recommendations."""
        recommendations = []
        
        if score > 0.3:
            recommendations.append("BUY - Indikator teknikal bullish")
        elif score < -0.3:
            recommendations.append("SELL - Indikator teknikal bearish")
        else:
            recommendations.append("HOLD - Indikator teknikal netral")
        
        if rsi > 70:
            recommendations.append("Overbought - Risiko koreksi")
        elif rsi < 30:
            recommendations.append("Oversold - Potensi rebound")
        
        if macd.get("histogram", 0) > 0:
            recommendations.append("MACD bullish - Momentum positif")
        elif macd.get("histogram", 0) < 0:
            recommendations.append("MACD bearish - Momentum negatif")
        
        if bb.get("position") == "LOWER":
            recommendations.append("Dekat lower band - Support kuat")
        elif bb.get("position") == "UPPER":
            recommendations.append("Dekat upper band - Resistance kuat")
        
        if "MA20" in ma:
            if price > ma["MA20"]:
                recommendations.append("Harga di atas MA20 - Trend naik")
            else:
                recommendations.append("Harga di bawah MA20 - Trend turun")
        
        return recommendations
