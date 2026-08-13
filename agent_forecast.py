"""
Agent 5: Forecasting Pergerakan Harga
Bertugas memprediksi pergerakan harga di masa depan menggunakan
berbagai metode forecasting seperti time series analysis, 
machine learning, dan pattern recognition.

Agent ini memberikan gambaran tentang kemungkinan jalur harga
di 1-7 hari ke depan.
"""

import os
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
import yfinance as yf
from scipy import stats
from scipy.signal import find_peaks
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor
import warnings
warnings.filterwarnings('ignore')

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class PricePrediction:
    """Data class untuk prediksi harga"""
    timestamp: datetime
    predicted_price: float
    confidence_interval_lower: float
    confidence_interval_upper: float
    confidence: float  # 0 to 1
    horizon: str  # SHORT, MEDIUM, LONG

@dataclass
class ForecastResult:
    """Data class untuk hasil forecasting"""
    symbol: str
    timestamp: datetime
    current_price: float
    
    # Predictions untuk berbagai horizon
    short_term: PricePrediction  # 1-2 hari
    medium_term: PricePrediction  # 3-5 hari
    long_term: PricePrediction    # 6-7 hari
    
    # Price paths (multiple scenarios)
    bullish_path: List[float]
    bearish_path: List[float]
    most_likely_path: List[float]
    scenarios: Dict[str, Any]
    
    # Trend analysis
    primary_trend: str  # "BULLISH", "BEARISH", "CONSOLIDATING"
    trend_strength: float  # 0 to 1
    next_move_probability: Dict[str, float]  # UP, DOWN, SIDEWAYS
    
    # Technical forecast
    expected_high: float
    expected_low: float
    expected_range: Dict[str, float]
    
    # Key levels
    key_resistance: List[float]
    key_support: List[float]
    
    # Summary
    summary: str
    recommendations: List[str]

