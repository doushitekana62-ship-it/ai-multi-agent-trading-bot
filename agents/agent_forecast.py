"""
Forecast Agent v4
=================

AI Multi-Agent Trading Bot
Agent 5: Forecasting Pergerakan Harga

Tujuan:
- Menghasilkan forecast 1-7 hari
- Menggabungkan beberapa model
- Melakukan validasi output setiap model
- Mencegah model dengan skala rusak menghancurkan ensemble
- Mengukur model agreement
- Mengukur data quality
- Menghasilkan probabilitas UP/DOWN/SIDEWAYS
- Menghasilkan bullish / bearish / most-likely scenarios
- Menghasilkan forecast confidence yang lebih realistis
- Tidak menghasilkan STRONG_BUY / STRONG_SELL hanya karena satu model anomali

PENTING:
Forecast Agent bukan eksekutor trade.
Keputusan akhir tetap berada di Decision Agent / Risk Engine / Execution Gate.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

from scipy.signal import find_peaks
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression

warnings.filterwarnings("ignore")

logger = logging.getLogger(__name__)


# ============================================================
# CONSTANTS
# ============================================================

EPSILON = 1e-12

HORIZONS = {
    "short": 2,
    "medium": 5,
    "long": 7,
}

DEFAULT_MODEL_WEIGHTS = {
    "arima": 0.20,
    "linear_regression": 0.15,
    "random_forest": 0.20,
    "pattern_recognition": 0.15,
    "monte_carlo": 0.15,
    "sentiment_technical": 0.15,
}

DEFAULT_CONFIDENCE = {
    "short": 0.60,
    "medium": 0.50,
    "long": 0.40,
}


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class PricePrediction:
    """
    Prediksi harga pada horizon tertentu.
    """

    timestamp: datetime
    predicted_price: float
    confidence_interval_lower: float
    confidence_interval_upper: float
    confidence: float
    horizon: str
    predicted_change_percent: float = 0.0


@dataclass
class ForecastResult:
    """
    Hasil lengkap Forecast Agent.
    """

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

    # ========================================================
    # EXTRA METADATA
    # ========================================================

    model_predictions: Dict[str, List[float]]
    model_weights: Dict[str, float]
    model_status: Dict[str, str]

    data_quality: Dict[str, float]

    model_agreement: float = 0.0
    forecast_score: float = 0.0
    forecast_action: str = "HOLD"

    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


# ============================================================
# FORECAST AGENT
# ============================================================

class ForecastAgent:
    """
    Forecast Agent v4.

    Arsitektur:

        Historical Data
               |
               +---- AR model
               |
               +---- Linear Regression
               |
               +---- Random Forest
               |
               +---- Pattern Recognition
               |
               +---- Monte Carlo
               |
               +---- Sentiment + Technical
               |
               v
        Validation Layer
               |
               v
        Ensemble Engine
               |
               +---- Model Agreement
               +---- Trend
               +---- Probability
               +---- Scenarios
               +---- Confidence
               |
               v
        ForecastResult
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):

        self.config = config or {}

        self.forecast_horizons = {
            **HORIZONS,
            **self.config.get("forecast_horizons", {}),
        }

        self.model_weights = {
            **DEFAULT_MODEL_WEIGHTS,
            **self.config.get("model_weights", {}),
        }

        self.confidence_levels = {
            **DEFAULT_CONFIDENCE,
            **self.config.get("confidence_levels", {}),
        }

        self.cache: Dict[str, Tuple[ForecastResult, datetime]] = {}

        self.cache_duration = timedelta(
            minutes=self.config.get("cache_minutes", 30)
        )

        # Model configuration
        self.rf_estimators = int(
            self.config.get("rf_estimators", 100)
        )

        self.rf_max_depth = int(
            self.config.get("rf_max_depth", 8)
        )

        self.mc_simulations = int(
            self.config.get("mc_simulations", 500)
        )

        # Pattern settings
        self.pattern_window = int(
            self.config.get("pattern_window", 30)
        )

        self.pattern_search_window = int(
            self.config.get("pattern_search_window", 240)
        )

        # Signal thresholds
        self.buy_threshold = float(
            self.config.get("buy_threshold", 0.025)
        )

        self.sell_threshold = float(
            self.config.get("sell_threshold", -0.025)
        )

        self.strong_buy_threshold = float(
            self.config.get("strong_buy_threshold", 0.05)
        )

        self.strong_sell_threshold = float(
            self.config.get("strong_sell_threshold", -0.05)
        )

        self.min_model_agreement = float(
            self.config.get("min_model_agreement", 0.55)
        )

        self.min_forecast_confidence = float(
            self.config.get("min_forecast_confidence", 0.55)
        )

        logger.info(
            "Forecast Agent initialized successfully"
        )

    # ========================================================
    # PUBLIC API
    # ========================================================

    def analyze(
        self,
        symbol: str,
        sentiment_result: Any = None,
        technical_result: Any = None,
        market_data: Optional[Dict[str, Any]] = None,
    ) -> ForecastResult:

        logger.info(
            "Generating forecast for %s",
            symbol,
        )

        cache_key = self._cache_key(symbol)

        cached = self._get_cached(cache_key)

        if cached is not None:
            logger.info(
                "Using cached forecast for %s",
                symbol,
            )
            return cached

        warnings_list: List[str] = []

        try:

            df = self._prepare_market_data(
                symbol=symbol,
                market_data=market_data,
            )

            if df is None or len(df) < 60:

                warnings_list.append(
                    "Insufficient historical data"
                )

                return self._get_default_forecast(
                    symbol=symbol,
                    current_price=self._extract_current_price(
                        market_data
                    ),
                    warnings=warnings_list,
                )

            current_price = float(
                df["Close"].iloc[-1]
            )

            if current_price <= 0:
                raise ValueError(
                    "Current price is invalid"
                )

            prices = (
                df["Close"]
                .astype(float)
                .to_numpy()
            )

            # ------------------------------------------------
            # DATA QUALITY
            # ------------------------------------------------

            data_quality = self._calculate_data_quality(
                df
            )

            if data_quality["quality_score"] < 0.70:
                warnings_list.append(
                    "Historical data quality is below recommended level"
                )

            # ------------------------------------------------
            # MODEL PREDICTIONS
            # ------------------------------------------------

            predictions: Dict[str, np.ndarray] = {}

            model_status: Dict[str, str] = {}

            # AR
            predictions["arima"] = self._safe_model_call(
                "arima",
                lambda: self._arima_forecast(
                    prices,
                    self.forecast_horizons["long"],
                ),
                prices,
                model_status,
            )

            # Linear regression
            predictions["linear_regression"] = self._safe_model_call(
                "linear_regression",
                lambda: self._linear_regression_forecast(
                    prices
                ),
                prices,
                model_status,
            )

            # Random forest
            predictions["random_forest"] = self._safe_model_call(
                "random_forest",
                lambda: self._random_forest_forecast(
                    df
                ),
                prices,
                model_status,
            )

            # Pattern recognition
            predictions["pattern_recognition"] = self._safe_model_call(
                "pattern_recognition",
                lambda: self._pattern_recognition_forecast(
                    prices
                ),
                prices,
                model_status,
            )

            # Monte Carlo
            predictions["monte_carlo"] = self._safe_model_call(
                "monte_carlo",
                lambda: self._monte_carlo_forecast(
                    prices
                ),
                prices,
                model_status,
            )

            # Sentiment + Technical
            if (
                sentiment_result is not None
                and technical_result is not None
            ):

                predictions["sentiment_technical"] = (
                    self._safe_model_call(
                        "sentiment_technical",
                        lambda: self._sentiment_technical_forecast(
                            prices,
                            sentiment_result,
                            technical_result,
                        ),
                        prices,
                        model_status,
                    )
                )

            # ------------------------------------------------
            # VALIDATE MODEL OUTPUTS
            # ------------------------------------------------

            predictions, validation_warnings = (
                self._validate_predictions(
                    predictions,
                    current_price,
                )
            )

            warnings_list.extend(
                validation_warnings
            )

            # ------------------------------------------------
            # ENSEMBLE
            # ------------------------------------------------

            ensemble_prediction, effective_weights = (
                self._ensemble_forecast(
                    predictions,
                    current_price,
                )
            )

            # ------------------------------------------------
            # MODEL AGREEMENT
            # ------------------------------------------------

            model_agreement = (
                self._calculate_model_agreement(
                    predictions,
                    current_price,
                )
            )

            # ------------------------------------------------
            # TREND
            # ------------------------------------------------

            primary_trend, trend_strength = (
                self._analyze_trend(
                    prices
                )
            )

            # ------------------------------------------------
            # NEXT MOVE PROBABILITY
            # ------------------------------------------------

            next_move_probability = (
                self._predict_next_move(
                    prices,
                    ensemble_prediction,
                    model_agreement,
                )
            )

            # ------------------------------------------------
            # SCENARIOS
            # ------------------------------------------------

            scenarios = self._generate_scenarios(
                current_price=current_price,
                ensemble_pred=ensemble_prediction,
                predictions=predictions,
                model_agreement=model_agreement,
            )

            # ------------------------------------------------
            # PRICE PREDICTIONS
            # ------------------------------------------------

            short_pred = self._create_price_prediction(
                ensemble_prediction,
                "short",
                current_price,
                model_agreement,
                data_quality["quality_score"],
            )

            medium_pred = self._create_price_prediction(
                ensemble_prediction,
                "medium",
                current_price,
                model_agreement,
                data_quality["quality_score"],
            )

            long_pred = self._create_price_prediction(
                ensemble_prediction,
                "long",
                current_price,
                model_agreement,
                data_quality["quality_score"],
            )

            # ------------------------------------------------
            # KEY LEVELS
            # ------------------------------------------------

            key_support, key_resistance = (
                self._find_key_levels(
                    df,
                    current_price,
                )
            )

            # ------------------------------------------------
            # EXPECTED RANGE
            # ------------------------------------------------

            expected_high, expected_low = (
                self._calculate_expected_range(
                    current_price=current_price,
                    predictions=predictions,
                    ensemble_prediction=ensemble_prediction,
                )
            )

            # ------------------------------------------------
            # FORECAST SCORE
            # ------------------------------------------------

            forecast_score = (
                self._calculate_forecast_score(
                    current_price=current_price,
                    short_prediction=short_pred,
                    trend=primary_trend,
                    trend_strength=trend_strength,
                    model_agreement=model_agreement,
                    data_quality=data_quality["quality_score"],
                    probabilities=next_move_probability,
                )
            )

            forecast_action = (
                self._forecast_action(
                    forecast_score=forecast_score,
                    confidence=short_pred.confidence,
                    model_agreement=model_agreement,
                )
            )

            # ------------------------------------------------
            # SUMMARY
            # ------------------------------------------------

            summary = self._generate_summary(
                symbol=symbol,
                current_price=current_price,
                trend=primary_trend,
                trend_strength=trend_strength,
                short_pred=short_pred,
                model_agreement=model_agreement,
                data_quality=data_quality["quality_score"],
                next_move_probability=next_move_probability,
            )

            # ------------------------------------------------
            # RECOMMENDATIONS
            # ------------------------------------------------

            recommendations = (
                self._generate_recommendations(
                    current_price=current_price,
                    trend=primary_trend,
                    trend_strength=trend_strength,
                    short_pred=short_pred,
                    model_agreement=model_agreement,
                    support=key_support,
                    resistance=key_resistance,
                    forecast_action=forecast_action,
                    probabilities=next_move_probability,
                )
            )

            # ------------------------------------------------
            # MODEL OUTPUT SERIALIZATION
            # ------------------------------------------------

            model_predictions_serialized = {
                name: self._safe_float_list(pred)
                for name, pred in predictions.items()
            }

            # ------------------------------------------------
            # BUILD RESULT
            # ------------------------------------------------

            result = ForecastResult(
                symbol=symbol,
                timestamp=datetime.now(timezone.utc),
                current_price=current_price,

                short_term=short_pred,
                medium_term=medium_pred,
                long_term=long_pred,

                bullish_path=self._safe_float_list(
                    scenarios["bullish"]
                ),

                bearish_path=self._safe_float_list(
                    scenarios["bearish"]
                ),

                most_likely_path=self._safe_float_list(
                    scenarios["most_likely"]
                ),

                scenarios={
                    "bullish": {
                        "path": self._safe_float_list(
                            scenarios["bullish"]
                        ),
                        "probability": float(
                            scenarios["bullish_prob"]
                        ),
                    },
                    "bearish": {
                        "path": self._safe_float_list(
                            scenarios["bearish"]
                        ),
                        "probability": float(
                            scenarios["bearish_prob"]
                        ),
                    },
                    "most_likely": {
                        "path": self._safe_float_list(
                            scenarios["most_likely"]
                        ),
                        "probability": float(
                            scenarios["most_likely_prob"]
                        ),
                    },
                },

                primary_trend=primary_trend,
                trend_strength=float(
                    trend_strength
                ),

                next_move_probability={
                    key: float(value)
                    for key, value
                    in next_move_probability.items()
                },

                expected_high=float(
                    expected_high
                ),

                expected_low=float(
                    expected_low
                ),

                expected_range={
                    "high": float(expected_high),
                    "low": float(expected_low),
                    "range_percent": float(
                        (
                            expected_high - expected_low
                        )
                        / current_price
                        * 100
                    ),
                },

                key_resistance=[
                    float(x)
                    for x in key_resistance
                ],

                key_support=[
                    float(x)
                    for x in key_support
                ],

                summary=summary,

                recommendations=recommendations,

                model_predictions=model_predictions_serialized,

                model_weights={
                    key: float(value)
                    for key, value
                    in effective_weights.items()
                },

                model_status=model_status,

                data_quality={
                    key: float(value)
                    for key, value
                    in data_quality.items()
                    if isinstance(value, (int, float, np.number))
                },

                model_agreement=float(
                    model_agreement
                ),

                forecast_score=float(
                    forecast_score
                ),

                forecast_action=forecast_action,

                warnings=warnings_list,
            )

            self._store_cache(
                cache_key,
                result,
            )

            return result

        except Exception as exc:

            logger.exception(
                "Error generating forecast for %s",
                symbol,
            )

            warnings_list.append(
                f"Forecast engine error: {str(exc)}"
            )

            return self._get_default_forecast(
                symbol=symbol,
                current_price=self._extract_current_price(
                    market_data
                ),
                warnings=warnings_list,
            )

    # ========================================================
    # DATA
    # ========================================================

    def _prepare_market_data(
        self,
        symbol: str,
        market_data: Optional[Dict[str, Any]],
    ) -> Optional[pd.DataFrame]:

        # ----------------------------------------------------
        # Try supplied market data first
        # ----------------------------------------------------

        if isinstance(market_data, dict):

            for key in (
                "df",
                "dataframe",
                "historical",
                "history",
            ):

                candidate = market_data.get(key)

                if isinstance(candidate, pd.DataFrame):

                    prepared = self._normalize_dataframe(
                        candidate
                    )

                    if prepared is not None:
                        return prepared

        # ----------------------------------------------------
        # Yahoo Finance
        # ----------------------------------------------------

        try:

            ticker = yf.Ticker(symbol)

            df = ticker.history(
                period="2y",
                interval="1d",
                auto_adjust=False,
            )

            return self._normalize_dataframe(
                df
            )

        except Exception as exc:

            logger.error(
                "Error fetching market data for %s: %s",
                symbol,
                exc,
            )

            return None

    def _normalize_dataframe(
        self,
        df: Optional[pd.DataFrame],
    ) -> Optional[pd.DataFrame]:

        if df is None or df.empty:
            return None

        data = df.copy()

        # Flatten MultiIndex columns
        if isinstance(
            data.columns,
            pd.MultiIndex,
        ):

            data.columns = [
                str(col[0])
                for col in data.columns
            ]

        required = [
            "Close",
        ]

        for column in required:

            if column not in data.columns:
                return None

        for column in (
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
        ):

            if column in data.columns:

                data[column] = pd.to_numeric(
                    data[column],
                    errors="coerce",
                )

        data = data.replace(
            [np.inf, -np.inf],
            np.nan,
        )

        data = data.dropna(
            subset=["Close"]
        )

        data = data[data["Close"] > 0]

        if data.empty:
            return None

        return data

    def _extract_current_price(
        self,
        market_data: Optional[Dict[str, Any]],
    ) -> float:

        if not isinstance(market_data, dict):
            return 0.0

        for key in (
            "current_price",
            "price",
            "last_price",
        ):

            value = market_data.get(key)

            try:

                value = float(value)

                if value > 0:
                    return value

            except Exception:
                pass

        return 0.0

    # ========================================================
    # MODEL SAFETY
    # ========================================================

    def _safe_model_call(
        self,
        model_name: str,
        function,
        prices: np.ndarray,
        model_status: Dict[str, str],
    ) -> np.ndarray:

        try:

            result = function()

            result = self._sanitize_prediction(
                result,
                prices[-1],
            )

            model_status[model_name] = "OK"

            return result

        except Exception as exc:

            logger.warning(
                "Model %s failed: %s",
                model_name,
                exc,
            )

            model_status[model_name] = (
                f"FALLBACK: {str(exc)[:80]}"
            )

            return np.full(
                self.forecast_horizons["long"],
                prices[-1],
                dtype=float,
            )

    def _sanitize_prediction(
        self,
        prediction: Any,
        current_price: float,
    ) -> np.ndarray:

        horizon = self.forecast_horizons["long"]

        arr = np.asarray(
            prediction,
            dtype=np.float64,
        ).reshape(-1)

        if arr.size == 0:
            raise ValueError(
                "Empty prediction"
            )

        arr = arr[
            np.isfinite(arr)
        ]

        if arr.size == 0:
            raise ValueError(
                "Prediction contains no finite values"
            )

        # Resize to exactly horizon
        if arr.size < horizon:

            arr = np.pad(
                arr,
                (
                    0,
                    horizon - arr.size,
                ),
                mode="edge",
            )

        elif arr.size > horizon:

            arr = arr[:horizon]

        # No negative prices
        arr = np.maximum(
            arr,
            current_price * 0.10,
        )

        # ----------------------------------------------------
        # CRITICAL OUTLIER PROTECTION
        #
        # A daily model shouldn't suddenly say BTC goes
        # from 62k to 156 dollars.
        # ----------------------------------------------------

        max_deviation = float(
            self.config.get(
                "max_prediction_deviation",
                0.35,
            )
        )

        lower_bound = (
            current_price
            * (1.0 - max_deviation)
        )

        upper_bound = (
            current_price
            * (1.0 + max_deviation)
        )

        arr = np.clip(
            arr,
            lower_bound,
            upper_bound,
        )

        return arr.astype(float)

    def _validate_predictions(
        self,
        predictions: Dict[str, np.ndarray],
        current_price: float,
    ) -> Tuple[
        Dict[str, np.ndarray],
        List[str],
    ]:

        warnings_list = []

        valid = {}

        horizon = self.forecast_horizons["long"]

        for name, prediction in predictions.items():

            try:

                arr = self._sanitize_prediction(
                    prediction,
                    current_price,
                )

                if len(arr) != horizon:

                    warnings_list.append(
                        f"{name}: invalid horizon length"
                    )

                    continue

                # Check total deviation
                deviation = abs(
                    arr[-1] / current_price - 1.0
                )

                if deviation > 0.35:

                    warnings_list.append(
                        f"{name}: extreme deviation rejected"
                    )

                    continue

                valid[name] = arr

            except Exception as exc:

                warnings_list.append(
                    f"{name}: validation failed - {exc}"
                )

        if not valid:

            valid["fallback"] = np.full(
                horizon,
                current_price,
            )

            warnings_list.append(
                "All forecasting models failed validation"
            )

        return valid, warnings_list

    # ========================================================
    # AR MODEL
    # ========================================================

    def _arima_forecast(
        self,
        prices: np.ndarray,
        horizon: int,
    ) -> np.ndarray:

        prices = np.asarray(
            prices,
            dtype=float,
        )

        if len(prices) < 30:
            return np.full(
                horizon,
                prices[-1],
            )

        data = prices[-60:]

        # Work with log returns instead of raw prices.
        # This improves numerical stability.
        returns = np.diff(
            np.log(data)
        )

        if len(returns) < 10:

            return self._simple_moving_average_forecast(
                prices,
                horizon,
            )

        # AR(2) on returns
        lag = 2

        y = returns[lag:]

        X = np.column_stack(
            [
                returns[lag - 1:-1],
                returns[lag - 2:-2],
                np.ones(len(y)),
            ]
        )

        coef, _, _, _ = np.linalg.lstsq(
            X,
            y,
            rcond=None,
        )

        future_returns = []

        history = list(
            returns[-2:]
        )

        for _ in range(horizon):

            next_return = (
                coef[0] * history[-1]
                + coef[1] * history[-2]
                + coef[2]
            )

            # Prevent explosive AR predictions
            next_return = float(
                np.clip(
                    next_return,
                    -0.10,
                    0.10,
                )
            )

            future_returns.append(
                next_return
            )

            history.append(
                next_return
            )

        last_price = prices[-1]

        predictions = []

        price = last_price

        for ret in future_returns:

            price *= np.exp(ret)

            predictions.append(
                price
            )

        return np.asarray(
            predictions,
            dtype=float,
        )

    def _simple_moving_average_forecast(
        self,
        prices: np.ndarray,
        horizon: int,
    ) -> np.ndarray:

        if len(prices) == 0:
            return np.zeros(
                horizon,
                dtype=float,
            )

        prices = np.asarray(
            prices,
            dtype=float,
        )

        window = min(
            20,
            len(prices),
        )

        recent = prices[-window:]

        weights = np.arange(
            1,
            window + 1,
            dtype=float,
        )

        weights /= weights.sum()

        baseline = float(
            np.sum(
                recent * weights
            )
        )

        if len(prices) >= 6:

            momentum = (
                prices[-1]
                / prices[-6]
                - 1.0
            )

        else:

            momentum = 0.0

        # Damp momentum heavily
        daily_drift = (
            momentum / 5.0
        )

        daily_drift = float(
            np.clip(
                daily_drift,
                -0.02,
                0.02,
            )
        )

        predictions = []

        price = baseline

        for i in range(horizon):

            price *= (
                1.0
                + daily_drift
                * (0.8 ** i)
            )

            predictions.append(
                price
            )

        return np.asarray(
            predictions,
            dtype=float,
        )

    # ========================================================
    # LINEAR REGRESSION
    # ========================================================

    def _linear_regression_forecast(
        self,
        prices: np.ndarray,
    ) -> np.ndarray:

        prices = np.asarray(
            prices,
            dtype=float,
        )

        horizon = self.forecast_horizons["long"]

        if len(prices) < 30:

            return np.full(
                horizon,
                prices[-1],
            )

        # Use recent window
        window = min(
            90,
            len(prices),
        )

        data = prices[-window:]

        # Regression on log prices
        log_prices = np.log(
            np.maximum(
                data,
                EPSILON,
            )
        )

        X = np.arange(
            len(data),
            dtype=float,
        ).reshape(-1, 1)

        model = LinearRegression()

        model.fit(
            X,
            log_prices,
        )

        future_X = np.arange(
            len(data),
            len(data) + horizon,
            dtype=float,
        ).reshape(-1, 1)

        predictions = np.exp(
            model.predict(
                future_X
            )
        )

        return predictions.astype(
            float
        )

    # ========================================================
    # RANDOM FOREST
    # ========================================================

    def _random_forest_forecast(
        self,
        df: pd.DataFrame,
    ) -> np.ndarray:

        prices = (
            df["Close"]
            .astype(float)
            .to_numpy()
        )

        horizon = self.forecast_horizons["long"]

        if len(prices) < 80:

            return self._linear_regression_forecast(
                prices
            )

        data = prices[-250:]

        # Features:
        # lagged log returns + momentum
        X = []
        y = []

        lookback = 12

        returns = np.diff(
            np.log(
                np.maximum(
                    data,
                    EPSILON,
                )
            )
        )

        for i in range(
            lookback,
            len(returns),
        ):

            feature_window = returns[
                i - lookback:i
            ]

            momentum_3 = (
                np.sum(
                    feature_window[-3:]
                )
            )

            momentum_7 = (
                np.sum(
                    feature_window[-7:]
                )
            )

            volatility = (
                np.std(
                    feature_window
                )
            )

            features = np.concatenate(
                [
                    feature_window,
                    [
                        momentum_3,
                        momentum_7,
                        volatility,
                    ],
                ]
            )

            X.append(
                features
            )

            y.append(
                returns[i]
            )

        if len(X) < 30:

            return self._linear_regression_forecast(
                prices
            )

        X = np.asarray(
            X,
            dtype=float,
        )

        y = np.asarray(
            y,
            dtype=float,
        )

        model = RandomForestRegressor(
            n_estimators=self.rf_estimators,
            max_depth=self.rf_max_depth,
            min_samples_leaf=3,
            random_state=42,
            n_jobs=-1,
        )

        model.fit(
            X,
            y,
        )

        recent_returns = list(
            returns[-lookback:]
        )

        price = float(
            prices[-1]
        )

        predictions = []

        for _ in range(horizon):

            recent = np.asarray(
                recent_returns[-lookback:],
                dtype=float,
            )

            features = np.concatenate(
                [
                    recent,
                    [
                        np.sum(
                            recent[-3:]
                        ),
                        np.sum(
                            recent[-7:]
                        ),
                        np.std(
                            recent
                        ),
                    ],
                ]
            ).reshape(
                1,
                -1,
            )

            next_return = float(
                model.predict(
                    features
                )[0]
            )

            next_return = float(
                np.clip(
                    next_return,
                    -0.08,
                    0.08,
                )
            )

            price *= np.exp(
                next_return
            )

            predictions.append(
                price
            )

            recent_returns.append(
                next_return
            )

        return np.asarray(
            predictions,
            dtype=float,
        )

    # ========================================================
    # PATTERN RECOGNITION
    # ========================================================

    def _pattern_recognition_forecast(
        self,
        prices: np.ndarray,
    ) -> np.ndarray:

        prices = np.asarray(
            prices,
            dtype=np.float64,
        )

        horizon = self.forecast_horizons["long"]

        window = self.pattern_window

        if len(prices) < (
            window + horizon + 20
        ):

            return self._momentum_fallback(
                prices,
                horizon,
            )

        current_pattern = prices[-window:]

        current_returns = (
            np.diff(
                np.log(
                    np.maximum(
                        current_pattern,
                        EPSILON,
                    )
                )
            )
        )

        candidates = []

        search_start = max(
            window,
            len(prices)
            - self.pattern_search_window,
        )

        search_end = (
            len(prices)
            - horizon
        )

        for end_idx in range(
            search_start,
            search_end,
        ):

            start_idx = (
                end_idx - window
            )

            historical_pattern = (
                prices[
                    start_idx:end_idx
                ]
            )

            historical_returns = (
                np.diff(
                    np.log(
                        np.maximum(
                            historical_pattern,
                            EPSILON,
                        )
                    )
                )
            )

            similarity = (
                self._calculate_pattern_similarity(
                    current_returns,
                    historical_returns,
                )
            )

            future_prices = prices[
                end_idx:end_idx + horizon
            ]

            if len(future_prices) != horizon:
                continue

            # ------------------------------------------------
            # IMPORTANT:
            # Store FUTURE RETURNS, not raw historical price.
            #
            # This prevents the old bug where BTC was compared
            # against patterns priced at 100-200 dollars.
            # ------------------------------------------------

            future_returns = (
                np.diff(
                    np.log(
                        np.maximum(
                            np.concatenate(
                                [
                                    [prices[end_idx - 1]],
                                    future_prices,
                                ]
                            ),
                            EPSILON,
                        )
                    )
                )
            )

            if len(future_returns) != horizon:
                continue

            candidates.append(
                (
                    similarity,
                    future_returns,
                )
            )

        if not candidates:

            return self._momentum_fallback(
                prices,
                horizon,
            )

        candidates.sort(
            key=lambda x: x[0],
            reverse=True,
        )

        # Only use meaningful matches
        selected = [
            candidate
            for candidate in candidates[:8]
            if candidate[0] >= 0.55
        ]

        if not selected:

            return self._momentum_fallback(
                prices,
                horizon,
            )

        weighted_returns = np.zeros(
            horizon,
            dtype=float,
        )

        total_weight = 0.0

        for similarity, future_returns in selected:

            weight = max(
                similarity - 0.5,
                0.01,
            )

            weighted_returns += (
                future_returns
                * weight
            )

            total_weight += weight

        if total_weight <= 0:

            return self._momentum_fallback(
                prices,
                horizon,
            )

        weighted_returns /= (
            total_weight
        )

        # Reconstruct future price from CURRENT price
        price = float(
            prices[-1]
        )

        predictions = []

        for ret in weighted_returns:

            ret = float(
                np.clip(
                    ret,
                    -0.08,
                    0.08,
                )
            )

            price *= np.exp(
                ret
            )

            predictions.append(
                price
            )

        return np.asarray(
            predictions,
            dtype=float,
        )

    def _calculate_pattern_similarity(
        self,
        pattern1: np.ndarray,
        pattern2: np.ndarray,
    ) -> float:

        pattern1 = np.asarray(
            pattern1,
            dtype=np.float64,
        )

        pattern2 = np.asarray(
            pattern2,
            dtype=np.float64,
        )

        if len(pattern1) != len(pattern2):
            return 0.0

        if len(pattern1) < 5:
            return 0.0

        std1 = np.std(pattern1)
        std2 = np.std(pattern2)

        if (
            std1 < EPSILON
            or std2 < EPSILON
        ):
            return 0.5

        p1 = (
            pattern1
            - np.mean(pattern1)
        ) / std1

        p2 = (
            pattern2
            - np.mean(pattern2)
        ) / std2

        correlation = np.corrcoef(
            p1,
            p2,
        )[0, 1]

        if not np.isfinite(correlation):
            correlation = 0.0

        correlation_score = (
            correlation + 1.0
        ) / 2.0

        shape_score = (
            self._compare_pattern_shape(
                pattern1,
                pattern2,
            )
        )

        similarity = (
            correlation_score * 0.75
            + shape_score * 0.25
        )

        return float(
            np.clip(
                similarity,
                0.0,
                1.0,
            )
        )

    def _compare_pattern_shape(
        self,
        pattern1: np.ndarray,
        pattern2: np.ndarray,
    ) -> float:

        peaks1, _ = find_peaks(
            pattern1,
            distance=3,
        )

        peaks2, _ = find_peaks(
            pattern2,
            distance=3,
        )

        troughs1, _ = find_peaks(
            -pattern1,
            distance=3,
        )

        troughs2, _ = find_peaks(
            -pattern2,
            distance=3,
        )

        count_difference = (
            abs(len(peaks1) - len(peaks2))
            + abs(len(troughs1) - len(troughs2))
        )

        count_score = max(
            0.0,
            1.0 - count_difference / 6.0,
        )

        positional_score = 0.5

        if (
            len(peaks1) > 0
            and len(peaks2) > 0
        ):

            p1 = (
                peaks1
                / len(pattern1)
            )

            p2 = (
                peaks2
                / len(pattern2)
            )

            common = min(
                len(p1),
                len(p2),
            )

            positional_score = (
                1.0
                - np.mean(
                    np.abs(
                        p1[:common]
                        - p2[:common]
                    )
                )
            )

        return float(
            np.clip(
                (
                    count_score
                    + positional_score
                )
                / 2.0,
                0.0,
                1.0,
            )
        )

    def _momentum_fallback(
        self,
        prices: np.ndarray,
        horizon: int,
    ) -> np.ndarray:

        prices = np.asarray(
            prices,
            dtype=float,
        )

        current = prices[-1]

        if len(prices) >= 10:

            momentum = (
                prices[-1]
                / prices[-10]
                - 1.0
            ) / 9.0

        else:

            momentum = 0.0

        momentum = float(
            np.clip(
                momentum,
                -0.015,
                0.015,
            )
        )

        predictions = []

        price = current

        for i in range(horizon):

            price *= (
                1.0
                + momentum
                * (0.8 ** i)
            )

            predictions.append(
                price
            )

        return np.asarray(
            predictions,
            dtype=float,
        )

    # ========================================================
    # MONTE CARLO
    # ========================================================

    def _monte_carlo_forecast(
        self,
        prices: np.ndarray,
    ) -> np.ndarray:

        prices = np.asarray(
            prices,
            dtype=float,
        )

        horizon = self.forecast_horizons["long"]

        if len(prices) < 30:

            return np.full(
                horizon,
                prices[-1],
            )

        returns = np.diff(
            np.log(
                np.maximum(
                    prices,
                    EPSILON,
                )
            )
        )

        # Recent volatility is more relevant
        returns = returns[-120:]

        mu = float(
            np.mean(returns)
        )

        sigma = float(
            np.std(returns)
        )

        # Damp drift to avoid unrealistic exponential growth
        mu *= 0.35

        sigma = max(
            sigma,
            0.0001,
        )

        rng = np.random.default_rng(
            seed=42
        )

        random_returns = rng.normal(
            loc=mu,
            scale=sigma,
            size=(
                self.mc_simulations,
                horizon,
            ),
        )

        cumulative = np.cumsum(
            random_returns,
            axis=1,
        )

        paths = (
            prices[-1]
            * np.exp(
                cumulative
            )
        )

        # Use median instead of mean.
        # Median is more robust against extreme paths.
        median_path = np.median(
            paths,
            axis=0,
        )

        return median_path.astype(
            float
        )

    # ========================================================
    # SENTIMENT + TECHNICAL
    # ========================================================

    def _sentiment_technical_forecast(
        self,
        prices: np.ndarray,
        sentiment_result: Any,
        technical_result: Any,
    ) -> np.ndarray:

        current_price = float(
            prices[-1]
        )

        horizon = self.forecast_horizons["long"]

        sentiment_score = self._safe_score(
            getattr(
                sentiment_result,
                "overall_score",
                0.0,
            )
        )

        technical_score = self._safe_score(
            getattr(
                technical_result,
                "overall_score",
                0.0,
            )
        )

        combined_score = (
            sentiment_score * 0.40
            + technical_score * 0.60
        )

        # Historical momentum
        if len(prices) >= 10:

            momentum = (
                prices[-1]
                / prices[-10]
                - 1.0
            )

        else:

            momentum = 0.0

        momentum = float(
            np.clip(
                momentum,
                -0.08,
                0.08,
            )
        )

        # Convert score into daily return.
        # Maximum approximately ±1.5%.
        sentiment_drift = (
            combined_score
            * 0.015
        )

        predictions = []

        price = current_price

        for i in range(horizon):

            decay = (
                0.85 ** i
            )

            daily_return = (
                momentum
                / 5.0
                * decay
                + sentiment_drift
                * decay
            )

            daily_return = float(
                np.clip(
                    daily_return,
                    -0.03,
                    0.03,
                )
            )

            price *= (
                1.0
                + daily_return
            )

            predictions.append(
                price
            )

        return np.asarray(
            predictions,
            dtype=float,
        )

    # ========================================================
    # ENSEMBLE
    # ========================================================

    def _ensemble_forecast(
        self,
        predictions: Dict[str, np.ndarray],
        current_price: float,
    ) -> Tuple[
        np.ndarray,
        Dict[str, float],
    ]:

        valid_predictions = {}

        for name, prediction in predictions.items():

            arr = np.asarray(
                prediction,
                dtype=float,
            )

            if (
                arr.size
                == self.forecast_horizons["long"]
                and np.all(
                    np.isfinite(arr)
                )
            ):

                valid_predictions[name] = arr

        if not valid_predictions:

            fallback = np.full(
                self.forecast_horizons["long"],
                current_price,
            )

            return (
                fallback,
                {"fallback": 1.0},
            )

        # ----------------------------------------------------
        # Normalize weights
        # ----------------------------------------------------

        raw_weights = {}

        for name in valid_predictions:

            raw_weights[name] = max(
                float(
                    self.model_weights.get(
                        name,
                        0.10,
                    )
                ),
                0.0,
            )

        total = sum(
            raw_weights.values()
        )

        if total <= 0:

            equal_weight = (
                1.0
                / len(valid_predictions)
            )

            effective_weights = {
                name: equal_weight
                for name in valid_predictions
            }

        else:

            effective_weights = {
                name: weight / total
                for name, weight
                in raw_weights.items()
            }

        ensemble = np.zeros(
            self.forecast_horizons["long"],
            dtype=float,
        )

        for name, prediction in valid_predictions.items():

            ensemble += (
                prediction
                * effective_weights[name]
            )

        ensemble = self._sanitize_prediction(
            ensemble,
            current_price,
        )

        return (
            ensemble,
            effective_weights,
        )

    # ========================================================
    # MODEL AGREEMENT
    # ========================================================

    def _calculate_model_agreement(
        self,
        predictions: Dict[str, np.ndarray],
        current_price: float,
    ) -> float:

        if len(predictions) <= 1:
            return 1.0

        final_returns = []

        for prediction in predictions.values():

            arr = np.asarray(
                prediction,
                dtype=float,
            )

            if len(arr) == 0:
                continue

            final_return = (
                arr[-1]
                / current_price
                - 1.0
            )

            final_returns.append(
                final_return
            )

        if len(final_returns) <= 1:
            return 1.0

        final_returns = np.asarray(
            final_returns,
            dtype=float,
        )

        dispersion = float(
            np.std(
                final_returns
            )
        )

        # Agreement falls as model dispersion increases.
        # 5% dispersion => ~0 agreement.
        agreement = (
            1.0
            - dispersion / 0.05
        )

        agreement = float(
            np.clip(
                agreement,
                0.0,
                1.0,
            )
        )

        # Also check direction agreement
        directions = np.sign(
            final_returns
        )

        positive = np.sum(
            directions > 0
        )

        negative = np.sum(
            directions < 0
        )

        sideways = np.sum(
            directions == 0
        )

        direction_ratio = max(
            positive,
            negative,
            sideways,
        ) / len(
            directions
        )

        agreement = (
            agreement * 0.65
            + direction_ratio * 0.35
        )

        return float(
            np.clip(
                agreement,
                0.0,
                1.0,
            )
        )

    # ========================================================
    # TREND
    # ========================================================

    def _analyze_trend(
        self,
        prices: np.ndarray,
    ) -> Tuple[str, float]:

        prices = np.asarray(
            prices,
            dtype=float,
        )

        if len(prices) < 50:

            return (
                "CONSOLIDATING",
                0.0,
            )

        current = float(
            prices[-1]
        )

        ma20 = float(
            np.mean(
                prices[-20:]
            )
        )

        ma50 = float(
            np.mean(
                prices[-50:]
            )
        )

        ma100 = float(
            np.mean(
                prices[-100:]
            )
        ) if len(prices) >= 100 else ma50

        # Slopes
        slope_20 = self._slope(
            prices[-20:]
        )

        slope_50 = self._slope(
            prices[-50:]
        )

        bullish_conditions = [
            current > ma20,
            ma20 > ma50,
            ma50 >= ma100,
            slope_20 > 0,
            slope_50 > 0,
        ]

        bearish_conditions = [
            current < ma20,
            ma20 < ma50,
            ma50 <= ma100,
            slope_20 < 0,
            slope_50 < 0,
        ]

        bullish_score = (
            sum(
                bullish_conditions
            )
            / len(
                bullish_conditions
            )
        )

        bearish_score = (
            sum(
                bearish_conditions
            )
            / len(
                bearish_conditions
            )
        )

        if bullish_score >= 0.70:

            trend = "BULLISH"

            distance = abs(
                current / ma20 - 1.0
            )

            strength = (
                distance * 5.0
                + bullish_score * 0.50
            )

        elif bearish_score >= 0.70:

            trend = "BEARISH"

            distance = abs(
                current / ma20 - 1.0
            )

            strength = (
                distance * 5.0
                + bearish_score * 0.50
            )

        else:

            trend = "CONSOLIDATING"

            recent_range = (
                np.max(
                    prices[-20:]
                )
                - np.min(
                    prices[-20:]
                )
            ) / max(
                np.mean(
                    prices[-20:]
                ),
                EPSILON,
            )

            strength = max(
                0.0,
                1.0 - recent_range * 10.0,
            ) * 0.40

        strength = float(
            np.clip(
                strength,
                0.0,
                1.0,
            )
        )

        return (
            trend,
            strength,
        )

    def _slope(
        self,
        values: np.ndarray,
    ) -> float:

        values = np.asarray(
            values,
            dtype=float,
        )

        if len(values) < 2:
            return 0.0

        x = np.arange(
            len(values),
            dtype=float,
        )

        slope = np.polyfit(
            x,
            values,
            1,
        )[0]

        mean_value = np.mean(
            values
        )

        if abs(mean_value) < EPSILON:
            return 0.0

        return float(
            slope / mean_value
        )

    # ========================================================
    # NEXT MOVE PROBABILITY
    # ========================================================

    def _predict_next_move(
        self,
        prices: np.ndarray,
        ensemble_pred: np.ndarray,
        model_agreement: float,
    ) -> Dict[str, float]:

        current_price = float(
            prices[-1]
        )

        if len(ensemble_pred) == 0:

            return {
                "UP": 0.33,
                "DOWN": 0.33,
                "SIDEWAYS": 0.34,
            }

        predicted_return = (
            ensemble_pred[0]
            / current_price
            - 1.0
        )

        if len(prices) >= 5:

            historical_momentum = (
                prices[-1]
                / prices[-5]
                - 1.0
            )

        else:

            historical_momentum = 0.0

        # Blend forecast and momentum
        combined = (
            predicted_return * 0.70
            + historical_momentum * 0.30
        )

        # Volatility adaptive threshold
        returns = np.diff(
            np.log(
                np.maximum(
                    prices,
                    EPSILON,
                )
            )
        )

        volatility = (
            np.std(
                returns[-30:]
            )
            if len(returns) >= 5
            else 0.01
        )

        threshold = max(
            0.005,
            volatility * 0.50,
        )

        # ----------------------------------------------------
        # Convert signal into probabilities
        # ----------------------------------------------------

        magnitude = abs(
            combined
        )

        strength = np.clip(
            magnitude
            / max(
                threshold * 3.0,
                EPSILON,
            ),
            0.0,
            1.0,
        )

        # Agreement modifies certainty.
        certainty = (
            0.35
            + 0.65
            * model_agreement
        )

        strength *= certainty

        if combined > threshold:

            up = (
                0.34
                + 0.45 * strength
            )

            down = (
                0.22
                - 0.10 * strength
            )

            sideways = (
                1.0
                - up
                - down
            )

        elif combined < -threshold:

            down = (
                0.34
                + 0.45 * strength
            )

            up = (
                0.22
                - 0.10 * strength
            )

            sideways = (
                1.0
                - up
                - down
            )

        else:

            sideways = (
                0.40
                + 0.20
                * (
                    1.0
                    - strength
                )
            )

            remaining = (
                1.0
                - sideways
            )

            up = (
                remaining * 0.50
            )

            down = (
                remaining * 0.50
            )

        probabilities = {
            "UP": max(
                0.0,
                float(up),
            ),
            "DOWN": max(
                0.0,
                float(down),
            ),
            "SIDEWAYS": max(
                0.0,
                float(sideways),
            ),
        }

        total = sum(
            probabilities.values()
        )

        if total <= 0:

            return {
                "UP": 0.33,
                "DOWN": 0.33,
                "SIDEWAYS": 0.34,
            }

        return {
            key: value / total
            for key, value
            in probabilities.items()
        }

    # ========================================================
    # PRICE PREDICTION
    # ========================================================

    def _create_price_prediction(
        self,
        ensemble_pred: np.ndarray,
        horizon: str,
        current_price: float,
        model_agreement: float,
        data_quality: float,
    ) -> PricePrediction:

        days = self.forecast_horizons[
            horizon
        ]

        idx = min(
            days - 1,
            len(ensemble_pred) - 1,
        )

        predicted_price = float(
            ensemble_pred[idx]
        )

        predicted_change = (
            predicted_price
            / current_price
            - 1.0
        )

        base_confidence = (
            self.confidence_levels.get(
                horizon,
                0.50,
            )
        )

        # Confidence should depend on:
        # 1. model agreement
        # 2. data quality
        # 3. magnitude of prediction
        # 4. horizon

        signal_strength = np.clip(
            abs(predicted_change)
            / 0.05,
            0.0,
            1.0,
        )

        confidence = (
            base_confidence * 0.35
            + model_agreement * 0.35
            + data_quality * 0.20
            + signal_strength * 0.10
        )

        confidence = float(
            np.clip(
                confidence,
                0.20,
                0.90,
            )
        )

        # Confidence interval based on recent volatility.
        #
        # More volatility = wider interval.
        spread_factor = (
            0.025
            + (
                1.0
                - confidence
            )
            * 0.05
        )

        spread = max(
            predicted_price
            * spread_factor,
            current_price * 0.01,
        )

        lower = max(
            current_price * 0.50,
            predicted_price - spread,
        )

        upper = (
            predicted_price
            + spread
        )

        return PricePrediction(
            timestamp=datetime.now(
                timezone.utc
            ) + timedelta(
                days=days
            ),

            predicted_price=predicted_price,

            confidence_interval_lower=float(
                lower
            ),

            confidence_interval_upper=float(
                upper
            ),

            confidence=confidence,

            horizon=horizon.upper(),

            predicted_change_percent=float(
                predicted_change * 100.0
            ),
        )

    # ========================================================
    # SCENARIOS
    # ========================================================

    def _generate_scenarios(
        self,
        current_price: float,
        ensemble_pred: np.ndarray,
        predictions: Dict[str, np.ndarray],
        model_agreement: float,
    ) -> Dict[str, Any]:

        ensemble_pred = np.asarray(
            ensemble_pred,
            dtype=float,
        )

        # Most likely
        most_likely = ensemble_pred.copy()

        if predictions:

            matrix = np.vstack(
                [
                    np.asarray(
                        pred,
                        dtype=float,
                    )
                    for pred in predictions.values()
                ]
            )

            # Use quantiles instead of min/max.
            # Min/max is too sensitive to one bad model.
            bullish = np.percentile(
                matrix,
                75,
                axis=0,
            )

            bearish = np.percentile(
                matrix,
                25,
                axis=0,
            )

        else:

            bullish = (
                ensemble_pred * 1.05
            )

            bearish = (
                ensemble_pred * 0.95
            )

        # Add controlled volatility buffer
        bullish = np.maximum(
            bullish,
            most_likely,
        )

        bearish = np.minimum(
            bearish,
            most_likely,
        )

        # Scenario probabilities
        #
        # Better agreement => most likely scenario gets
        # higher probability.
        most_likely_prob = (
            0.35
            + 0.30
            * model_agreement
        )

        remaining = (
            1.0
            - most_likely_prob
        )

        # Direction determines whether bullish or bearish
        # gets slightly higher probability.
        expected_return = (
            most_likely[-1]
            / current_price
            - 1.0
        )

        if expected_return > 0:

            bullish_prob = (
                remaining * 0.60
            )

            bearish_prob = (
                remaining * 0.40
            )

        elif expected_return < 0:

            bullish_prob = (
                remaining * 0.40
            )

            bearish_prob = (
                remaining * 0.60
            )

        else:

            bullish_prob = (
                remaining * 0.50
            )

            bearish_prob = (
                remaining * 0.50
            )

        probabilities = np.array(
            [
                bullish_prob,
                bearish_prob,
                most_likely_prob,
            ],
            dtype=float,
        )

        probabilities /= (
            probabilities.sum()
        )

        return {
            "bullish": bullish,
            "bearish": bearish,
            "most_likely": most_likely,

            "bullish_prob": float(
                probabilities[0]
            ),

            "bearish_prob": float(
                probabilities[1]
            ),

            "most_likely_prob": float(
                probabilities[2]
            ),
        }

    # ========================================================
    # KEY LEVELS
    # ========================================================

    def _find_key_levels(
        self,
        df: pd.DataFrame,
        current_price: float,
    ) -> Tuple[
        List[float],
        List[float],
    ]:

        if (
            "High" not in df.columns
            or "Low" not in df.columns
        ):

            return [], []

        high = (
            df["High"]
            .astype(float)
            .to_numpy()
        )

        low = (
            df["Low"]
            .astype(float)
            .to_numpy()
        )

        if len(high) < 30:
            return [], []

        window = 5

        peaks, _ = find_peaks(
            high,
            distance=window,
        )

        troughs, _ = find_peaks(
            -low,
            distance=window,
        )

        resistance_candidates = [
            float(high[i])
            for i in peaks
            if high[i] > current_price
        ]

        support_candidates = [
            float(low[i])
            for i in troughs
            if low[i] < current_price
        ]

        resistance = self._cluster_levels(
            resistance_candidates,
            tolerance=0.015,
        )

        support = self._cluster_levels(
            support_candidates,
            tolerance=0.015,
        )

        # Nearest levels first
        resistance = sorted(
            resistance,
            key=lambda x: abs(
                x - current_price
            ),
        )

        support = sorted(
            support,
            key=lambda x: abs(
                x - current_price
            ),
        )

        return (
            support[:3],
            resistance[:3],
        )

    def _cluster_levels(
        self,
        levels: List[float],
        tolerance: float = 0.02,
    ) -> List[float]:

        if not levels:
            return []

        sorted_levels = sorted(
            float(x)
            for x in levels
            if np.isfinite(x)
            and x > 0
        )

        if not sorted_levels:
            return []

        clusters = []

        current_cluster = [
            sorted_levels[0]
        ]

        for level in sorted_levels[1:]:

            avg = np.mean(
                current_cluster
            )

            if (
                abs(
                    level - avg
                )
                / max(
                    avg,
                    EPSILON,
                )
                <= tolerance
            ):

                current_cluster.append(
                    level
                )

            else:

                clusters.append(
                    float(
                        np.mean(
                            current_cluster
                        )
                    )
                )

                current_cluster = [
                    level
                ]

        clusters.append(
            float(
                np.mean(
                    current_cluster
                )
            )
        )

        return clusters

    # ========================================================
    # EXPECTED RANGE
    # ========================================================

    def _calculate_expected_range(
        self,
        current_price: float,
        predictions: Dict[str, np.ndarray],
        ensemble_prediction: np.ndarray,
    ) -> Tuple[float, float]:

        if not predictions:

            return (
                current_price * 1.05,
                current_price * 0.95,
            )

        matrix = np.vstack(
            [
                np.asarray(
                    prediction,
                    dtype=float,
                )
                for prediction
                in predictions.values()
            ]
        )

        # Robust quantiles
        high = float(
            np.percentile(
                matrix,
                90,
            )
        )

        low = float(
            np.percentile(
                matrix,
                10,
            )
        )

        # Include ensemble
        high = max(
            high,
            float(
                np.max(
                    ensemble_prediction
                )
            ),
        )

        low = min(
            low,
            float(
                np.min(
                    ensemble_prediction
                )
            ),
        )

        # ----------------------------------------------------
        # CRITICAL SAFETY
        # ----------------------------------------------------

        low = max(
            low,
            current_price * 0.50,
        )

        high = max(
            high,
            current_price * 1.001,
        )

        # Never return invalid range
        if low >= high:

            low = (
                current_price * 0.97
            )

            high = (
                current_price * 1.03
            )

        return (
            float(high),
            float(low),
        )

    # ========================================================
    # FORECAST SCORE
    # ========================================================

    def _calculate_forecast_score(
        self,
        current_price: float,
        short_prediction: PricePrediction,
        trend: str,
        trend_strength: float,
        model_agreement: float,
        data_quality: float,
        probabilities: Dict[str, float],
    ) -> float:

        predicted_return = (
            short_prediction.predicted_price
            / current_price
            - 1.0
        )

        # Normalize expected return to -1..1
        return_component = np.clip(
            predicted_return / 0.05,
            -1.0,
            1.0,
        )

        trend_component = 0.0

        if trend == "BULLISH":
            trend_component = (
                trend_strength
            )

        elif trend == "BEARISH":
            trend_component = (
                -trend_strength
            )

        probability_component = (
            probabilities["UP"]
            - probabilities["DOWN"]
        )

        score = (
            return_component * 0.45
            + trend_component * 0.20
            + probability_component * 0.20
            + (
                return_component
                * model_agreement
            ) * 0.10
            + (
                return_component
                * data_quality
            ) * 0.05
        )

        return float(
            np.clip(
                score,
                -1.0,
                1.0,
            )
        )

    # ========================================================
    # ACTION
    # ========================================================

    def _forecast_action(
        self,
        forecast_score: float,
        confidence: float,
        model_agreement: float,
    ) -> str:

        # ----------------------------------------------------
        # No strong action when models disagree.
        # ----------------------------------------------------

        if (
            model_agreement
            < self.min_model_agreement
        ):

            return "HOLD"

        if (
            confidence
            < self.min_forecast_confidence
        ):

            return "HOLD"

        if (
            forecast_score
            >= self.strong_buy_threshold
        ):

            return "STRONG_BUY"

        if (
            forecast_score
            >= self.buy_threshold
        ):

            return "BUY"

        if (
            forecast_score
            <= self.strong_sell_threshold
        ):

            return "STRONG_SELL"

        if (
            forecast_score
            <= self.sell_threshold
        ):

            return "SELL"

        return "HOLD"

    # ========================================================
    # SUMMARY
    # ========================================================

    def _generate_summary(
        self,
        symbol: str,
        current_price: float,
        trend: str,
        trend_strength: float,
        short_pred: PricePrediction,
        model_agreement: float,
        data_quality: float,
        next_move_probability: Dict[str, float],
    ) -> str:

        symbol_name = (
            symbol
            .replace("-USD", "")
            .replace("-USDT", "")
        )

        change = (
            short_pred.predicted_change_percent
        )

        if change > 1.0:

            direction = (
                f"naik {change:.2f}%"
            )

        elif change < -1.0:

            direction = (
                f"turun {abs(change):.2f}%"
            )

        else:

            direction = (
                "bergerak relatif sideways"
            )

        summary = (
            f"Forecast {symbol_name}: "
            f"harga saat ini "
            f"${current_price:.2f}. "
        )

        summary += (
            f"Trend {trend} "
            f"dengan strength "
            f"{trend_strength:.1%}. "
        )

        summary += (
            f"Forecast jangka pendek "
            f"${short_pred.predicted_price:.2f} "
            f"({direction}). "
        )

        summary += (
            f"Model agreement "
            f"{model_agreement:.1%}. "
        )

        summary += (
            f"Data quality "
            f"{data_quality:.1%}. "
        )

        summary += (
            f"Probabilitas UP "
            f"{next_move_probability['UP']:.1%}, "
            f"DOWN "
            f"{next_move_probability['DOWN']:.1%}, "
            f"SIDEWAYS "
            f"{next_move_probability['SIDEWAYS']:.1%}."
        )

        return summary

    # ========================================================
    # RECOMMENDATIONS
    # ========================================================

    def _generate_recommendations(
        self,
        current_price: float,
        trend: str,
        trend_strength: float,
        short_pred: PricePrediction,
        model_agreement: float,
        support: List[float],
        resistance: List[float],
        forecast_action: str,
        probabilities: Dict[str, float],
    ) -> List[str]:

        recommendations = []

        # Trend
        if trend == "BULLISH":

            recommendations.append(
                "Trend bullish, tetapi entry tetap membutuhkan confirmation."
            )

        elif trend == "BEARISH":

            recommendations.append(
                "Trend bearish, hindari entry agresif sebelum confirmation."
            )

        else:

            recommendations.append(
                "Trend masih konsolidasi; wait and see lebih aman."
            )

        # Forecast action
        recommendations.append(
            f"Forecast signal: {forecast_action}."
        )

        # Agreement
        if model_agreement < 0.50:

            recommendations.append(
                "Model disagreement tinggi; jangan menjadikan forecast sebagai sinyal tunggal."
            )

        elif model_agreement >= 0.75:

            recommendations.append(
                f"Model agreement relatif kuat ({model_agreement:.1%})."
            )

        # Support
        if support:

            nearest_support = min(
                support,
                key=lambda x: abs(
                    x - current_price
                ),
            )

            recommendations.append(
                f"Support terdekat: ${nearest_support:.2f}."
            )

        # Resistance
        if resistance:

            nearest_resistance = min(
                resistance,
                key=lambda x: abs(
                    x - current_price
                ),
            )

            recommendations.append(
                f"Resistance terdekat: ${nearest_resistance:.2f}."
            )

        # Direction probability
        if (
            probabilities["DOWN"]
            >= 0.65
        ):

            recommendations.append(
                "Probability DOWN dominan; tunggu confirmation sebelum entry."
            )

        elif (
            probabilities["UP"]
            >= 0.65
        ):

            recommendations.append(
                "Probability UP dominan; tunggu confirmation sebelum entry."
            )

        else:

            recommendations.append(
                "Tidak ada probabilitas arah yang cukup dominan."
            )

        return recommendations[:6]

    # ========================================================
    # DATA QUALITY
    # ========================================================

    def _calculate_data_quality(
        self,
        df: pd.DataFrame,
    ) -> Dict[str, float]:

        observations = len(df)

        close = (
            df["Close"]
            .astype(float)
        )

        returns = (
            close
            .pct_change()
            .replace(
                [np.inf, -np.inf],
                np.nan,
            )
            .dropna()
        )

        missing_ratio = (
            float(
                df["Close"].isna().mean()
            )
        )

        return_volatility = (
            float(
                returns.std()
            )
            if len(returns) > 1
            else 0.0
        )

        observation_score = min(
            observations / 365.0,
            1.0,
        )

        missing_score = max(
            0.0,
            1.0 - missing_ratio,
        )

        volatility_score = 1.0

        if return_volatility > 0.10:
            volatility_score = 0.70

        if return_volatility > 0.20:
            volatility_score = 0.40

        quality_score = (
            observation_score * 0.50
            + missing_score * 0.30
            + volatility_score * 0.20
        )

        return {
            "observations": float(
                observations
            ),
            "return_volatility": return_volatility,
            "missing_ratio": missing_ratio,
            "quality_score": float(
                np.clip(
                    quality_score,
                    0.0,
                    1.0,
                )
            ),
        }

    # ========================================================
    # CACHE
    # ========================================================

    def _cache_key(
        self,
        symbol: str,
    ) -> str:

        return (
            f"forecast_v4_{symbol}"
        )

    def _get_cached(
        self,
        cache_key: str,
    ) -> Optional[ForecastResult]:

        if cache_key not in self.cache:
            return None

        result, timestamp = (
            self.cache[cache_key]
        )

        now = datetime.now(
            timezone.utc
        )

        # Normalize naive datetime
        if timestamp.tzinfo is None:

            timestamp = timestamp.replace(
                tzinfo=timezone.utc
            )

        if (
            now - timestamp
            < self.cache_duration
        ):

            return result

        del self.cache[
            cache_key
        ]

        return None

    def _store_cache(
        self,
        cache_key: str,
        result: ForecastResult,
    ):

        self.cache[
            cache_key
        ] = (
            result,
            datetime.now(
                timezone.utc
            ),
        )

    # ========================================================
    # DEFAULT FORECAST
    # ========================================================

    def _get_default_forecast(
        self,
        symbol: str,
        current_price: float = 0.0,
        warnings: Optional[List[str]] = None,
    ) -> ForecastResult:

        current_price = max(
            float(current_price),
            0.0,
        )

        now = datetime.now(
            timezone.utc
        )

        def make_prediction(
            horizon_name: str,
        ) -> PricePrediction:

            days = self.forecast_horizons[
                horizon_name
            ]

            return PricePrediction(
                timestamp=now + timedelta(
                    days=days
                ),
                predicted_price=current_price,
                confidence_interval_lower=(
                    current_price * 0.95
                ),
                confidence_interval_upper=(
                    current_price * 1.05
                ),
                confidence=0.20,
                horizon=horizon_name.upper(),
                predicted_change_percent=0.0,
            )

        short = make_prediction(
            "short"
        )

        medium = make_prediction(
            "medium"
        )

        long = make_prediction(
            "long"
        )

        return ForecastResult(
            symbol=symbol,
            timestamp=now,
            current_price=current_price,

            short_term=short,
            medium_term=medium,
            long_term=long,

            bullish_path=[
                current_price
            ] * 7,

            bearish_path=[
                current_price
            ] * 7,

            most_likely_path=[
                current_price
            ] * 7,

            scenarios={
                "bullish": {
                    "path": [
                        current_price
                    ] * 7,
                    "probability": 0.33,
                },
                "bearish": {
                    "path": [
                        current_price
                    ] * 7,
                    "probability": 0.33,
                },
                "most_likely": {
                    "path": [
                        current_price
                    ] * 7,
                    "probability": 0.34,
                },
            },

            primary_trend="CONSOLIDATING",

            trend_strength=0.0,

            next_move_probability={
                "UP": 0.33,
                "DOWN": 0.33,
                "SIDEWAYS": 0.34,
            },

            expected_high=(
                current_price * 1.05
            ),

            expected_low=(
                current_price * 0.95
            ),

            expected_range={
                "high": current_price * 1.05,
                "low": current_price * 0.95,
                "range_percent": 10.0,
            },

            key_resistance=[],
            key_support=[],

            summary=(
                "Forecast unavailable; "
                "defaulting to neutral."
            ),

            recommendations=[
                "Wait for sufficient historical data.",
                "Do not trade based on forecast alone.",
            ],

            model_predictions={},

            model_weights={},

            model_status={},

            data_quality={
                "observations": 0.0,
                "return_volatility": 0.0,
                "missing_ratio": 1.0,
                "quality_score": 0.0,
            },

            model_agreement=0.0,

            forecast_score=0.0,

            forecast_action="HOLD",

            warnings=warnings or [],
        )

    # ========================================================
    # HELPERS
    # ========================================================

    @staticmethod
    def _safe_score(
        value: Any,
    ) -> float:

        try:

            value = float(
                np.asarray(
                    value
                ).reshape(-1)[0]
            )

            if not np.isfinite(
                value
            ):
                return 0.0

            return float(
                np.clip(
                    value,
                    -1.0,
                    1.0,
                )
            )

        except Exception:

            return 0.0

    @staticmethod
    def _safe_float_list(
        values: Any,
    ) -> List[float]:

        arr = np.asarray(
            values,
            dtype=float,
        ).reshape(-1)

        return [
            float(x)
            for x in arr
            if np.isfinite(x)
        ]


