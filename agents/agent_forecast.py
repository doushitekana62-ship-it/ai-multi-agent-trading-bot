"""
Agent 5: Forecasting Pergerakan Harga - V5
Dengan dukungan Unified Market Data
"""

import logging
import warnings
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd
from scipy.signal import find_peaks
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor

warnings.filterwarnings("ignore")

logger = logging.getLogger(__name__)


# ============================================================
# DATA CLASSES (SAMA)
# ============================================================

@dataclass
class PricePrediction:
    timestamp: datetime
    predicted_price: float
    confidence_interval_lower: float
    confidence_interval_upper: float
    confidence: float
    horizon: str
    predicted_change_percent: float = 0.0


@dataclass
class ForecastResult:
    symbol: str
    timestamp: datetime
    current_price: float
    short_term: PricePrediction
    medium_term: PricePrediction
    long_term: PricePrediction
    bullish_path: List[float]
    bearish_path: List[float]
    most_likely_path: List[float]
    scenarios: Dict[str, Any]
    primary_trend: str
    trend_strength: float
    next_move_probability: Dict[str, float]
    expected_high: float
    expected_low: float
    expected_range: Dict[str, float]
    key_resistance: List[float]
    key_support: List[float]
    summary: str
    recommendations: List[str]
    model_predictions: Dict[str, List[float]]
    model_weights: Dict[str, float]
    model_status: Dict[str, str]
    data_quality: Dict[str, float]
    model_agreement: float
    forecast_score: float
    forecast_action: str
    warnings: List[str]


