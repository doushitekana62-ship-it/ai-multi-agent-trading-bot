"""
Agent 2: Analisis Teknikal - Candlestick & Market Demand
Bertugas menganalisis pola candlestick, support/resistance, volume,
dan indikator teknikal lainnya untuk mengidentifikasi peluang trading.
"""

import os
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
import yfinance as yf
import talib
from scipy import stats
from sklearn.preprocessing import StandardScaler

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class TechnicalResult:
    """Data class untuk hasil analisis teknikal"""
    symbol: str
    timestamp: datetime
    current_price: float
    
    # Candlestick patterns
    detected_patterns: List[Dict[str, Any]]
    pattern_score: float  # -1 to 1 (bearish to bullish)
    
    # Support & Resistance
    support_levels: List[float]
    resistance_levels: List[float]
    current_position: str  # "NEAR_SUPPORT", "NEAR_RESISTANCE", "MIDDLE"
    
    # Technical Indicators
    rsi: float
    macd: Dict[str, float]
    bollinger_bands: Dict[str, float]
    moving_averages: Dict[str, float]
    
    # Volume Analysis
    volume_score: float  # -1 to 1
    volume_trend: str  # "INCREASING", "DECREASING", "STABLE"
    
    # Demand Score
    demand_score: float  # 0 to 1
    supply_score: float  # 0 to 1
    overall_score: float  # -1 to 1 (bearish to bullish)
    
    # Summary
    summary: str
    recommendations: List[str]