class ForecastAgent:
    """
    Agent Forecasting dengan multiple methods
    """
    
    def __init__(self, config: Dict = None):
        """
        Initialize Forecast Agent
        
        Args:
            config: Konfigurasi untuk agent
        """
        self.config = config or {}
        
        # Model parameters
        self.forecast_horizons = {
            'short': 2,    # 2 hari
            'medium': 5,   # 5 hari
            'long': 7      # 7 hari
        }
        
        # Confidence levels
        self.confidence_levels = {
            'short': 0.85,
            'medium': 0.75,
            'long': 0.65
        }
        
        # Model weights untuk ensemble
        self.model_weights = {
            'arima': 0.20,
            'linear_regression': 0.15,
            'random_forest': 0.20,
            'pattern_recognition': 0.20,
            'monte_carlo': 0.15,
            'sentiment_technical': 0.10
        }
        
        # Cache
        self.cache = {}
        self.cache_duration = timedelta(hours=1)
        
        # Historical patterns database
        self.pattern_database = []
        self._initialize_pattern_database()
        
        logger.info("Forecast Agent initialized successfully")
    
    def analyze(self, symbol: str, 
                sentiment_result: Any = None,
                technical_result: Any = None,
                market_data: Dict = None) -> ForecastResult:
        """
        Main method untuk forecasting harga
        
        Args:
            symbol: Simbol aset
            sentiment_result: Hasil dari Sentiment Agent (opsional)
            technical_result: Hasil dari Technical Agent (opsional)
            market_data: Data pasar tambahan
        
        Returns:
            ForecastResult: Hasil forecasting lengkap
        """
        logger.info(f"Generating forecast for {symbol}")
        
        # Check cache
        cache_key = f"forecast_{symbol}"
        if cache_key in self.cache:
            cached_result, cache_time = self.cache[cache_key]
            if datetime.now() - cache_time < self.cache_duration:
                logger.info(f"Using cached forecast for {symbol}")
                return cached_result
        
        try:
            # Fetch historical data
            df = self._fetch_historical_data(symbol)
            if df is None or len(df) < 50:
                return self._get_default_forecast(symbol)
            
            current_price = df['Close'].iloc[-1]
            prices = df['Close'].values
            dates = df.index
            
            # 1. Multiple forecasting methods
            predictions = {}
            
            # ARIMA-like forecasting (using simple auto-regression)
            predictions['arima'] = self._arima_forecast(prices, self.forecast_horizons['long'])
            
            # Linear Regression
            predictions['linear_regression'] = self._linear_regression_forecast(prices)
            
            # Random Forest
            predictions['random_forest'] = self._random_forest_forecast(df)
            
            # Pattern Recognition
            predictions['pattern_recognition'] = self._pattern_recognition_forecast(prices)
            
            # Monte Carlo simulation
            predictions['monte_carlo'] = self._monte_carlo_forecast(prices)
            
            # Sentiment-Technical weighted forecast
            if sentiment_result and technical_result:
                predictions['sentiment_technical'] = self._sentiment_technical_forecast(
                    prices, sentiment_result, technical_result
                )
            
            # 2. Ensemble prediction (weighted average)
            ensemble_prediction = self._ensemble_forecast(predictions)
            
            # 3. Generate multiple scenarios
            scenarios = self._generate_scenarios(
                current_price, ensemble_prediction, predictions
            )
            
            # 4. Trend analysis
            primary_trend, trend_strength = self._analyze_trend(prices)
            next_move_prob = self._predict_next_move(prices, ensemble_prediction)
            
            # 5. Create predictions untuk berbagai horizon
            short_pred = self._create_price_prediction(
                ensemble_prediction, horizon='short', current_price=current_price
            )
            medium_pred = self._create_price_prediction(
                ensemble_prediction, horizon='medium', current_price=current_price
            )
            long_pred = self._create_price_prediction(
                ensemble_prediction, horizon='long', current_price=current_price
            )
            
            # 6. Key levels
            key_support, key_resistance = self._find_key_levels(df)
            
            # 7. Expected range
            expected_high, expected_low = self._calculate_expected_range(
                predictions, current_price
            )
            
            # 8. Generate summary
            summary = self._generate_summary(
                symbol, current_price, primary_trend, ensemble_prediction,
                short_pred, scenarios
            )
            
            # 9. Recommendations
            recommendations = self._generate_recommendations(
                primary_trend, ensemble_prediction, short_pred,
                key_support, key_resistance
            )
            
            # Build result
            result = ForecastResult(
                symbol=symbol,
                timestamp=datetime.now(),
                current_price=current_price,
                short_term=short_pred,
                medium_term=medium_pred,
                long_term=long_pred,
                bullish_path=scenarios['bullish'],
                bearish_path=scenarios['bearish'],
                most_likely_path=scenarios['most_likely'],
                scenarios={
                    'bullish': {'path': scenarios['bullish'], 'probability': scenarios['bullish_prob']},
                    'bearish': {'path': scenarios['bearish'], 'probability': scenarios['bearish_prob']},
                    'most_likely': {'path': scenarios['most_likely'], 'probability': scenarios['most_likely_prob']}
                },
                primary_trend=primary_trend,
                trend_strength=trend_strength,
                next_move_probability=next_move_prob,
                expected_high=expected_high,
                expected_low=expected_low,
                expected_range={
                    'high': expected_high,
                    'low': expected_low,
                    'range_percent': ((expected_high - expected_low) / current_price) * 100
                },
                key_resistance=key_resistance,
                key_support=key_support,
                summary=summary,
                recommendations=recommendations
            )
            
            # Cache result
            self.cache[cache_key] = (result, datetime.now())
            
            return result
            
        except Exception as e:
            logger.error(f"Error generating forecast for {symbol}: {str(e)}")
            return self._get_default_forecast(symbol)
    
    def _fetch_historical_data(self, symbol: str) -> pd.DataFrame:
        """Fetch historical OHLCV data"""
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period='1y', interval='1d')
            return df
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            return None
    
    def _arima_forecast(self, prices: np.ndarray, horizon: int) -> np.ndarray:
        """
        Simple ARIMA-like forecasting using auto-regression
        
        Returns:
            Array of predicted prices
        """
        try:
            # Use last 30 days for AR model
            data = prices[-30:]
            predictions = []
            
            # Simple auto-regressive model: y(t) = a*y(t-1) + b*y(t-2) + c
            if len(data) > 10:
                # Fit AR(2) model
                y = data[2:]
                X = np.column_stack([data[1:-1], data[:-2], np.ones(len(data)-2)])
                
                try:
                    coef, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
                    
                    # Predict next values
                    last_values = data[-2:]
                    for _ in range(horizon):
                        next_pred = coef[0] * last_values[-1] + coef[1] * last_values[-2] + coef[2]
                        predictions.append(next_pred)
                        last_values = np.append(last_values, next_pred)[-2:]
                    
                    return np.array(predictions)
                except:
                    return self._simple_moving_average_forecast(data, horizon)
            
            return self._simple_moving_average_forecast(prices, horizon)
            
        except Exception as e:
            logger.error(f"Error in ARIMA forecast: {e}")
            return self._simple_moving_average_forecast(prices, horizon)
    
    def _simple_moving_average_forecast(self, prices: np.ndarray, horizon: int) -> np.ndarray:
        """Simple moving average forecast (fallback)"""
        if len(prices) < 10:
            return np.full(horizon, prices[-1] if len(prices) > 0 else 0)
        
        # Use weighted moving average
        weights = np.exp(np.linspace(-1, 0, 10))
        weights = weights / weights.sum()
        ma = np.convolve(prices[-10:], weights, mode='valid')
        
        if len(ma) > 0:
            trend = ma[-1] / ma[-3] - 1 if len(ma) >= 3 else 0
            last_price = prices[-1]
            predictions = [last_price * (1 + trend) ** (i + 1) for i in range(horizon)]
            return np.array(predictions)
        
        return np.full(horizon, prices[-1])
    
    def _linear_regression_forecast(self, prices: np.ndarray) -> np.ndarray:
        """
        Linear regression forecast based on historical prices
        """
        try:
            n = len(prices)
            if n < 10:
                return np.full(self.forecast_horizons['long'], prices[-1] if len(prices) > 0 else 0)
            
            # Use last 60 days
            data = prices[-60:]
            X = np.arange(len(data)).reshape(-1, 1)
            y = data.reshape(-1, 1)
            
            model = LinearRegression()
            model.fit(X, y)
            
            # Predict next days
            future_X = np.arange(len(data), len(data) + self.forecast_horizons['long']).reshape(-1, 1)
            predictions = model.predict(future_X).flatten()
            
            return predictions
            
        except Exception as e:
            logger.error(f"Error in linear regression forecast: {e}")
            return np.full(self.forecast_horizons['long'], prices[-1])
    
    def _random_forest_forecast(self, df: pd.DataFrame) -> np.ndarray:
        """
        Random forest regression for forecasting
        """
        try:
            # Create features
            prices = df['Close'].values
            if len(prices) < 50:
                return np.full(self.forecast_horizons['long'], prices[-1])
            
            # Use last 100 days
            data = prices[-100:]
            X = []
            y = []
            
            # Create lag features
            for i in range(10, len(data) - 1):
                features = data[i-10:i]
                X.append(features)
                y.append(data[i])
            
            if len(X) < 20:
                return self._linear_regression_forecast(prices)
            
            X = np.array(X)
            y = np.array(y)
            
            # Train Random Forest
            rf = RandomForestRegressor(n_estimators=50, max_depth=10, random_state=42)
            rf.fit(X, y)
            
            # Predict next days
            predictions = []
            last_features = data[-10:].tolist()
            
            for _ in range(self.forecast_horizons['long']):
                features_array = np.array(last_features).reshape(1, -1)
                next_price = rf.predict(features_array)[0]
                predictions.append(next_price)
                last_features = last_features[1:] + [next_price]
            
            return np.array(predictions)
            
        except Exception as e:
            logger.error(f"Error in random forest forecast: {e}")
            return self._linear_regression_forecast(df['Close'].values)
    
    def _pattern_recognition_forecast(self, prices: np.ndarray) -> np.ndarray:
        """
        Forecast based on historical pattern recognition
        """
        try:
            if len(prices) < 30:
                return np.full(self.forecast_horizons['long'], prices[-1])
            
            # Find similar patterns in history
            current_pattern = prices[-30:]
            similarities = []
            
            # Search in pattern database
            for pattern in self.pattern_database:
                if len(pattern['prices']) >= 30:
                    # Calculate similarity
                    sim = self._calculate_pattern_similarity(
                        current_pattern, pattern['prices'][:30]
                    )
                    similarities.append({
                        'similarity': sim,
                        'future': pattern['future_prices'][:self.forecast_horizons['long']]
                    })
            
            if similarities:
                # Sort by similarity
                similarities.sort(key=lambda x: x['similarity'], reverse=True)
                
                # Take top 5 similar patterns
                top_patterns = similarities[:5]
                
                # Average their future prices
                weighted_predictions = []
                total_weight = 0
                
                for pattern in top_patterns:
                    weight = pattern['similarity']
                    weighted_predictions.append(np.array(pattern['future']) * weight)
                    total_weight += weight
                
                if total_weight > 0:
                    avg_prediction = np.sum(weighted_predictions, axis=0) / total_weight
                    return avg_prediction
            
            return np.full(self.forecast_horizons['long'], prices[-1])
            
        except Exception as e:
            logger.error(f"Error in pattern recognition forecast: {e}")
            return np.full(self.forecast_horizons['long'], prices[-1])
    
    def _calculate_pattern_similarity(self, pattern1: np.ndarray, pattern2: np.ndarray) -> float:
        """Calculate similarity between two price patterns"""
        if len(pattern1) != len(pattern2):
            return 0.0
        
        # Normalize patterns
        p1_norm = (pattern1 - pattern1.mean()) / pattern1.std() if pattern1.std() > 0 else pattern1
        p2_norm = (pattern2 - pattern2.mean()) / pattern2.std() if pattern2.std() > 0 else pattern2
        
        # Calculate correlation
        correlation = np.corrcoef(p1_norm, p2_norm)[0, 1]
        
        # Also consider pattern shape (peaks and troughs)
        shape_similarity = self._compare_pattern_shape(pattern1, pattern2)
        
        # Combine metrics
        similarity = 0.7 * (correlation + 1) / 2 + 0.3 * shape_similarity
        
        return similarity
    
    def _compare_pattern_shape(self, pattern1: np.ndarray, pattern2: np.ndarray) -> float:
        """Compare pattern shape using peak/trough analysis"""
        # Find peaks and troughs
        peaks1, _ = find_peaks(pattern1, distance=3)
        peaks2, _ = find_peaks(pattern2, distance=3)
        troughs1, _ = find_peaks(-pattern1, distance=3)
        troughs2, _ = find_peaks(-pattern2, distance=3)
        
        # Compare number of peaks/troughs
        if len(peaks1) != len(peaks2) or len(troughs1) != len(troughs2):
            return 0.5
        
        # Compare relative positions
        pos_similarity = 0.5
        if len(peaks1) > 0 and len(peaks2) > 0:
            pos1 = peaks1 / len(pattern1)
            pos2 = peaks2 / len(pattern2)
            pos_similarity = 1 - np.mean(np.abs(pos1 - pos2))
        
        return 0.5 + pos_similarity * 0.5
    
    def _monte_carlo_forecast(self, prices: np.ndarray) -> np.ndarray:
        """
        Monte Carlo simulation for price paths
        """
        try:
            n_simulations = 100
            horizon = self.forecast_horizons['long']
            
            # Calculate returns
            returns = np.diff(prices) / prices[:-1]
            
            if len(returns) < 10:
                return np.full(horizon, prices[-1])
            
            # Parameters
            mu = np.mean(returns)
            sigma = np.std(returns)
            last_price = prices[-1]
            
            # Run simulations
            simulations = []
            for _ in range(n_simulations):
                path = [last_price]
                for _ in range(horizon):
                    # Geometric Brownian Motion
                    random_return = np.random.normal(mu, sigma)
                    new_price = path[-1] * (1 + random_return)
                    path.append(new_price)
                simulations.append(path[1:])
            
            # Average all paths
            avg_path = np.mean(simulations, axis=0)
            
            return avg_path
            
        except Exception as e:
            logger.error(f"Error in Monte Carlo forecast: {e}")
            return np.full(self.forecast_horizons['long'], prices[-1])
    
    def _sentiment_technical_forecast(self, prices: np.ndarray, 
                                     sentiment_result: Any,
                                     technical_result: Any) -> np.ndarray:
        """
        Forecast combining sentiment and technical analysis
        """
        try:
            # Get sentiment and technical scores
            sentiment_score = getattr(sentiment_result, 'overall_score', 0)
            technical_score = getattr(technical_result, 'overall_score', 0)
            
            # Combine scores
            combined_score = (sentiment_score * 0.4 + technical_score * 0.6)
            
            # Adjust trend based on combined score
            last_price = prices[-1]
            trend_factor = combined_score * 0.05  # Max 5% adjustment per day
            
            # Generate forecast
            predictions = []
            for i in range(self.forecast_horizons['long']):
                # Decay trend factor over time
                decay = 1 / (1 + i * 0.1)
                adjustment = trend_factor * decay
                
                # Simple momentum forecast
                if len(prices) > 5:
                    momentum = (prices[-1] - prices[-5]) / prices[-5] * 0.5
                else:
                    momentum = 0
                
                next_price = last_price * (1 + momentum + adjustment)
                predictions.append(next_price)
                last_price = next_price
            
            return np.array(predictions)
            
        except Exception as e:
            logger.error(f"Error in sentiment-technical forecast: {e}")
            return np.full(self.forecast_horizons['long'], prices[-1])
    
    def _ensemble_forecast(self, predictions: Dict[str, np.ndarray]) -> np.ndarray:
        """
        Combine all predictions using weighted average
        """
        if not predictions:
            return np.array([0] * self.forecast_horizons['long'])
        
        weighted_sum = None
        total_weight = 0
        
        for method, pred in predictions.items():
            weight = self.model_weights.get(method, 0.1)
            
            if weighted_sum is None:
                weighted_sum = pred * weight
            else:
                weighted_sum += pred * weight
            
            total_weight += weight
        
        if total_weight > 0 and weighted_sum is not None:
            return weighted_sum / total_weight
        
        return predictions.get('arima', np.zeros(self.forecast_horizons['long']))
    
    def _generate_scenarios(self, current_price: float, 
                           ensemble_pred: np.ndarray,
                           predictions: Dict) -> Dict[str, Any]:
        """
        Generate multiple scenarios (bullish, bearish, most likely)
        """
        horizon = len(ensemble_pred)
        
        # Most likely: ensemble prediction
        most_likely = ensemble_pred
        
        # Bullish: upper bound based on predictions
        all_predictions = list(predictions.values())
        if all_predictions:
            bullish = np.max(all_predictions, axis=0)
            bearish = np.min(all_predictions, axis=0)
        else:
            bullish = ensemble_pred * 1.10
            bearish = ensemble_pred * 0.90
        
        # Calculate probabilities based on model agreement
        if all_predictions:
            std_dev = np.std(all_predictions, axis=0)
            agreement = 1 - np.mean(std_dev / np.mean(all_predictions, axis=0))
            most_likely_prob = min(0.6, agreement * 0.8)
        else:
            most_likely_prob = 0.4
        
        # Probabilities for scenarios
        bullish_prob = 0.25
        bearish_prob = 0.25
        
        return {
            'bullish': bullish,
            'bearish': bearish,
            'most_likely': most_likely,
            'bullish_prob': bullish_prob,
            'bearish_prob': bearish_prob,
            'most_likely_prob': most_likely_prob
        }
    
    def _analyze_trend(self, prices: np.ndarray) -> Tuple[str, float]:
        """
        Analyze primary trend and strength
        """
        if len(prices) < 20:
            return "CONSOLIDATING", 0.0
        
        # Calculate moving averages
        ma20 = np.mean(prices[-20:])
        ma50 = np.mean(prices[-50:]) if len(prices) >= 50 else ma20
        ma100 = np.mean(prices[-100:]) if len(prices) >= 100 else ma50
        
        current_price = prices[-1]
        
        # Determine trend
        if current_price > ma20 > ma50 > ma100:
            trend = "BULLISH"
        elif current_price < ma20 < ma50 < ma100:
            trend = "BEARISH"
        else:
            trend = "CONSOLIDATING"
        
        # Calculate trend strength
        if trend == "BULLISH":
            strength = (current_price - ma20) / ma20
        elif trend == "BEARISH":
            strength = (ma20 - current_price) / ma20
        else:
            # Check if consolidating
            price_range = (prices[-20:].max() - prices[-20:].min()) / prices[-20:].mean()
            if price_range < 0.03:
                strength = 0.3  # Tight consolidation
            else:
                strength = 0.0
        
        strength = min(abs(strength) * 5, 1.0)  # Scale to 0-1
        
        return trend, strength
    
    def _predict_next_move(self, prices: np.ndarray, 
                          ensemble_pred: np.ndarray) -> Dict[str, float]:
        """
        Predict probability of next move (UP, DOWN, SIDEWAYS)
        """
        if len(prices) < 5:
            return {'UP': 0.33, 'DOWN': 0.33, 'SIDEWAYS': 0.34}
        
        # Based on ensemble prediction
        predicted_change = (ensemble_pred[0] - prices[-1]) / prices[-1] if len(ensemble_pred) > 0 else 0
        
        # Based on historical momentum
        historical_momentum = (prices[-1] - prices[-5]) / prices[-5] if len(prices) >= 5 else 0
        
        # Combine both
        combined = predicted_change * 0.6 + historical_momentum * 0.4
        
        if combined > 0.01:
            up_prob = min(0.7, 0.5 + combined * 5)
            down_prob = 0.2
            sideways_prob = 1 - up_prob - down_prob
        elif combined < -0.01:
            down_prob = min(0.7, 0.5 - combined * 5)
            up_prob = 0.2
            sideways_prob = 1 - up_prob - down_prob
        else:
            up_prob = 0.33
            down_prob = 0.33
            sideways_prob = 0.34
        
        return {
            'UP': max(0, min(1, up_prob)),
            'DOWN': max(0, min(1, down_prob)),
            'SIDEWAYS': max(0, min(1, sideways_prob))
        }
    
    def _create_price_prediction(self, ensemble_pred: np.ndarray, 
                                 horizon: str,
                                 current_price: float) -> PricePrediction:
        """
        Create PricePrediction object for specific horizon
        """
        horizon_days = {
            'short': 2,
            'medium': 5,
            'long': 7
        }
        
        days = horizon_days.get(horizon, 2)
        idx = min(days - 1, len(ensemble_pred) - 1)
        idx = max(0, idx)
        
        predicted_price = ensemble_pred[idx] if idx < len(ensemble_pred) else current_price
        
        # Calculate confidence interval
        confidence = self.confidence_levels.get(horizon, 0.7)
        spread = abs(predicted_price - current_price) * (1 - confidence) * 0.5
        
        return PricePrediction(
            timestamp=datetime.now() + timedelta(days=days),
            predicted_price=predicted_price,
            confidence_interval_lower=predicted_price - spread,
            confidence_interval_upper=predicted_price + spread,
            confidence=confidence,
            horizon=horizon.upper()
        )
    
    def _find_key_levels(self, df: pd.DataFrame) -> Tuple[List[float], List[float]]:
        """Find key support and resistance levels"""
        high = df['High'].values
        low = df['Low'].values
        close = df['Close'].values
        
        # Find local maxima and minima
        window = 10
        peaks = []
        troughs = []
        
        for i in range(window, len(high) - window):
            if high[i] == max(high[i-window:i+window]):
                peaks.append(high[i])
            if low[i] == min(low[i-window:i+window]):
                troughs.append(low[i])
        
        # Cluster levels
        resistance = self._cluster_levels(peaks, tolerance=0.03)
        support = self._cluster_levels(troughs, tolerance=0.03)
        
        # Sort
        resistance.sort(reverse=True)
        support.sort()
        
        return support[:3], resistance[:3]
    
    def _cluster_levels(self, levels: List[float], tolerance: float = 0.03) -> List[float]:
        """Cluster similar price levels"""
        if not levels:
            return []
        
        levels = sorted(levels)
        clusters = []
        current_cluster = [levels[0]]
        
        for level in levels[1:]:
            cluster_avg = sum(current_cluster) / len(current_cluster)
            if abs(level - cluster_avg) / cluster_avg <= tolerance:
                current_cluster.append(level)
            else:
                clusters.append(sum(current_cluster) / len(current_cluster))
                current_cluster = [level]
        
        if current_cluster:
            clusters.append(sum(current_cluster) / len(current_cluster))
        
        return clusters
    
    def _calculate_expected_range(self, predictions: Dict, 
                                 current_price: float) -> Tuple[float, float]:
        """Calculate expected price range"""
        # Get all predictions
        all_predictions = []
        for pred in predictions.values():
            if len(pred) > 0:
                all_predictions.extend(pred[:7])
        
        if not all_predictions:
            return current_price * 1.05, current_price * 0.95
        
        # Calculate expected high and low
        expected_high = max(all_predictions)
        expected_low = min(all_predictions)
        
        # Add buffer
        buffer = (expected_high - expected_low) * 0.1
        
        return expected_high + buffer, expected_low - buffer
    
    def _generate_summary(self, symbol: str, current_price: float,
                         trend: str, ensemble_pred: np.ndarray,
                         short_pred: PricePrediction,
                         scenarios: Dict) -> str:
        """Generate forecast summary"""
        symbol_name = symbol.replace('-USD', '').replace('-USDT', '')
        price_change = ((ensemble_pred[0] if len(ensemble_pred) > 0 else current_price) - current_price) / current_price
        
        summary = f"Forecast untuk {symbol_name}: "
        summary += f"Harga saat ini ${current_price:.2f}. "
        
        if trend == "BULLISH":
            summary += "Trend BULLISH dengan strength {:.1%}. ".format(
                self._analyze_trend([current_price] * 10)[1]
            )
        elif trend == "BEARISH":
            summary += "Trend BEARISH dengan strength {:.1%}. ".format(
                self._analyze_trend([current_price] * 10)[1]
            )
        else:
            summary += "Trend CONSOLIDATING. "
        
        if abs(price_change) > 0.02:
            direction = "naik" if price_change > 0 else "turun"
            summary += f"Diprediksi {direction} {abs(price_change):.1%} dalam 2 hari ke depan. "
        else:
            summary += "Diprediksi sideways dalam waktu dekat. "
        
        summary += f"Target jangka pendek: ${short_pred.predicted_price:.2f}. "
        
        # Add scenario info
        most_likely_prob = scenarios.get('most_likely_prob', 0.4)
        summary += f"Probabilitas skenario utama: {most_likely_prob:.1%}."
        
        return summary
    
    def _generate_recommendations(self, trend: str, ensemble_pred: np.ndarray,
                                 short_pred: PricePrediction,
                                 support: List[float],
                                 resistance: List[float]) -> List[str]:
        """Generate recommendations based on forecast"""
        recommendations = []
        
        # Trend-based recommendations
        if trend == "BULLISH":
            recommendations.append("✅ Trend bullish - Pertimbangkan posisi BUY")
            if resistance:
                recommendations.append(f"🎯 Target resistance: ${resistance[0]:.2f}")
            if support:
                recommendations.append(f"🛑 Stop loss di bawah support: ${support[0]:.2f}")
        elif trend == "BEARISH":
            recommendations.append("❌ Trend bearish - Pertimbangkan posisi SELL")
            if support:
                recommendations.append(f"🎯 Target support: ${support[0]:.2f}")
            if resistance:
                recommendations.append(f"🛑 Stop loss di atas resistance: ${resistance[0]:.2f}")
        else:
            recommendations.append("⏸️ Trend konsolidasi - Wait and see")
            if support and resistance:
                recommendations.append(f"📊 Trading range: ${support[0]:.2f} - ${resistance[0]:.2f}")
        
        # Confidence-based
        if short_pred.confidence > 0.75:
            recommendations.append(f"📈 Keyakinan tinggi ({short_pred.confidence:.1%})")
        elif short_pred.confidence < 0.5:
            recommendations.append(f"⚠️ Keyakinan rendah ({short_pred.confidence:.1%}) - Kurangi posisi")
        
        # Risk management
        predicted_move = abs(ensemble_pred[0] - 0) if len(ensemble_pred) > 0 else 0
        if predicted_move < 0.01:
            recommendations.append("⚠️ Pergerakan rendah diprediksi - Hindari overtrading")
        
        return recommendations[:4]
    
    def _initialize_pattern_database(self):
        """Initialize pattern database with sample patterns"""
        # This would be populated from historical data in production
        # Adding some sample patterns for demonstration
        
        # Sample bullish pattern
        self.pattern_database.append({
            'prices': [100, 101, 102, 103, 104, 105, 106, 107, 108, 109,
                      110, 111, 112, 113, 114, 115, 116, 117, 118, 119,
                      120, 121, 122, 123, 124, 125, 126, 127, 128, 129],
            'future_prices': [130, 131, 132, 133, 134, 135, 136]
        })
        
        # Sample bearish pattern
        self.pattern_database.append({
            'prices': [200, 199, 198, 197, 196, 195, 194, 193, 192, 191,
                      190, 189, 188, 187, 186, 185, 184, 183, 182, 181,
                      180, 179, 178, 177, 176, 175, 174, 173, 172, 171],
            'future_prices': [170, 169, 168, 167, 166, 165, 164]
        })
    
    def _get_default_forecast(self, symbol: str) -> ForecastResult:
        """Return default forecast jika terjadi error"""
        current_price = 0.0
        default_pred = PricePrediction(
            timestamp=datetime.now() + timedelta(days=1),
            predicted_price=0.0,
            confidence_interval_lower=0.0,
            confidence_interval_upper=0.0,
            confidence=0.0,
            horizon="SHORT"
        )
        
        return ForecastResult(
            symbol=symbol,
            timestamp=datetime.now(),
            current_price=current_price,
            short_term=default_pred,
            medium_term=default_pred,
            long_term=default_pred,
            bullish_path=[],
            bearish_path=[],
            most_likely_path=[],
            scenarios={},
            primary_trend="CONSOLIDATING",
            trend_strength=0.0,
            next_move_probability={'UP': 0.33, 'DOWN': 0.33, 'SIDEWAYS': 0.34},
            expected_high=0.0,
            expected_low=0.0,
            expected_range={'high': 0, 'low': 0, 'range_percent': 0},
            key_resistance=[],
            key_support=[],
            summary="Unable to generate forecast - default to neutral",
            recommendations=["Wait for more data"]
        )