# ============================================================
# TEST / DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s - "
            "%(name)s - "
            "%(levelname)s - "
            "%(message)s"
        ),
    )

    print("=" * 70)
    print("FORECAST AGENT v4 TEST")
    print("=" * 70)

    agent = ForecastAgent()

    result = agent.analyze(
        "BTC-USD"
    )

    print()
    print(
        f"Symbol       : {result.symbol}"
    )

    print(
        f"Current Price: ${result.current_price:,.2f}"
    )

    print(
        f"Trend        : {result.primary_trend}"
    )

    print(
        f"Trend Strength: "
        f"{result.trend_strength:.2%}"
    )

    print()
    print("FORECAST")
    print("-" * 70)

    print(
        f"Short : "
        f"${result.short_term.predicted_price:,.2f} "
        f"({result.short_term.predicted_change_percent:+.2f}%) "
        f"confidence="
        f"{result.short_term.confidence:.1%}"
    )

    print(
        f"Medium: "
        f"${result.medium_term.predicted_price:,.2f} "
        f"({result.medium_term.predicted_change_percent:+.2f}%) "
        f"confidence="
        f"{result.medium_term.confidence:.1%}"
    )

    print(
        f"Long  : "
        f"${result.long_term.predicted_price:,.2f} "
        f"({result.long_term.predicted_change_percent:+.2f}%) "
        f"confidence="
        f"{result.long_term.confidence:.1%}"
    )

    print()
    print("NEXT MOVE PROBABILITY")
    print("-" * 70)

    for direction, probability in (
        result.next_move_probability.items()
    ):

        print(
            f"{direction:10s}: "
            f"{probability:.1%}"
        )

    print()
    print("MODEL AGREEMENT")
    print("-" * 70)

    print(
        f"{result.model_agreement:.1%}"
    )

    print()
    print("FORECAST SCORE")
    print("-" * 70)

    print(
        f"{result.forecast_score:+.4f}"
    )

    print(
        f"Action: {result.forecast_action}"
    )

    print()
    print("MODEL STATUS")
    print("-" * 70)

    for model, status in (
        result.model_status.items()
    ):

        print(
            f"{model:25s}: "
            f"{status}"
        )

    print()
    print("MODEL PREDICTIONS")
    print("-" * 70)

    for model, prediction in (
        result.model_predictions.items()
    ):

        first = (
            prediction[0]
            if prediction
            else result.current_price
        )

        last = (
            prediction[-1]
            if prediction
            else result.current_price
        )

        print(
            f"{model:25s}: "
            f"${first:,.2f} -> "
            f"${last:,.2f}"
        )

    print()
    print("EXPECTED RANGE")
    print("-" * 70)

    print(
        f"High: ${result.expected_high:,.2f}"
    )

    print(
        f"Low : ${result.expected_low:,.2f}"
    )

    print(
        f"Range: "
        f"{result.expected_range['range_percent']:.2f}%"
    )

    print()
    print("SUMMARY")
    print("-" * 70)

    print(
        result.summary
    )

    print()
    print("RECOMMENDATIONS")
    print("-" * 70)

    for recommendation in (
        result.recommendations
    ):

        print(
            f"- {recommendation}"
        )

    if result.warnings:

        print()
        print("WARNINGS")
        print("-" * 70)

        for warning in result.warnings:

            print(
                f"- {warning}"
            )

    print()
    print("=" * 70)
    print("FORECAST AGENT v4 TEST COMPLETE")
    print("=" * 70)