class TechnicalAgent:
    """
    Agent Analisis Teknikal dengan kemampuan multi-indicator
    """
    
    def __init__(self, config: Dict = None):
        """
        Initialize Technical Agent
        
        Args:
            config: Konfigurasi untuk agent
        """
        self.config = config or {}
        
        # Threshold untuk berbagai indikator
        self.thresholds = {
            'rsi_oversold': 30,
            'rsi_overbought': 70,
            'volume_threshold': 1.5,  # Volume > 1.5x average
            'pattern_confidence': 0.6,
            'support_resistance_tolerance': 0.02  # 2% tolerance
        }
        
        # Weight untuk scoring
        self.weights = {
            'patterns': 0.25,
            'indicators': 0.35,
            'volume': 0.15,
            'supply_demand': 0.25
        }
        
        # Cache untuk data historis
        self.cache = {}
        self.cache_duration = timedelta(minutes=2)
        
        logger.info("Technical Agent initialized successfully")
    
    def analyze(self, symbol: str, market_data: Dict = None) -> TechnicalResult:
        """
        Main method untuk analisis teknikal
        
        Args:
            symbol: Simbol aset (e.g., 'AAPL', 'BTC-USD')
            market_data: Data pasar opsional
        
        Returns:
            TechnicalResult: Hasil analisis teknikal lengkap
        """
        logger.info(f"Analyzing technicals for {symbol}")
        
        # Check cache
        cache_key = f"technical_{symbol}"
        if cache_key in self.cache:
            cached_result, cache_time = self.cache[cache_key]
            if datetime.now() - cache_time < self.cache_duration:
                logger.info(f"Using cached technical analysis for {symbol}")
                return cached_result
        
        try:
            # Fetch data jika belum ada
            if market_data and 'ohlcv' in market_data:
                df = market_data['ohlcv']
            else:
                df = self._fetch_historical_data(symbol)
            
            if df is None or len(df) < 100:
                logger.warning(f"Insufficient data for {symbol}")
                return self._get_default_result(symbol)
            
            # 1. Detect Candlestick Patterns
            detected_patterns = self._detect_patterns(df)
            pattern_score = self._score_patterns(detected_patterns)
            
            # 2. Find Support & Resistance
            support_levels, resistance_levels = self._find_support_resistance(df)
            current_price = df['Close'].iloc[-1]
            current_position = self._determine_position(
                current_price, support_levels, resistance_levels
            )
            
            # 3. Calculate Technical Indicators
            indicators = self._calculate_indicators(df)
            
            # 4. Analyze Volume
            volume_score, volume_trend = self._analyze_volume(df)
            
            # 5. Calculate Supply & Demand
            demand_score, supply_score = self._calculate_supply_demand(df)
            
            # 6. Calculate Overall Score
            overall_score = self._calculate_overall_score({
                'patterns': pattern_score,
                'indicators': indicators['composite_score'],
                'volume': volume_score,
                'supply_demand': demand_score - supply_score
            })
            
            # 7. Generate Summary & Recommendations
            summary = self._generate_summary(
                symbol, overall_score, indicators, detected_patterns
            )
            recommendations = self._generate_recommendations(
                overall_score, indicators, current_position, detected_patterns
            )
            
            # Buat result
            result = TechnicalResult(
                symbol=symbol,
                timestamp=datetime.now(),
                current_price=current_price,
                detected_patterns=detected_patterns,
                pattern_score=pattern_score,
                support_levels=support_levels,
                resistance_levels=resistance_levels,
                current_position=current_position,
                rsi=indicators['rsi'],
                macd=indicators['macd'],
                bollinger_bands=indicators['bollinger_bands'],
                moving_averages=indicators['moving_averages'],
                volume_score=volume_score,
                volume_trend=volume_trend,
                demand_score=demand_score,
                supply_score=supply_score,
                overall_score=overall_score,
                summary=summary,
                recommendations=recommendations
            )
            
            # Cache result
            self.cache[cache_key] = (result, datetime.now())
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing technicals for {symbol}: {str(e)}")
            return self._get_default_result(symbol)
    
    def _fetch_historical_data(self, symbol: str) -> pd.DataFrame:
        """
        Fetch historical OHLCV data dari Yahoo Finance
        
        Returns:
            DataFrame dengan columns: Open, High, Low, Close, Volume
        """
        try:
            ticker = yf.Ticker(symbol)
            
            # Ambil 100 hari terakhir dengan interval 1 jam
            df = ticker.history(period='100d', interval='1h')
            
            if df.empty:
                # Fallback: ambil 100 hari dengan interval 1 hari
                df = ticker.history(period='100d')
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            return None
    
    def _detect_patterns(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Mendeteksi candlestick patterns menggunakan TA-Lib
        
        Returns:
            List of detected patterns with confidence
        """
        patterns = []
        
        # Pastikan kolom yang diperlukan ada
        required_cols = ['Open', 'High', 'Low', 'Close']
        if not all(col in df.columns for col in required_cols):
            return patterns
        
        open_price = df['Open'].values
        high_price = df['High'].values
        low_price = df['Low'].values
        close_price = df['Close'].values
        
        # Dictionary pattern functions dari TA-Lib
        pattern_functions = {
            'hammer': talib.CDLHAMMER,
            'doji': talib.CDLDOJI,
            'engulfing': talib.CDLENGULFING,
            'morning_star': talib.CDLMORNINGSTAR,
            'evening_star': talib.CDLEVENINGSTAR,
            'three_white_soldiers': talib.CDL3WHITESOLDIERS,
            'three_black_crows': talib.CDL3BLACKCROWS,
            'shooting_star': talib.CDLSHOOTINGSTAR,
            'hanging_man': talib.CDLHANGINGMAN,
            'bullish_harami': talib.CDLHARAMI,
            'bearish_harami': talib.CDLHARAMI,
            'piercing': talib.CDLPIERCING,
            'dark_cloud_cover': talib.CDLDARKCLOUDCOVER,
            'doji_star': talib.CDLDOJISTAR,
            'spinning_top': talib.CDLSPINNINGTOP
        }
        
        # Deteksi setiap pattern
        for pattern_name, func in pattern_functions.items():
            try:
                result = func(open_price, high_price, low_price, close_price)
                
                # TA-Lib return: 100 (bullish), -100 (bearish), 0 (none)
                last_value = result[-1] if len(result) > 0 else 0
                
                if last_value != 0:
                    patterns.append({
                        'name': pattern_name,
                        'signal': 'BULLISH' if last_value > 0 else 'BEARISH',
                        'confidence': min(abs(last_value) / 100, 1.0),
                        'strength': abs(last_value) / 100
                    })
            except Exception as e:
                logger.debug(f"Error detecting pattern {pattern_name}: {e}")
                continue
        
        # Filter patterns dengan confidence tinggi
        patterns = [p for p in patterns if p['confidence'] > 0.3]
        
        # Sort by confidence
        patterns.sort(key=lambda x: x['confidence'], reverse=True)
        
        return patterns[:5]  # Return top 5 patterns
    
    def _score_patterns(self, patterns: List[Dict[str, Any]]) -> float:
        """
        Score detected patterns
        
        Returns:
            float: -1 to 1 (bearish to bullish)
        """
        if not patterns:
            return 0.0
        
        bullish_score = 0.0
        bearish_score = 0.0
        
        for pattern in patterns:
            if pattern['signal'] == 'BULLISH':
                bullish_score += pattern['confidence'] * pattern['strength']
            else:
                bearish_score += pattern['confidence'] * pattern['strength']
        
        total_score = bullish_score - bearish_score
        total_confidence = bullish_score + bearish_score
        
        if total_confidence > 0:
            return np.clip(total_score / total_confidence, -1.0, 1.0)
        return 0.0
    
    def _find_support_resistance(self, df: pd.DataFrame) -> Tuple[List[float], List[float]]:
        """
        Find support and resistance levels menggunakan pivot points
        
        Returns:
            Tuple of (support_levels, resistance_levels)
        """
        high = df['High'].values
        low = df['Low'].values
        close = df['Close'].values
        
        # Find local maxima and minima
        window = 20  # Window untuk local max/min
        
        local_max = []
        local_min = []
        
        for i in range(window, len(high) - window):
            # Local maximum
            if high[i] == max(high[i-window:i+window]):
                local_max.append(high[i])
            
            # Local minimum
            if low[i] == min(low[i-window:i+window]):
                local_min.append(low[i])
        
        # Cluster similar values (within 2% tolerance)
        resistance_levels = self._cluster_values(local_max, tolerance=0.02)
        support_levels = self._cluster_values(local_min, tolerance=0.02)
        
        # Sort
        resistance_levels.sort(reverse=True)
        support_levels.sort()
        
        # Return top 3 levels
        return support_levels[:3], resistance_levels[:3]
    
    def _cluster_values(self, values: List[float], tolerance: float = 0.02) -> List[float]:
        """
        Cluster values that are within tolerance
        
        Returns:
            List of clustered values (average of each cluster)
        """
        if not values:
            return []
        
        values = sorted(values)
        clusters = []
        current_cluster = [values[0]]
        
        for val in values[1:]:
            # Cek jika value dalam tolerance dari cluster average
            cluster_avg = sum(current_cluster) / len(current_cluster)
            if abs(val - cluster_avg) / cluster_avg <= tolerance:
                current_cluster.append(val)
            else:
                clusters.append(sum(current_cluster) / len(current_cluster))
                current_cluster = [val]
        
        if current_cluster:
            clusters.append(sum(current_cluster) / len(current_cluster))
        
        return clusters
    
    def _determine_position(self, price: float, support: List[float], 
                           resistance: List[float]) -> str:
        """
        Determine current position relative to support/resistance
        """
        if not support or not resistance:
            return "MIDDLE"
        
        nearest_support = min(support, key=lambda x: abs(x - price))
        nearest_resistance = min(resistance, key=lambda x: abs(x - price))
        
        support_diff = abs(price - nearest_support) / price
        resistance_diff = abs(price - nearest_resistance) / price
        
        if support_diff < 0.02:  # Within 2%
            return "NEAR_SUPPORT"
        elif resistance_diff < 0.02:
            return "NEAR_RESISTANCE"
        else:
            return "MIDDLE"
    
    def _calculate_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate berbagai technical indicators
        """
        close = df['Close'].values
        
        # RSI
        rsi = talib.RSI(close, timeperiod=14)
        current_rsi = rsi[-1] if len(rsi) > 0 else 50
        
        # MACD
        macd, macd_signal, macd_hist = talib.MACD(close)
        current_macd = {
            'macd': macd[-1] if len(macd) > 0 else 0,
            'signal': macd_signal[-1] if len(macd_signal) > 0 else 0,
            'histogram': macd_hist[-1] if len(macd_hist) > 0 else 0
        }
        
        # Bollinger Bands
        upper, middle, lower = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2)
        current_price = close[-1] if len(close) > 0 else 0
        current_bands = {
            'upper': upper[-1] if len(upper) > 0 else current_price * 1.1,
            'middle': middle[-1] if len(middle) > 0 else current_price,
            'lower': lower[-1] if len(lower) > 0 else current_price * 0.9,
            'position': self._get_bb_position(current_price, upper[-1], lower[-1]) if len(upper) > 0 and len(lower) > 0 else "MIDDLE"
        }
        
        # Moving Averages
        ma_10 = talib.SMA(close, timeperiod=10)[-1] if len(close) >= 10 else close[-1]
        ma_20 = talib.SMA(close, timeperiod=20)[-1] if len(close) >= 20 else close[-1]
        ma_50 = talib.SMA(close, timeperiod=50)[-1] if len(close) >= 50 else close[-1]
        ma_200 = talib.SMA(close, timeperiod=200)[-1] if len(close) >= 200 else close[-1]
        
        # Trend strength
        trend_strength = self._calculate_trend_strength(close)
        
        # Composite score dari indicators
        composite_score = self._score_indicators({
            'rsi': current_rsi,
            'macd': current_macd,
            'bb_position': current_bands['position'],
            'ma_trend': self._get_ma_trend(close[-1], [ma_10, ma_20, ma_50])
        })
        
        return {
            'rsi': current_rsi,
            'macd': current_macd,
            'bollinger_bands': current_bands,
            'moving_averages': {
                'MA10': ma_10,
                'MA20': ma_20,
                'MA50': ma_50,
                'MA200': ma_200
            },
            'trend_strength': trend_strength,
            'composite_score': composite_score
        }
    
    def _get_bb_position(self, price: float, upper: float, lower: float) -> str:
        """Determine price position within Bollinger Bands"""
        if price >= upper * 0.98:
            return "NEAR_UPPER"
        elif price <= lower * 1.02:
            return "NEAR_LOWER"
        else:
            return "MIDDLE"
    
    def _get_ma_trend(self, price: float, ma_values: List[float]) -> str:
        """Determine trend based on moving averages"""
        bullish_count = sum(1 for ma in ma_values if price > ma)
        bearish_count = sum(1 for ma in ma_values if price < ma)
        
        if bullish_count >= 2:
            return "BULLISH"
        elif bearish_count >= 2:
            return "BEARISH"
        else:
            return "NEUTRAL"
    
    def _score_indicators(self, indicators: Dict) -> float:
        """Score indicators untuk composite score"""
        score = 0.0
        
        # RSI scoring
        rsi = indicators.get('rsi', 50)
        if rsi < 30:
            score += 0.5  # Oversold = bullish
        elif rsi > 70:
            score -= 0.5  # Overbought = bearish
        else:
            score += (50 - rsi) / 100
        
        # MACD scoring
        macd = indicators.get('macd', {})
        if macd.get('histogram', 0) > 0:
            score += 0.3
        else:
            score -= 0.3
        
        # Bollinger Bands scoring
        bb_pos = indicators.get('bb_position', 'MIDDLE')
        if bb_pos == 'NEAR_LOWER':
            score += 0.3
        elif bb_pos == 'NEAR_UPPER':
            score -= 0.3
        
        # MA trend scoring
        ma_trend = indicators.get('ma_trend', 'NEUTRAL')
        if ma_trend == 'BULLISH':
            score += 0.2
        elif ma_trend == 'BEARISH':
            score -= 0.2
        
        return np.clip(score, -1.0, 1.0)
    
    def _calculate_trend_strength(self, close: np.ndarray) -> float:
        """Calculate trend strength using ADX"""
        try:
            adx = talib.ADX(close, close, close, timeperiod=14)
            current_adx = adx[-1] if len(adx) > 0 else 0
            return min(current_adx / 100, 1.0)
        except:
            return 0.5
    
    def _analyze_volume(self, df: pd.DataFrame) -> Tuple[float, str]:
        """
        Analyze volume patterns
        
        Returns:
            Tuple of (volume_score, volume_trend)
        """
        volume = df['Volume'].values
        
        if len(volume) < 20:
            return 0.0, "STABLE"
        
        avg_volume = np.mean(volume[-20:-1])  # Average excluding current
        current_volume = volume[-1]
        
        # Volume trend
        volume_trend = "STABLE"
        if current_volume > avg_volume * self.thresholds['volume_threshold']:
            volume_trend = "INCREASING"
        elif current_volume < avg_volume * 0.5:
            volume_trend = "DECREASING"
        
        # Volume score
        # High volume on uptrend = bullish, high volume on downtrend = bearish
        price_change = (df['Close'].iloc[-1] - df['Close'].iloc[-2]) / df['Close'].iloc[-2] if len(df) > 1 else 0
        
        if volume_trend == "INCREASING":
            if price_change > 0:
                volume_score = 0.5  # Bullish confirmation
            else:
                volume_score = -0.5  # Bearish confirmation
        else:
            volume_score = 0.0
        
        return volume_score, volume_trend
    
    def _calculate_supply_demand(self, df: pd.DataFrame) -> Tuple[float, float]:
        """
        Calculate supply and demand scores
        
        Returns:
            Tuple of (demand_score, supply_score)
        """
        high = df['High'].values
        low = df['Low'].values
        close = df['Close'].values
        
        # Simple supply/demand berdasarkan volume di level harga tertentu
        price_bins = np.linspace(min(low), max(high), 20)
        volume_profile = []
        
        for i in range(len(price_bins) - 1):
            mask = (close >= price_bins[i]) & (close < price_bins[i+1])
            if any(mask):
                volume_profile.append({
                    'price_level': (price_bins[i] + price_bins[i+1]) / 2,
                    'volume': df['Volume'][mask].sum() if any(mask) else 0
                })
        
        if not volume_profile:
            return 0.5, 0.5
        
        # Find high volume nodes
        volumes = [v['volume'] for v in volume_profile]
        max_volume = max(volumes) if volumes else 1
        
        # Normalize
        for v in volume_profile:
            v['volume_ratio'] = v['volume'] / max_volume
        
        # Demand (buying pressure) - high volume at support levels
        # Supply (selling pressure) - high volume at resistance levels
        demand_nodes = [v for v in volume_profile if v['volume_ratio'] > 0.5 and v['price_level'] < close[-1]]
        supply_nodes = [v for v in volume_profile if v['volume_ratio'] > 0.5 and v['price_level'] > close[-1]]
        
        demand_score = min(len(demand_nodes) / 5, 1.0)
        supply_score = min(len(supply_nodes) / 5, 1.0)
        
        return demand_score, supply_score
    
    def _calculate_overall_score(self, components: Dict[str, float]) -> float:
        """Calculate weighted overall score"""
        total_score = 0.0
        total_weight = 0.0
        
        for comp, score in components.items():
            weight = self.weights.get(comp, 0.1)
            total_score += score * weight
            total_weight += weight
        
        if total_weight > 0:
            return np.clip(total_score / total_weight, -1.0, 1.0)
        return 0.0
    
    def _generate_summary(self, symbol: str, score: float, 
                         indicators: Dict, patterns: List) -> str:
        """Generate summary dari analisis teknikal"""
        symbol_name = symbol.replace('-USD', '').replace('-USDT', '')
        
        if score > 0.3:
            signal = "bullish"
            action = "mempertimbangkan posisi BUY"
        elif score < -0.3:
            signal = "bearish"
            action = "mempertimbangkan posisi SELL"
        else:
            signal = "netral"
            action = "wait and see"
        
        summary = f"Analisis teknikal {symbol_name} menunjukkan sinyal {signal} "
        summary += f"(score: {score:.2f}). "
        
        # Tambahkan info RSI
        rsi = indicators.get('rsi', 50)
        if rsi > 70:
            summary += f"RSI di {rsi:.1f} menunjukkan kondisi overbought. "
        elif rsi < 30:
            summary += f"RSI di {rsi:.1f} menunjukkan kondisi oversold. "
        
        # Tambahkan info pattern
        if patterns:
            top_pattern = patterns[0]
            summary += f"Terdeteksi pola {top_pattern['name']} dengan sinyal {top_pattern['signal']}. "
        
        summary += f"Rekomendasi: {action}."
        
        return summary
    
    def _generate_recommendations(self, score: float, indicators: Dict,
                                 position: str, patterns: List) -> List[str]:
        """Generate recommendations based on analysis"""
        recommendations = []
        
        # Berdasarkan overall score
        if score > 0.5:
            recommendations.append("STRONG BUY - Semua indikator bullish")
        elif score > 0.2:
            recommendations.append("BUY - Indikator cenderung bullish")
        elif score < -0.5:
            recommendations.append("STRONG SELL - Semua indikator bearish")
        elif score < -0.2:
            recommendations.append("SELL - Indikator cenderung bearish")
        else:
            recommendations.append("HOLD - Tidak ada sinyal jelas")
        
        # Berdasarkan RSI
        rsi = indicators.get('rsi', 50)
        if rsi < 25:
            recommendations.append("RSI sangat oversold - Potensi rebound")
        elif rsi > 75:
            recommendations.append("RSI sangat overbought - Waspada koreksi")
        
        # Berdasarkan posisi support/resistance
        if position == "NEAR_SUPPORT":
            recommendations.append("Dekat level support - Potensi bounce")
        elif position == "NEAR_RESISTANCE":
            recommendations.append("Dekat level resistance - Waspada rejection")
        
        # Berdasarkan pattern
        if patterns:
            top_pattern = patterns[0]
            if top_pattern['signal'] == 'BULLISH' and top_pattern['confidence'] > 0.7:
                recommendations.append(f"Konfirmasi bullish dari pola {top_pattern['name']}")
            elif top_pattern['signal'] == 'BEARISH' and top_pattern['confidence'] > 0.7:
                recommendations.append(f"Konfirmasi bearish dari pola {top_pattern['name']}")
        
        return recommendations[:3]  # Return top 3 recommendations
    
    def _get_default_result(self, symbol: str) -> TechnicalResult:
        """Return default result jika terjadi error"""
        return TechnicalResult(
            symbol=symbol,
            timestamp=datetime.now(),
            current_price=0.0,
            detected_patterns=[],
            pattern_score=0.0,
            support_levels=[],
            resistance_levels=[],
            current_position="MIDDLE",
            rsi=50.0,
            macd={'macd': 0, 'signal': 0, 'histogram': 0},
            bollinger_bands={'upper': 0, 'middle': 0, 'lower': 0, 'position': 'MIDDLE'},
            moving_averages={'MA10': 0, 'MA20': 0, 'MA50': 0, 'MA200': 0},
            volume_score=0.0,
            volume_trend="STABLE",
            demand_score=0.5,
            supply_score=0.5,
            overall_score=0.0,
            summary=f"Unable to analyze technicals for {symbol}. Default to neutral.",
            recommendations=["HOLD - Insufficient data"]
        )

# Example usage
if __name__ == "__main__":
    # Testing technical agent
    agent = TechnicalAgent()
    
    # Test dengan BTC
    result = agent.analyze("BTC-USD")
    print("=" * 60)
    print(f"Technical Analysis Result for {result.symbol}")
    print("=" * 60)
    print(f"Current Price: ${result.current_price:.2f}")
    print(f"Overall Score: {result.overall_score:.3f}")
    print(f"Pattern Score: {result.pattern_score:.3f}")
    print(f"RSI: {result.rsi:.1f}")
    print(f"Volume Trend: {result.volume_trend}")
    print(f"Position: {result.current_position}")
    print(f"\nSupport Levels: {[f'${s:.2f}' for s in result.support_levels]}")
    print(f"Resistance Levels: {[f'${r:.2f}' for r in result.resistance_levels]}")
    print(f"\nDetected Patterns:")
    for pattern in result.detected_patterns:
        print(f"  - {pattern['name']}: {pattern['signal']} (confidence: {pattern['confidence']:.2%})")
    print(f"\nSummary: {result.summary}")
    print(f"\nRecommendations:")
    for rec in result.recommendations:
        print(f"  • {rec}")