# Example usage
if __name__ == "__main__":
    # Initialize forecast agent
    forecast_agent = ForecastAgent()
    
    # Test with BTC
    print("=" * 60)
    print("FORECAST ANALYSIS - BTC-USD")
    print("=" * 60)
    
    result = forecast_agent.analyze("BTC-USD")
    
    print(f"\n📊 CURRENT PRICE: ${result.current_price:.2f}")
    print(f"📈 PRIMARY TREND: {result.primary_trend} (Strength: {result.trend_strength:.1%})")
    
    print(f"\n🎯 PRICE PREDICTIONS:")
    print(f"  Short-term (2 days): ${result.short_term.predicted_price:.2f}")
    print(f"    Confidence: {result.short_term.confidence:.1%}")
    print(f"    Range: ${result.short_term.confidence_interval_lower:.2f} - ${result.short_term.confidence_interval_upper:.2f}")
    
    print(f"\n  Medium-term (5 days): ${result.medium_term.predicted_price:.2f}")
    print(f"    Confidence: {result.medium_term.confidence:.1%}")
    
    print(f"\n  Long-term (7 days): ${result.long_term.predicted_price:.2f}")
    print(f"    Confidence: {result.long_term.confidence:.1%}")
    
    print(f"\n📊 NEXT MOVE PROBABILITY:")
    for direction, prob in result.next_move_probability.items():
        print(f"  {direction}: {prob:.1%}")
    
    print(f"\n📈 EXPECTED RANGE:")
    print(f"  High: ${result.expected_high:.2f}")
    print(f"  Low: ${result.expected_low:.2f}")
    print(f"  Range: {result.expected_range['range_percent']:.1f}%")
    
    print(f"\n🔑 KEY LEVELS:")
    if result.key_support:
        print(f"  Support: ${', $'.join([f'{s:.2f}' for s in result.key_support])}")
    if result.key_resistance:
        print(f"  Resistance: ${', $'.join([f'{r:.2f}' for r in result.key_resistance])}")
    
    print(f"\n📝 SUMMARY: {result.summary}")
    
    print(f"\n💡 RECOMMENDATIONS:")
    for rec in result.recommendations:
        print(f"  • {rec}")