class ForecastAgent:
    """
    Forecast Agent dengan Unified Market Data.
    
    SEKARANG: Menggunakan data dari UnifiedMarketSnapshot,
    bukan fetching data sendiri via yfinance.
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        
        # Horizons (days)
        self.forecast_horizons = {
            "short": 2,
            "medium": 5,
            "long": 7
        }
        
        # Model weights
        self.base_model_weights = {
            "arima": 0.20,
            "linear_regression": 0.12,
            "random_forest": 0.20,
            "pattern_recognition": 0.13,
            "monte_carlo": 0.15,
            "sentiment_technical": 0.20,
        }
        self.model_weights = dict(self.base_model_weights)
        
        # Validation
        self.max_reasonable_move = float(
            self.config.get("max_reasonable_move", 0.15)
        )
        self.pattern_window = int(
            self.config.get("pattern_window", 30)
        )
        self.min_pattern_history = int(
            self.config.get("min_pattern_history", 90)
        )
        
        # Cache
        self.cache = {}
        self.cache_duration = timedelta(
            minutes=int(self.config.get("cache_minutes", 10))
        )
        
        logger.info("Forecast Agent initialized with Unified Market Data support")

    # ============================================================
    # MAIN ANALYZE - DENGAN UNIFIED DATA
    # ============================================================

    def analyze(
        self,
        symbol: str,
        sentiment_result: Any = None,
        technical_result: Any = None,
        market_data: Optional[Dict] = None
    ) -> ForecastResult:
        """
        Generate forecast menggunakan Unified Market Data.
        
        Args:
            symbol: Simbol aset (BTC-USD, ETH-USD, dll)
            sentiment_result: Hasil dari Sentiment Agent
            technical_result: Hasil dari Technical Agent
            market_data: Data dari UnifiedMarketSnapshot
        """
        logger.info(f"Generating forecast for {symbol}")
        
        symbol = symbol.upper()
        market_data = market_data or {}
        warnings_list = []
        
        try:
            # ============================================================
            # FIX: GUNAKAN UNIFIED DATA
            # ============================================================
            
            # Extract unified price
            current_price = market_data.get("unified_price")
            if current_price is None:
                current_price = market_data.get("current_price", 0)
            
            try:
                current_price = float(current_price)
            except (TypeError, ValueError):
                current_price = 0
            
            if current_price <= 0:
                warnings_list.append("Invalid current price")
                return self._get_default_forecast(symbol, reason="Invalid current price")
            
            # Extract OHLCV dari snapshot
            ohlcv_data = market_data.get("ohlcv", [])
            if not ohlcv_data and "_unified_snapshot" in market_data:
                snapshot = market_data["_unified_snapshot"]
                if hasattr(snapshot, "ohlcv_data"):
                    ohlcv_data = [o.to_dict() if hasattr(o, "to_dict") else o for o in snapshot.ohlcv_data]
            
            # Convert to price arrays
            prices = []
            highs = []
            lows = []
            volumes = []
            
            for candle in ohlcv_data:
                try:
                    if isinstance(candle, dict):
                        prices.append(float(candle.get("close", 0)))
                        highs.append(float(candle.get("high", 0)))
                        lows.append(float(candle.get("low", 0)))
                        volumes.append(float(candle.get("volume", 0)))
                    elif hasattr(candle, "close"):
                        prices.append(float(candle.close))
                        highs.append(float(candle.high))
                        lows.append(float(candle.low))
                        volumes.append(float(candle.volume))
                except (TypeError, ValueError):
                    continue
            
            prices = np.asarray(prices, dtype=float)
            
            if len(prices) < 80:
                warnings_list.append("Insufficient historical data")
                return self._get_default_forecast(symbol, current_price, "Insufficient data")
            
            # ============================================================
            # DATA QUALITY
            # ============================================================
            
            data_quality = self._calculate_data_quality_from_data(prices, volumes)
            
            if data_quality["quality_score"] < 0.70:
                warnings_list.append("Historical data quality below preferred threshold")
            
            # ============================================================
            # VOLATILITY
            # ============================================================
            
            returns = self._calculate_returns(prices)
            volatility = self._annualized_or_daily_volatility(returns)
            
            # ============================================================
            # MODEL PREDICTIONS
            # ============================================================
            
            model_status = {}
            raw_predictions = {}
            
            # 1. ARIMA-like
            raw_predictions["arima"] = self._safe_model_call(
                "arima",
                lambda: self._arima_forecast(prices, self.forecast_horizons["long"]),
                current_price, model_status, warnings_list
            )
            
            # 2. Linear Regression
            raw_predictions["linear_regression"] = self._safe_model_call(
                "linear_regression",
                lambda: self._linear_regression_forecast(prices),
                current_price, model_status, warnings_list
            )
            
            # 3. Random Forest
            raw_predictions["random_forest"] = self._safe_model_call(
                "random_forest",
                lambda: self._random_forest_forecast(prices),
                current_price, model_status, warnings_list
            )
            
            # 4. Pattern Recognition
            raw_predictions["pattern_recognition"] = self._safe_model_call(
                "pattern_recognition",
                lambda: self._pattern_recognition_forecast(prices),
                current_price, model_status, warnings_list
            )
            
            # 5. Monte Carlo
            raw_predictions["monte_carlo"] = self._safe_model_call(
                "monte_carlo",
                lambda: self._monte_carlo_forecast(prices),
                current_price, model_status, warnings_list
            )
            
            # 6. Sentiment + Technical
            if sentiment_result is not None and technical_result is not None:
                raw_predictions["sentiment_technical"] = self._safe_model_call(
                    "sentiment_technical",
                    lambda: self._sentiment_technical_forecast(
                        prices, sentiment_result, technical_result
                    ),
                    current_price, model_status, warnings_list
                )
            else:
                model_status["sentiment_technical"] = "SKIPPED"
            
            # ============================================================
            # VALIDATE PREDICTIONS
            # ============================================================
            
            validated_predictions = {}
            for model_name, prediction in raw_predictions.items():
                if prediction is None:
                    continue
                clean = self._validate_prediction(
                    prediction, current_price, model_name, warnings_list
                )
                if clean is not None:
                    validated_predictions[model_name] = clean
                    model_status[model_name] = "OK"
                else:
                    model_status[model_name] = "REJECTED"
            
            if not validated_predictions:
                warnings_list.append("All forecasting models failed validation")
                return self._get_default_forecast(
                    symbol, current_price, "All models rejected"
                )
            
            # ============================================================
            # DYNAMIC WEIGHTS & ENSEMBLE
            # ============================================================
            
            dynamic_weights = self._calculate_dynamic_weights(
                validated_predictions, current_price, volatility,
                data_quality["quality_score"]
            )
            self.model_weights = dynamic_weights
            
            ensemble_prediction = self._ensemble_forecast(
                validated_predictions, dynamic_weights, current_price
            )
            ensemble_prediction = self._repair_prediction_path(
                ensemble_prediction, current_price
            )
            
            # ============================================================
            # MODEL AGREEMENT
            # ============================================================
            
            model_agreement = self._calculate_model_agreement(
                validated_predictions, current_price
            )
            
            # ============================================================
            # TREND & PROBABILITY
            # ============================================================
            
            primary_trend, trend_strength = self._analyze_trend(prices)
            
            next_move_probability = self._predict_next_move(
                prices=prices,
                ensemble_pred=ensemble_prediction,
                volatility=volatility,
                model_agreement=model_agreement
            )
            
            # ============================================================
            # SCENARIOS
            # ============================================================
            
            scenarios = self._generate_scenarios(
                current_price, ensemble_prediction, validated_predictions,
                volatility, model_agreement, primary_trend
            )
            
            # ============================================================
            # PRICE PREDICTIONS
            # ============================================================
            
            short_pred = self._create_price_prediction(
                ensemble_prediction, "short", current_price,
                volatility, model_agreement
            )
            medium_pred = self._create_price_prediction(
                ensemble_prediction, "medium", current_price,
                volatility, model_agreement
            )
            long_pred = self._create_price_prediction(
                ensemble_prediction, "long", current_price,
                volatility, model_agreement
            )
            
            # ============================================================
            # SUPPORT / RESISTANCE
            # ============================================================
            
            key_support, key_resistance = self._find_key_levels(prices, highs, lows)
            
            # ============================================================
            # EXPECTED RANGE
            # ============================================================
            
            expected_high, expected_low = self._calculate_expected_range(
                validated_predictions, current_price, volatility
            )
            
            # ============================================================
            # FORECAST SCORE & ACTION
            # ============================================================
            
            forecast_score = self._calculate_forecast_score(
                current_price, short_pred, primary_trend, trend_strength,
                next_move_probability, model_agreement, volatility
            )
            
            forecast_action = self._translate_forecast_to_action(
                forecast_score, primary_trend, trend_strength,
                next_move_probability, model_agreement, short_pred, volatility
            )
            
            # ============================================================
            # SUMMARY & RECOMMENDATIONS
            # ============================================================
            
            summary = self._generate_summary(
                symbol, current_price, primary_trend, trend_strength,
                short_pred, medium_pred, long_pred, next_move_probability,
                model_agreement, forecast_score, forecast_action
            )
            
            recommendations = self._generate_recommendations(
                primary_trend, trend_strength, forecast_action, forecast_score,
                short_pred, key_support, key_resistance, next_move_probability,
                model_agreement, volatility
            )
            
            # ============================================================
            # BUILD RESULT
            # ============================================================
            
            model_predictions = {
                name: [float(x) for x in pred]
                for name, pred in validated_predictions.items()
            }
            
            return ForecastResult(
                symbol=symbol,
                timestamp=datetime.now(timezone.utc),
                current_price=float(current_price),
                short_term=short_pred,
                medium_term=medium_pred,
                long_term=long_pred,
                bullish_path=[float(x) for x in scenarios["bullish"]],
                bearish_path=[float(x) for x in scenarios["bearish"]],
                most_likely_path=[float(x) for x in scenarios["most_likely"]],
                scenarios=scenarios,
                primary_trend=primary_trend,
                trend_strength=float(trend_strength),
                next_move_probability={k: float(v) for k, v in next_move_probability.items()},
                expected_high=float(expected_high),
                expected_low=float(expected_low),
                expected_range={
                    "high": float(expected_high),
                    "low": float(expected_low),
                    "range_percent": float((expected_high - expected_low) / current_price * 100)
                },
                key_resistance=[float(x) for x in key_resistance],
                key_support=[float(x) for x in key_support],
                summary=summary,
                recommendations=recommendations,
                model_predictions=model_predictions,
                model_weights={k: float(v) for k, v in dynamic_weights.items()},
                model_status=model_status,
                data_quality={k: float(v) for k, v in data_quality.items()},
                model_agreement=float(model_agreement),
                forecast_score=float(forecast_score),
                forecast_action=forecast_action,
                warnings=warnings_list
            )
            
        except Exception as e:
            logger.exception(f"Error generating forecast for {symbol}: {e}")
            warnings_list.append(f"Forecast exception: {str(e)}")
            return self._get_default_forecast(
                symbol, current_price if 'current_price' in locals() else 0,
                "Forecast exception", warnings_list
            )

    # ============================================================
    # DATA QUALITY DARI UNIFIED DATA
    # ============================================================
    
    def _calculate_data_quality_from_data(
        self,
        prices: np.ndarray,
        volumes: List[float]
    ) -> Dict[str, float]:
        """Calculate data quality from unified data."""
        observations = len(prices)
        
        missing_ratio = 0.0
        if observations > 0:
            missing_ratio = np.isnan(prices).mean()
        
        returns = self._calculate_returns(prices)
        volatility = float(np.std(returns)) if len(returns) else 0.0
        
        observation_score = min(observations / 365.0, 1.0)
        missing_score = max(0.0, 1.0 - missing_ratio)
        finite_score = 1.0 if np.all(np.isfinite(prices)) else 0.0
        
        quality_score = observation_score * 0.40 + missing_score * 0.35 + finite_score * 0.25
        
        return {
            "observations": float(observations),
            "return_volatility": volatility,
            "missing_ratio": float(missing_ratio),
            "quality_score": float(np.clip(quality_score, 0.0, 1.0))
        }
    
    # ============================================================
    # SUPPORT / RESISTANCE DARI UNIFIED DATA
    # ============================================================
    
    def _find_key_levels(
        self,
        prices: np.ndarray,
        highs: List[float],
        lows: List[float]
    ) -> Tuple[List[float], List[float]]:
        """Find support and resistance from unified data."""
        if len(prices) < 20:
            return [prices[-1] * 0.97], [prices[-1] * 1.03]
        
        # Use highs and lows if available
        high_array = np.asarray(highs) if highs else prices
        low_array = np.asarray(lows) if lows else prices
        
        window = 10
        peaks = []
        troughs = []
        
        for i in range(window, len(high_array) - window):
            if high_array[i] == np.max(high_array[i-window:i+window+1]):
                peaks.append(float(high_array[i]))
            if low_array[i] == np.min(low_array[i-window:i+window+1]):
                troughs.append(float(low_array[i]))
        
        resistance = self._cluster_levels(peaks, tolerance=0.02)
        support = self._cluster_levels(troughs, tolerance=0.02)
        
        current_price = float(prices[-1])
        
        support = [l for l in support if l < current_price]
        resistance = [l for l in resistance if l > current_price]
        
        support.sort(reverse=True)
        resistance.sort()
        
        return support[:3], resistance[:3]
    
    def _cluster_levels(self, levels: List[float], tolerance: float = 0.02) -> List[float]:
        """Cluster price levels."""
        if not levels:
            return []
        
        levels = sorted([float(x) for x in levels if np.isfinite(x) and x > 0])
        if not levels:
            return []
        
        clusters = []
        current_cluster = [levels[0]]
        
        for level in levels[1:]:
            avg = sum(current_cluster) / len(current_cluster)
            if abs(level - avg) / max(avg, 1e-12) <= tolerance:
                current_cluster.append(level)
            else:
                clusters.append(sum(current_cluster) / len(current_cluster))
                current_cluster = [level]
        
        clusters.append(sum(current_cluster) / len(current_cluster))
        return clusters

    # ============================================================
    # HELPER METHODS (SAMA DENGAN SEBELUMNYA)
    # ============================================================
    
    def _calculate_returns(self, prices: np.ndarray) -> np.ndarray:
        if len(prices) < 2:
            return np.array([])
        previous = prices[:-1]
        valid = previous != 0
        returns = (prices[1:][valid] / previous[valid] - 1.0)
        return returns[np.isfinite(returns)]
    
    def _annualized_or_daily_volatility(self, returns: np.ndarray) -> float:
        if len(returns) < 10:
            return 0.02
        volatility = float(np.std(returns[-90:]))
        return float(np.clip(volatility, 0.002, 0.20))
    
    def _safe_model_call(self, model_name, func, current_price, model_status, warnings_list):
        try:
            prediction = func()
            if prediction is None:
                model_status[model_name] = "FAILED"
                warnings_list.append(f"{model_name}: returned None")
                return None
            prediction = np.asarray(prediction, dtype=float)
            if len(prediction) == 0:
                model_status[model_name] = "FAILED"
                warnings_list.append(f"{model_name}: empty prediction")
                return None
            return prediction
        except Exception as e:
            model_status[model_name] = "FAILED"
            warnings_list.append(f"{model_name}: {str(e)}")
            logger.warning(f"{model_name} failed: {e}")
            return None
    
    def _validate_prediction(self, prediction, current_price, model_name, warnings_list):
        prediction = np.asarray(prediction, dtype=float)
        prediction = prediction[np.isfinite(prediction)]
        if len(prediction) == 0:
            return None
        
        horizon = self.forecast_horizons["long"]
        if len(prediction) < horizon:
            prediction = np.pad(prediction, (0, horizon - len(prediction)), mode="edge")
        elif len(prediction) > horizon:
            prediction = prediction[:horizon]
        
        relative_moves = prediction / current_price - 1.0
        max_move = np.max(np.abs(relative_moves))
        
        if not np.isfinite(max_move) or max_move > self.max_reasonable_move:
            warnings_list.append(f"{model_name}: rejected abnormal forecast")
            return None
        
        if np.any(prediction <= 0):
            warnings_list.append(f"{model_name}: rejected non-positive price")
            return None
        
        for i in range(1, len(prediction)):
            step_return = prediction[i] / prediction[i-1] - 1.0
            if abs(step_return) > 0.10:
                warnings_list.append(f"{model_name}: rejected unstable path")
                return None
        
        return prediction
    
    # ============================================================
    # MODEL IMPLEMENTATIONS (SINGKAT)
    # ============================================================
    
    def _arima_forecast(self, prices: np.ndarray, horizon: int) -> np.ndarray:
        data = np.asarray(prices[-60:], dtype=float)
        if len(data) < 15:
            return self._simple_forecast(prices, horizon)
        y = data[2:]
        X = np.column_stack([data[1:-1], data[:-2], np.ones(len(data)-2)])
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        predictions = []
        last_values = [float(data[-2]), float(data[-1])]
        for _ in range(horizon):
            next_price = coef[0] * last_values[-1] + coef[1] * last_values[-2] + coef[2]
            if not np.isfinite(next_price):
                raise ValueError("AR forecast became non-finite")
            predictions.append(float(next_price))
            last_values = [last_values[-1], next_price]
        return np.asarray(predictions)
    
    def _linear_regression_forecast(self, prices: np.ndarray) -> np.ndarray:
        horizon = self.forecast_horizons["long"]
        if len(prices) < 30:
            return np.full(horizon, prices[-1])
        data = prices[-90:]
        y = np.log(np.maximum(data, 1e-12))
        X = np.arange(len(data)).reshape(-1, 1)
        model = LinearRegression().fit(X, y)
        future_X = np.arange(len(data), len(data) + horizon).reshape(-1, 1)
        return np.exp(model.predict(future_X))
    
    def _random_forest_forecast(self, prices: np.ndarray) -> np.ndarray:
        horizon = self.forecast_horizons["long"]
        if len(prices) < 80:
            return np.full(horizon, prices[-1])
        data = prices[-180:]
        lag = 10
        X = [data[i-lag:i] for i in range(lag, len(data))]
        y = data[lag:]
        X = np.asarray(X)
        y = np.asarray(y)
        if len(X) < 40:
            return np.full(horizon, prices[-1])
        rf = RandomForestRegressor(n_estimators=150, max_depth=8, min_samples_leaf=3, random_state=42, n_jobs=-1)
        rf.fit(X, y)
        last_features = data[-lag:].tolist()
        predictions = []
        for _ in range(horizon):
            features = np.asarray(last_features, dtype=float).reshape(1, -1)
            next_price = float(rf.predict(features)[0])
            predictions.append(next_price)
            last_features = last_features[1:] + [next_price]
        return np.asarray(predictions)
    
    def _pattern_recognition_forecast(self, prices: np.ndarray) -> np.ndarray:
        horizon = self.forecast_horizons["long"]
        window = self.pattern_window
        if len(prices) < self.min_pattern_history:
            return np.full(horizon, prices[-1])
        current = prices[-window:]
        current_returns = np.diff(current) / current[:-1]
        current_norm = (current_returns - np.mean(current_returns)) / (np.std(current_returns) + 1e-12)
        candidates = []
        max_start = len(prices) - window - horizon
        for start in range(0, max_start):
            hist_window = prices[start:start + window]
            future_window = prices[start + window:start + window + horizon]
            if len(future_window) < horizon:
                continue
            hist_returns = np.diff(hist_window) / hist_window[:-1]
            hist_norm = (hist_returns - np.mean(hist_returns)) / (np.std(hist_returns) + 1e-12)
            correlation = np.corrcoef(current_norm, hist_norm)[0, 1] if len(current_norm) > 1 else 0
            if not np.isfinite(correlation):
                correlation = 0
            similarity = max(0, (correlation + 1) / 2)
            if similarity < 0.60:
                continue
            future_returns = future_window / hist_window[-1] - 1.0
            candidates.append((similarity, future_returns))
        if not candidates:
            return np.full(horizon, prices[-1])
        candidates.sort(key=lambda x: x[0], reverse=True)
        top = candidates[:8]
        weighted_returns = []
        total_weight = 0.0
        for similarity, future_returns in top:
            weight = max(similarity - 0.50, 0.01)
            weighted_returns.append(future_returns * weight)
            total_weight += weight
        if total_weight <= 0:
            return np.full(horizon, prices[-1])
        avg_returns = np.sum(weighted_returns, axis=0) / total_weight
        predictions = []
        base = float(prices[-1])
        for future_return in avg_returns:
            future_return = np.clip(future_return, -0.05, 0.05)
            base *= (1.0 + future_return)
            predictions.append(base)
        return np.asarray(predictions)
    
    def _monte_carlo_forecast(self, prices: np.ndarray) -> np.ndarray:
        horizon = self.forecast_horizons["long"]
        returns = self._calculate_returns(prices)
        if len(returns) < 30:
            return np.full(horizon, prices[-1])
        returns = returns[-180:]
        mu = float(np.mean(returns))
        sigma = float(max(np.std(returns), 0.001))
        rng = np.random.default_rng(42)
        simulations = np.zeros((500, horizon))
        for sim in range(500):
            price = float(prices[-1])
            for step in range(horizon):
                random_return = np.clip(rng.normal(mu, sigma), -0.15, 0.15)
                price *= (1.0 + random_return)
                simulations[sim, step] = price
        return np.median(simulations, axis=0)
    
    def _sentiment_technical_forecast(self, prices, sentiment_result, technical_result) -> np.ndarray:
        horizon = self.forecast_horizons["long"]
        sentiment_score = float(getattr(sentiment_result, "overall_score", 0.0))
        technical_score = float(getattr(technical_result, "overall_score", 0.0))
        combined = np.clip(sentiment_score * 0.40 + technical_score * 0.60, -1.0, 1.0)
        last_price = float(prices[-1])
        momentum = (prices[-1] / prices[-6] - 1.0) if len(prices) >= 6 else 0.0
        daily_bias = combined * 0.003 + np.clip(momentum * 0.10, -0.003, 0.003)
        predictions = []
        price = last_price
        for i in range(horizon):
            decay = 1.0 / (1.0 + 0.20 * i)
            price *= (1.0 + daily_bias * decay)
            predictions.append(price)
        return np.asarray(predictions)
    
    def _simple_forecast(self, prices: np.ndarray, horizon: int) -> np.ndarray:
        if len(prices) == 0:
            return np.zeros(horizon)
        window = min(20, len(prices))
        recent = prices[-window:]
        weights = np.arange(1, window + 1, dtype=float)
        weights /= weights.sum()
        baseline = float(np.sum(recent * weights))
        last_price = float(prices[-1])
        predictions = []
        for i in range(horizon):
            alpha = min(0.10, 0.03 * (i + 1))
            predictions.append(last_price * (1 - alpha) + baseline * alpha)
        return np.asarray(predictions)
    
    # ============================================================
    # ENSEMBLE & WEIGHTING (SAMA)
    # ============================================================
    
    def _calculate_dynamic_weights(self, predictions, current_price, volatility, quality_score):
        raw_weights = {}
        for model_name, pred in predictions.items():
            base_weight = self.base_model_weights.get(model_name, 0.10)
            path_returns = pred / current_price - 1.0
            max_move = float(np.max(np.abs(path_returns)))
            stability = max(0.20, 1.0 - min(max_move / self.max_reasonable_move, 1.0))
            short_return = path_returns[0]
            vol_ratio = abs(short_return) / max(volatility, 0.001)
            if vol_ratio > 5.0:
                magnitude_factor = 0.25
            elif vol_ratio > 3.0:
                magnitude_factor = 0.50
            elif vol_ratio > 2.0:
                magnitude_factor = 0.75
            else:
                magnitude_factor = 1.0
            weight = base_weight * stability * magnitude_factor * (0.75 + 0.25 * quality_score)
            raw_weights[model_name] = max(weight, 0.001)
        total = sum(raw_weights.values())
        if total <= 0:
            count = max(len(raw_weights), 1)
            return {name: 1.0 / count for name in raw_weights}
        return {name: weight / total for name, weight in raw_weights.items()}
    
    def _ensemble_forecast(self, predictions, weights, current_price):
        horizon = self.forecast_horizons["long"]
        weighted_sum = np.zeros(horizon, dtype=float)
        total_weight = 0.0
        for model_name, pred in predictions.items():
            weight = weights.get(model_name, 0.0)
            if weight <= 0:
                continue
            pred = np.asarray(pred, dtype=float)
            if len(pred) != horizon:
                continue
            weighted_sum += pred * weight
            total_weight += weight
        if total_weight <= 0:
            return np.full(horizon, current_price)
        return self._repair_prediction_path(weighted_sum / total_weight, current_price)
    
    def _repair_prediction_path(self, prediction, current_price):
        prediction = np.asarray(prediction, dtype=float)
        prediction = np.where(np.isfinite(prediction), prediction, current_price)
        lower = current_price * (1.0 - self.max_reasonable_move)
        upper = current_price * (1.0 + self.max_reasonable_move)
        prediction = np.clip(prediction, lower, upper)
        prediction = np.maximum(prediction, current_price * 0.01)
        return prediction
    
    def _calculate_model_agreement(self, predictions, current_price):
        if len(predictions) < 2:
            return 0.35
        short_returns = []
        for pred in predictions.values():
            if len(pred) == 0:
                continue
            short_returns.append(pred[0] / current_price - 1.0)
        if len(short_returns) < 2:
            return 0.35
        short_returns = np.asarray(short_returns)
        dispersion = float(np.std(short_returns))
        agreement = 1.0 - dispersion / 0.02
        signs = np.sign(short_returns)
        direction_agreement = max(np.mean(signs > 0), np.mean(signs < 0), np.mean(signs == 0))
        return float(np.clip(agreement * 0.60 + direction_agreement * 0.40, 0.0, 1.0))
    
    # ============================================================
    # TREND, PROBABILITY, SCENARIOS (SAMA)
    # ============================================================
    
    def _analyze_trend(self, prices: np.ndarray) -> Tuple[str, float]:
        if len(prices) < 50:
            return "CONSOLIDATING", 0.0
        ma20 = float(np.mean(prices[-20:]))
        ma50 = float(np.mean(prices[-50:]))
        ma100 = float(np.mean(prices[-100:])) if len(prices) >= 100 else ma50
        current_price = float(prices[-1])
        if current_price > ma20 > ma50 > ma100:
            trend = "BULLISH"
        elif current_price < ma20 < ma50 < ma100:
            trend = "BEARISH"
        else:
            trend = "CONSOLIDATING"
        if trend == "BULLISH":
            strength = abs(current_price - ma50) / ma50 * 3 + abs(ma20 - ma50) / ma50 * 2
        elif trend == "BEARISH":
            strength = abs(ma50 - current_price) / ma50 * 3 + abs(ma50 - ma20) / ma50 * 2
        else:
            recent = prices[-20:]
            range_pct = (np.max(recent) - np.min(recent)) / np.mean(recent)
            strength = max(0.0, 1.0 - min(range_pct / 0.08, 1.0))
        return trend, float(np.clip(strength, 0.0, 1.0))
    
    def _predict_next_move(self, prices, ensemble_pred, volatility, model_agreement):
        if len(ensemble_pred) == 0:
            return {"UP": 0.33, "DOWN": 0.33, "SIDEWAYS": 0.34}
        current_price = float(prices[-1])
        predicted_return = ensemble_pred[0] / current_price - 1.0
        historical_momentum = prices[-1] / prices[-6] - 1.0 if len(prices) >= 6 else 0.0
        vol = max(volatility, 0.001)
        signal = (predicted_return / vol) * 0.65 + (historical_momentum / vol) * 0.35
        directional_strength = abs(signal) * model_agreement
        if abs(signal) < 0.35:
            up, down, sideways = 0.25, 0.25, 0.50
        elif signal > 0:
            directional = min(0.70, 0.40 + directional_strength * 0.12)
            up = directional
            sideways = max(0.10, 0.40 - directional_strength * 0.08)
            down = 1.0 - up - sideways
        else:
            directional = min(0.70, 0.40 + directional_strength * 0.12)
            down = directional
            sideways = max(0.10, 0.40 - directional_strength * 0.08)
            up = 1.0 - down - sideways
        probs = {"UP": max(0.0, float(up)), "DOWN": max(0.0, float(down)), "SIDEWAYS": max(0.0, float(sideways))}
        total = sum(probs.values())
        return {k: v / total for k, v in probs.items()}
    
    def _generate_scenarios(self, current_price, ensemble_pred, predictions, volatility, model_agreement, trend):
        horizon = len(ensemble_pred)
        if horizon == 0:
            ensemble_pred = np.full(self.forecast_horizons["long"], current_price)
            horizon = len(ensemble_pred)
        if predictions:
            matrix = np.vstack([pred[:horizon] for pred in predictions.values()])
            dispersion = np.std(matrix, axis=0)
        else:
            dispersion = np.full(horizon, current_price * volatility)
        time_scale = np.sqrt(np.arange(1, horizon + 1))
        total_buffer = current_price * volatility * 1.5 * time_scale + dispersion * 0.50
        bullish = np.clip(ensemble_pred + total_buffer, current_price * 0.85, current_price * 1.15)
        bearish = np.clip(ensemble_pred - total_buffer, current_price * 0.85, current_price * 1.15)
        most_likely = ensemble_pred
        if trend == "BULLISH":
            bullish_prob = np.clip(0.30 + model_agreement * 0.20, 0.10, 0.45)
            bearish_prob = np.clip(0.20 - model_agreement * 0.05, 0.10, 0.45)
        elif trend == "BEARISH":
            bearish_prob = np.clip(0.30 + model_agreement * 0.20, 0.10, 0.45)
            bullish_prob = np.clip(0.20 - model_agreement * 0.05, 0.10, 0.45)
        else:
            bullish_prob, bearish_prob = 0.25, 0.25
        most_likely_prob = max(0.10, 1.0 - bullish_prob - bearish_prob)
        total = bullish_prob + bearish_prob + most_likely_prob
        return {
            "bullish": bullish, "bearish": bearish, "most_likely": most_likely,
            "bullish_prob": bullish_prob / total, "bearish_prob": bearish_prob / total,
            "most_likely_prob": most_likely_prob / total
        }
    
    # ============================================================
    # PRICE PREDICTION, SCORE, ACTION (SAMA)
    # ============================================================
    
    def _create_price_prediction(self, ensemble_pred, horizon, current_price, volatility, model_agreement):
        days_map = {"short": 2, "medium": 5, "long": 7}
        days = days_map.get(horizon, 2)
        index = min(days - 1, len(ensemble_pred) - 1)
        predicted_price = float(ensemble_pred[index])
        predicted_change = predicted_price / current_price - 1.0
        mag_vs_vol = abs(predicted_change) / max(volatility * np.sqrt(days), 0.001)
        if mag_vs_vol <= 1.0:
            plausibility = 0.85
        elif mag_vs_vol <= 2.0:
            plausibility = 0.70
        elif mag_vs_vol <= 3.0:
            plausibility = 0.50
        else:
            plausibility = 0.30
        confidence = float(np.clip(0.45 * model_agreement + 0.35 * plausibility + 0.14, 0.35, 0.90))
        interval_width = current_price * volatility * np.sqrt(days) * (1.20 - 0.50 * model_agreement)
        lower = max(0.0, predicted_price - interval_width)
        upper = predicted_price + interval_width
        return PricePrediction(
            timestamp=datetime.now(timezone.utc) + timedelta(days=days),
            predicted_price=predicted_price,
            confidence_interval_lower=float(lower),
            confidence_interval_upper=float(upper),
            confidence=confidence,
            horizon=horizon.upper(),
            predicted_change_percent=float(predicted_change * 100)
        )
    
    def _calculate_forecast_score(self, current_price, short_pred, trend, trend_strength, probs, model_agreement, vol):
        predicted_return = short_pred.predicted_price / current_price - 1.0
        vol = max(vol, 0.001)
        magnitude_score = float(np.tanh(predicted_return / vol))
        probability_score = probs["UP"] - probs["DOWN"]
        trend_score = trend_strength if trend == "BULLISH" else (-trend_strength if trend == "BEARISH" else 0.0)
        score = magnitude_score * 0.45 + probability_score * 0.30 + trend_score * 0.15 + (probability_score * model_agreement) * 0.10
        return float(np.clip(score, -1.0, 1.0))
    
    def _translate_forecast_to_action(self, score, trend, trend_strength, probs, model_agreement, short_pred, vol):
        predicted_move = abs(short_pred.predicted_change_percent) / 100.0
        vol = max(vol, 0.001)
        movement_ratio = predicted_move / vol
        up, down = probs["UP"], probs["DOWN"]
        if score >= 0.65 and up >= 0.62 and model_agreement >= 0.60 and movement_ratio >= 0.75 and trend == "BULLISH":
            return "STRONG_BUY"
        if score >= 0.25 and up >= 0.52 and model_agreement >= 0.45 and movement_ratio >= 0.35:
            return "BUY"
        if score <= -0.65 and down >= 0.62 and model_agreement >= 0.60 and movement_ratio >= 0.75 and trend == "BEARISH":
            return "STRONG_SELL"
        if score <= -0.25 and down >= 0.52 and model_agreement >= 0.45 and movement_ratio >= 0.35:
            return "SELL"
        return "HOLD"
    
    def _generate_summary(self, symbol, current_price, trend, trend_strength, short_pred, medium_pred, long_pred, probs, agreement, score, action):
        name = symbol.replace("-USD", "").replace("-USDT", "")
        summary = (f"Forecast {name}: harga saat ini ${current_price:.2f}. "
                  f"Trend {trend} dengan strength {trend_strength:.1%}. "
                  f"Forecast SHORT ${short_pred.predicted_price:.2f} ({short_pred.predicted_change_percent:+.2f}%). "
                  f"MEDIUM {medium_pred.predicted_change_percent:+.2f}%, LONG {long_pred.predicted_change_percent:+.2f}%. "
                  f"Probability UP={probs['UP']:.1%}, DOWN={probs['DOWN']:.1%}, SIDEWAYS={probs['SIDEWAYS']:.1%}. "
                  f"Model agreement {agreement:.1%}. Forecast score {score:+.3f}. Forecast action {action}.")
        return summary
    
    def _generate_recommendations(self, trend, trend_strength, action, score, short_pred, support, resistance, probs, agreement, vol):
        recs = []
        if trend == "BULLISH":
            recs.append("Trend bullish; tunggu confirmation sebelum entry agresif.")
        elif trend == "BEARISH":
            recs.append("Trend bearish; hindari entry agresif tanpa confirmation.")
        else:
            recs.append("Trend masih konsolidasi; wait and see lebih aman.")
        if action == "STRONG_BUY":
            recs.append("Forecast bullish kuat dengan confirmation antar-model.")
        elif action == "BUY":
            recs.append("Forecast memiliki bullish bias, tetapi tetap membutuhkan confirmation.")
        elif action == "STRONG_SELL":
            recs.append("Forecast bearish kuat dengan confirmation antar-model.")
        elif action == "SELL":
            recs.append("Forecast memiliki bearish bias, tetapi tetap membutuhkan confirmation.")
        else:
            recs.append("Belum ada directional edge yang cukup kuat untuk trade.")
        highest = max(probs, key=probs.get)
        if probs[highest] >= 0.55:
            recs.append(f"Probability {highest} {probs[highest]:.1%}.")
        else:
            recs.append("Tidak ada probabilitas arah yang cukup dominan.")
        if support:
            recs.append(f"Support terdekat: ${support[0]:.2f}.")
        if resistance:
            recs.append(f"Resistance terdekat: ${resistance[0]:.2f}.")
        if agreement < 0.45:
            recs.append("Model agreement rendah; forecast perlu dianggap low confidence.")
        return recs[:6]
    
    def _calculate_expected_range(self, predictions, current_price, volatility):
        if not predictions:
            return current_price * 1.05, current_price * 0.95
        final_prices = []
        for pred in predictions.values():
            if len(pred):
                final_prices.append(float(pred[-1]))
        if not final_prices:
            return current_price * 1.05, current_price * 0.95
        final_prices = np.asarray(final_prices)
        low_model = float(np.percentile(final_prices, 20))
        high_model = float(np.percentile(final_prices, 80))
        vol_buffer = current_price * volatility * 1.25
        expected_low = max(0.0, min(low_model - vol_buffer, current_price * 0.85))
        expected_high = min(high_model + vol_buffer, current_price * 1.15)
        return expected_high, expected_low
    
    # ============================================================
    # DEFAULT FORECAST
    # ============================================================
    
    def _get_default_forecast(self, symbol, current_price=0.0, reason="No forecast available", warnings_list=None):
        if warnings_list is None:
            warnings_list = []
        if reason not in warnings_list:
            warnings_list.append(reason)
        now = datetime.now(timezone.utc)
        if current_price <= 0:
            current_price = 0.0
        
        def default_pred(horizon, days):
            return PricePrediction(
                timestamp=now + timedelta(days=days),
                predicted_price=float(current_price),
                confidence_interval_lower=float(current_price),
                confidence_interval_upper=float(current_price),
                confidence=0.0,
                horizon=horizon,
                predicted_change_percent=0.0
            )
        
        return ForecastResult(
            symbol=symbol,
            timestamp=now,
            current_price=float(current_price),
            short_term=default_pred("SHORT", 2),
            medium_term=default_pred("MEDIUM", 5),
            long_term=default_pred("LONG", 7),
            bullish_path=[float(current_price)] * 7,
            bearish_path=[float(current_price)] * 7,
            most_likely_path=[float(current_price)] * 7,
            scenarios={
                "bullish": {"path": [float(current_price)] * 7, "probability": 0.25},
                "bearish": {"path": [float(current_price)] * 7, "probability": 0.25},
                "most_likely": {"path": [float(current_price)] * 7, "probability": 0.50}
            },
            primary_trend="CONSOLIDATING",
            trend_strength=0.0,
            next_move_probability={"UP": 0.33, "DOWN": 0.33, "SIDEWAYS": 0.34},
            expected_high=float(current_price),
            expected_low=float(current_price),
            expected_range={"high": float(current_price), "low": float(current_price), "range_percent": 0.0},
            key_resistance=[],
            key_support=[],
            summary=f"Forecast unavailable for {symbol}: {reason}",
            recommendations=["Wait for valid historical data."],
            model_predictions={},
            model_weights={},
            model_status={},
            data_quality={"observations": 0.0, "return_volatility": 0.0, "missing_ratio": 1.0, "quality_score": 0.0},
            model_agreement=0.0,
            forecast_score=0.0,
            forecast_action="HOLD",
            warnings=warnings_list
        )
