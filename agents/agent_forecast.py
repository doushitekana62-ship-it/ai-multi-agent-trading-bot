"""
Agent 5: Forecasting Pergerakan Harga
=====================================

Forecast Agent v4

Tujuan:
    Menghasilkan forecast harga multi-horizon menggunakan ensemble:

        1. Auto Regression
        2. Linear Regression
        3. Random Forest
        4. Pattern Recognition
        5. Monte Carlo
        6. Sentiment + Technical

Pipeline:

    MARKET DATA
         |
         v
    Forecast Agent
         |
         +--> AR
         +--> Linear Regression
         +--> Random Forest
         +--> Pattern Recognition
         +--> Monte Carlo
         +--> Sentiment/Technical
         |
         v
      ENSEMBLE
         |
         v
      SCENARIOS
         |
         v
    ForecastResult

IMPORTANT:
    - Agent ini TIDAK melakukan trading.
    - Agent hanya menghasilkan forecast.
    - Forecast bukan jaminan harga masa depan.
    - Semua output harus diproses lagi oleh Risk Engine
      dan Decision Engine sebelum paper/live execution.
"""

import logging
import warnings

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd

from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor

import yfinance as yf

from scipy.signal import find_peaks


warnings.filterwarnings("ignore")

logger = logging.getLogger(__name__)


# ==============================================================
# DATA CLASSES
# ==============================================================


@dataclass
class PricePrediction:
    """
    Prediksi harga untuk satu horizon.
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
    Hasil lengkap forecasting.
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

    model_predictions: Dict[str, List[float]]

    model_weights: Dict[str, float]

    model_status: Dict[str, str]

    data_quality: Dict[str, Any]

    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:

        return asdict(self)


# ==============================================================
# FORECAST AGENT
# ==============================================================


class ForecastAgent:

    """
    Multi-model forecasting engine.

    Fokus utama:
        - robustness
        - graceful fallback
        - model agreement
        - data quality
        - compatibility dengan pipeline AI trading
    """

    # ----------------------------------------------------------
    # CONSTANTS
    # ----------------------------------------------------------

    HORIZONS = {
        "short": 2,
        "medium": 5,
        "long": 7,
    }

    BASE_CONFIDENCE = {
        "short": 0.70,
        "medium": 0.60,
        "long": 0.50,
    }

    DEFAULT_WEIGHTS = {
        "arima": 0.20,
        "linear_regression": 0.15,
        "random_forest": 0.20,
        "pattern_recognition": 0.15,
        "monte_carlo": 0.15,
        "sentiment_technical": 0.15,
    }

    MIN_HISTORY = 50

    def __init__(self, config: Optional[Dict[str, Any]] = None):

        self.config = config or {}

        # ------------------------------------------------------
        # CONFIG
        # ------------------------------------------------------

        self.forecast_horizons = {
            **self.HORIZONS,
            **self.config.get("forecast_horizons", {}),
        }

        self.model_weights = {
            **self.DEFAULT_WEIGHTS,
            **self.config.get("model_weights", {}),
        }

        self.cache_duration = timedelta(
            hours=float(
                self.config.get(
                    "cache_hours",
                    1.0
                )
            )
        )

        self.history_period = self.config.get(
            "history_period",
            "1y"
        )

        self.history_interval = self.config.get(
            "history_interval",
            "1d"
        )

        self.random_state = int(
            self.config.get(
                "random_state",
                42
            )
        )

        self.enable_cache = bool(
            self.config.get(
                "enable_cache",
                True
            )
        )

        self.cache: Dict[
            str,
            Tuple[ForecastResult, datetime]
        ] = {}

        self.pattern_database: List[Dict[str, Any]] = []

        self._initialize_pattern_database()

        logger.info(
            "Forecast Agent initialized successfully"
        )

    # ==========================================================
    # PUBLIC API
    # ==========================================================

    def analyze(
        self,
        symbol: str,
        sentiment_result: Any = None,
        technical_result: Any = None,
        market_data: Optional[Dict[str, Any]] = None,
    ) -> ForecastResult:

        logger.info(
            "Generating forecast for %s",
            symbol
        )

        symbol = str(symbol).upper()

        cache_key = f"forecast_{symbol}"

        # ------------------------------------------------------
        # CACHE
        # ------------------------------------------------------

        if self.enable_cache:

            cached = self.cache.get(cache_key)

            if cached:

                cached_result, cache_time = cached

                if (
                    datetime.now(timezone.utc)
                    - cache_time
                    < self.cache_duration
                ):

                    logger.info(
                        "Using cached forecast for %s",
                        symbol
                    )

                    return cached_result

        warnings_list: List[str] = []

        # ------------------------------------------------------
        # MARKET DATA
        # ------------------------------------------------------

        df = self._prepare_market_data(
            symbol=symbol,
            market_data=market_data
        )

        # ------------------------------------------------------
        # FALLBACK
        # ------------------------------------------------------

        if df is None or df.empty:

            logger.warning(
                "No usable historical data for %s",
                symbol
            )

            result = self._get_default_forecast(
                symbol=symbol,
                market_data=market_data
            )

            result.warnings.append(
                "Historical market data unavailable."
            )

            return result

        # ------------------------------------------------------
        # CLEAN CLOSE
        # ------------------------------------------------------

        prices = self._safe_price_array(
            df["Close"]
        )

        if len(prices) < self.MIN_HISTORY:

            warnings_list.append(
                f"Limited history: {len(prices)} observations."
            )

        if len(prices) < 10:

            logger.warning(
                "Insufficient price history for %s",
                symbol
            )

            return self._get_default_forecast(
                symbol=symbol,
                market_data=market_data,
                current_price=float(prices[-1])
                if len(prices) > 0
                else 0.0
            )

        current_price = float(
            prices[-1]
        )

        # ------------------------------------------------------
        # DATA QUALITY
        # ------------------------------------------------------

        data_quality = self._calculate_data_quality(
            prices
        )

        if data_quality["return_volatility"] > 0.10:

            warnings_list.append(
                "Very high historical volatility."
            )

        if data_quality["missing_ratio"] > 0:

            warnings_list.append(
                "Missing values were detected and cleaned."
            )

        # ======================================================
        # MODEL PREDICTIONS
        # ======================================================

        predictions: Dict[str, np.ndarray] = {}

        model_status: Dict[str, str] = {}

        horizon = self.forecast_horizons["long"]

        # ------------------------------------------------------
        # 1. AUTO REGRESSION
        # ------------------------------------------------------

        try:

            pred = self._arima_forecast(
                prices,
                horizon
            )

            predictions["arima"] = self._sanitize_prediction(
                pred,
                current_price,
                horizon
            )

            model_status["arima"] = "OK"

        except Exception as e:

            logger.exception(
                "AR model failed"
            )

            model_status["arima"] = f"FAILED: {e}"

        # ------------------------------------------------------
        # 2. LINEAR REGRESSION
        # ------------------------------------------------------

        try:

            pred = self._linear_regression_forecast(
                prices
            )

            predictions["linear_regression"] = (
                self._sanitize_prediction(
                    pred,
                    current_price,
                    horizon
                )
            )

            model_status["linear_regression"] = "OK"

        except Exception as e:

            logger.exception(
                "Linear regression failed"
            )

            model_status["linear_regression"] = (
                f"FAILED: {e}"
            )

        # ------------------------------------------------------
        # 3. RANDOM FOREST
        # ------------------------------------------------------

        try:

            pred = self._random_forest_forecast(
                df
            )

            predictions["random_forest"] = (
                self._sanitize_prediction(
                    pred,
                    current_price,
                    horizon
                )
            )

            model_status["random_forest"] = "OK"

        except Exception as e:

            logger.exception(
                "Random forest failed"
            )

            model_status["random_forest"] = (
                f"FAILED: {e}"
            )

        # ------------------------------------------------------
        # 4. PATTERN RECOGNITION
        # ------------------------------------------------------

        try:

            pred = self._pattern_recognition_forecast(
                prices
            )

            predictions["pattern_recognition"] = (
                self._sanitize_prediction(
                    pred,
                    current_price,
                    horizon
                )
            )

            model_status["pattern_recognition"] = "OK"

        except Exception as e:

            logger.exception(
                "Pattern recognition failed"
            )

            model_status["pattern_recognition"] = (
                f"FAILED: {e}"
            )

        # ------------------------------------------------------
        # 5. MONTE CARLO
        # ------------------------------------------------------

        try:

            pred = self._monte_carlo_forecast(
                prices
            )

            predictions["monte_carlo"] = (
                self._sanitize_prediction(
                    pred,
                    current_price,
                    horizon
                )
            )

            model_status["monte_carlo"] = "OK"

        except Exception as e:

            logger.exception(
                "Monte Carlo failed"
            )

            model_status["monte_carlo"] = (
                f"FAILED: {e}"
            )

        # ------------------------------------------------------
        # 6. SENTIMENT + TECHNICAL
        # ------------------------------------------------------

        if (
            sentiment_result is not None
            or technical_result is not None
        ):

            try:

                pred = self._sentiment_technical_forecast(
                    prices,
                    sentiment_result,
                    technical_result
                )

                predictions["sentiment_technical"] = (
                    self._sanitize_prediction(
                        pred,
                        current_price,
                        horizon
                    )
                )

                model_status[
                    "sentiment_technical"
                ] = "OK"

            except Exception as e:

                logger.exception(
                    "Sentiment/technical forecast failed"
                )

                model_status[
                    "sentiment_technical"
                ] = f"FAILED: {e}"

        # ======================================================
        # ENSEMBLE
        # ======================================================

        ensemble_prediction, effective_weights = (
            self._ensemble_forecast(
                predictions,
                current_price,
                horizon
            )
        )

        if len(predictions) < 2:

            warnings_list.append(
                "Ensemble has fewer than 2 successful models."
            )

        # ======================================================
        # SCENARIOS
        # ======================================================

        scenarios = self._generate_scenarios(
            current_price=current_price,
            ensemble_pred=ensemble_prediction,
            predictions=predictions,
            prices=prices
        )

        # ======================================================
        # TREND
        # ======================================================

        primary_trend, trend_strength = (
            self._analyze_trend(
                prices
            )
        )

        # ======================================================
        # NEXT MOVE
        # ======================================================

        next_move_probability = (
            self._predict_next_move(
                prices,
                ensemble_prediction
            )
        )

        # ======================================================
        # PRICE PREDICTIONS
        # ======================================================

        short_pred = self._create_price_prediction(
            ensemble_prediction,
            "short",
            current_price
        )

        medium_pred = self._create_price_prediction(
            ensemble_prediction,
            "medium",
            current_price
        )

        long_pred = self._create_price_prediction(
            ensemble_prediction,
            "long",
            current_price
        )

        # ======================================================
        # KEY LEVELS
        # ======================================================

        key_support, key_resistance = (
            self._find_key_levels(
                df,
                current_price
            )
        )

        # ======================================================
        # EXPECTED RANGE
        # ======================================================

        expected_high, expected_low = (
            self._calculate_expected_range(
                predictions=predictions,
                current_price=current_price,
                prices=prices
            )
        )

        # ======================================================
        # SUMMARY
        # ======================================================

        summary = self._generate_summary(
            symbol=symbol,
            current_price=current_price,
            trend=primary_trend,
            trend_strength=trend_strength,
            ensemble_pred=ensemble_prediction,
            short_pred=short_pred,
            scenarios=scenarios,
            data_quality=data_quality
        )

        # ======================================================
        # RECOMMENDATIONS
        # ======================================================

        recommendations = (
            self._generate_recommendations(
                trend=primary_trend,
                trend_strength=trend_strength,
                ensemble_pred=ensemble_prediction,
                short_pred=short_pred,
                support=key_support,
                resistance=key_resistance,
                next_move_probability=next_move_probability
            )
        )

        # ======================================================
        # MODEL OUTPUT
        # ======================================================

        model_predictions = {}

        for name, pred in predictions.items():

            model_predictions[name] = [
                float(x)
                for x in pred
            ]

        # ======================================================
        # BUILD RESULT
        # ======================================================

        result = ForecastResult(

            symbol=symbol,

            timestamp=datetime.now(
                timezone.utc
            ),

            current_price=current_price,

            short_term=short_pred,

            medium_term=medium_pred,

            long_term=long_pred,

            bullish_path=[
                float(x)
                for x in scenarios["bullish"]
            ],

            bearish_path=[
                float(x)
                for x in scenarios["bearish"]
            ],

            most_likely_path=[
                float(x)
                for x in scenarios["most_likely"]
            ],

            scenarios={
                "bullish": {
                    "path": [
                        float(x)
                        for x in scenarios["bullish"]
                    ],
                    "probability": float(
                        scenarios["bullish_prob"]
                    )
                },

                "bearish": {
                    "path": [
                        float(x)
                        for x in scenarios["bearish"]
                    ],
                    "probability": float(
                        scenarios["bearish_prob"]
                    )
                },

                "most_likely": {
                    "path": [
                        float(x)
                        for x in scenarios["most_likely"]
                    ],
                    "probability": float(
                        scenarios["most_likely_prob"]
                    )
                }
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
                        expected_high
                        - expected_low
                    )
                    / current_price
                    * 100
                )
                if current_price > 0
                else 0.0
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

            model_predictions=model_predictions,

            model_weights={
                key: float(value)
                for key, value
                in effective_weights.items()
            },

            model_status=model_status,

            data_quality=data_quality,

            warnings=warnings_list
        )

        # ------------------------------------------------------
        # CACHE
        # ------------------------------------------------------

        if self.enable_cache:

            self.cache[cache_key] = (
                result,
                datetime.now(timezone.utc)
            )

        return result

    # ==========================================================
    # MARKET DATA
    # ==========================================================

    def _prepare_market_data(
        self,
        symbol: str,
        market_data: Optional[Dict[str, Any]]
    ) -> Optional[pd.DataFrame]:

        """
        Gunakan market_data jika memiliki OHLCV.

        Jika tidak tersedia, fallback ke yfinance.
        """

        # ------------------------------------------------------
        # MARKET DATA FROM ORCHESTRATOR
        # ------------------------------------------------------

        if isinstance(
            market_data,
            pd.DataFrame
        ):

            df = market_data.copy()

            return self._clean_dataframe(
                df
            )

        if isinstance(
            market_data,
            dict
        ):

            # Support:
            # {
            #   "history": [...]
            # }
            # atau:
            # {
            #   "historical_data": [...]
            # }

            historical = (
                market_data.get("history")
                or market_data.get("historical_data")
            )

            if historical is not None:

                try:

                    df = pd.DataFrame(
                        historical
                    )

                    return self._clean_dataframe(
                        df
                    )

                except Exception as e:

                    logger.warning(
                        "Unable to parse market_data history: %s",
                        e
                    )

            # Support simple OHLC arrays
            if "Close" in market_data:

                try:

                    close = self._safe_price_array(
                        market_data["Close"]
                    )

                    if len(close) >= 10:

                        return pd.DataFrame(
                            {
                                "Close": close
                            }
                        )

                except Exception:
                    pass

        # ======================================================
        # YFINANCE FALLBACK
        # ======================================================

        try:

            ticker = yf.Ticker(
                symbol
            )

            df = ticker.history(
                period=self.history_period,
                interval=self.history_interval,
                auto_adjust=True
            )

            return self._clean_dataframe(
                df
            )

        except Exception as e:

            logger.error(
                "Error fetching historical data for %s: %s",
                symbol,
                e
            )

            return None

    # ==========================================================
    # DATA CLEANING
    # ==========================================================

    def _clean_dataframe(
        self,
        df: pd.DataFrame
    ) -> Optional[pd.DataFrame]:

        if df is None or df.empty:

            return None

        df = df.copy()

        # Normalize column names
        df.columns = [
            str(col).strip()
            for col in df.columns
        ]

        # Case-insensitive Close lookup
        close_column = None

        for col in df.columns:

            if str(col).lower() == "close":

                close_column = col
                break

        if close_column is None:

            return None

        if close_column != "Close":

            df["Close"] = df[
                close_column
            ]

        # Numeric conversion
        for col in [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume"
        ]:

            if col in df.columns:

                df[col] = pd.to_numeric(
                    df[col],
                    errors="coerce"
                )

        # Remove invalid prices
        df = df.dropna(
            subset=["Close"]
        )

        df = df[
            np.isfinite(
                df["Close"].values
            )
        ]

        # Positive prices only
        df = df[
            df["Close"] > 0
        ]

        return df

    # ==========================================================
    # SAFE ARRAY
    # ==========================================================

    @staticmethod
    def _safe_price_array(
        data: Any
    ) -> np.ndarray:

        """
        FIX UTAMA ERROR:

            'list' object has no attribute 'std'

        Semua input dikonversi ke numpy.ndarray.
        """

        if data is None:

            return np.array(
                [],
                dtype=float
            )

        if isinstance(
            data,
            pd.Series
        ):

            values = data.to_numpy(
                dtype=float
            )

        elif isinstance(
            data,
            pd.DataFrame
        ):

            values = data.iloc[
                :,
                0
            ].to_numpy(
                dtype=float
            )

        else:

            values = np.asarray(
                data,
                dtype=float
            )

        values = values.reshape(-1)

        values = values[
            np.isfinite(values)
        ]

        values = values[
            values > 0
        ]

        return values.astype(
            float
        )

    # ==========================================================
    # AUTO REGRESSION
    # ==========================================================

    def _arima_forecast(
        self,
        prices: np.ndarray,
        horizon: int
    ) -> np.ndarray:

        prices = self._safe_price_array(
            prices
        )

        if len(prices) < 10:

            return np.full(
                horizon,
                prices[-1]
                if len(prices)
                else 0.0
            )

        window_size = min(
            60,
            len(prices)
        )

        data = prices[
            -window_size:
        ]

        lag = min(
            5,
            max(
                2,
                len(data) // 10
            )
        )

        if len(data) <= lag + 5:

            return self._simple_moving_average_forecast(
                data,
                horizon
            )

        X = []

        y = []

        for i in range(
            lag,
            len(data)
        ):

            X.append(
                data[
                    i - lag:i
                ]
            )

            y.append(
                data[i]
            )

        X = np.asarray(
            X,
            dtype=float
        )

        y = np.asarray(
            y,
            dtype=float
        )

        model = LinearRegression()

        model.fit(
            X,
            y
        )

        history = list(
            data[-lag:]
        )

        predictions = []

        for _ in range(horizon):

            features = np.asarray(
                history[-lag:],
                dtype=float
            ).reshape(
                1,
                -1
            )

            next_price = float(
                model.predict(
                    features
                )[0]
            )

            predictions.append(
                next_price
            )

            history.append(
                next_price
            )

        return np.asarray(
            predictions,
            dtype=float
        )

    # ==========================================================
    # MOVING AVERAGE FALLBACK
    # ==========================================================

    def _simple_moving_average_forecast(
        self,
        prices: np.ndarray,
        horizon: int
    ) -> np.ndarray:

        prices = self._safe_price_array(
            prices
        )

        if len(prices) == 0:

            return np.zeros(
                horizon
            )

        if len(prices) < 5:

            return np.full(
                horizon,
                prices[-1]
            )

        window = min(
            10,
            len(prices)
        )

        recent = prices[
            -window:
        ]

        weights = np.arange(
            1,
            window + 1,
            dtype=float
        )

        weights /= weights.sum()

        base = float(
            np.dot(
                recent,
                weights
            )
        )

        returns = np.diff(
            recent
        ) / recent[:-1]

        drift = float(
            np.median(
                returns
            )
        ) if len(returns) else 0.0

        # Limit runaway forecasts
        drift = float(
            np.clip(
                drift,
                -0.02,
                0.02
            )
        )

        predictions = []

        price = base

        for _ in range(horizon):

            price *= (
                1 + drift
            )

            predictions.append(
                price
            )

        return np.asarray(
            predictions
        )

    # ==========================================================
    # LINEAR REGRESSION
    # ==========================================================

    def _linear_regression_forecast(
        self,
        prices: np.ndarray
    ) -> np.ndarray:

        prices = self._safe_price_array(
            prices
        )

        horizon = self.forecast_horizons[
            "long"
        ]

        if len(prices) < 10:

            return np.full(
                horizon,
                prices[-1]
                if len(prices)
                else 0.0
            )

        window = min(
            60,
            len(prices)
        )

        data = prices[
            -window:
        ]

        X = np.arange(
            len(data),
            dtype=float
        ).reshape(
            -1,
            1
        )

        y = data

        model = LinearRegression()

        model.fit(
            X,
            y
        )

        future_X = np.arange(
            len(data),
            len(data) + horizon
        ).reshape(
            -1,
            1
        )

        predictions = model.predict(
            future_X
        )

        return np.asarray(
            predictions,
            dtype=float
        )

    # ==========================================================
    # RANDOM FOREST
    # ==========================================================

    def _random_forest_forecast(
        self,
        df: pd.DataFrame
    ) -> np.ndarray:

        prices = self._safe_price_array(
            df["Close"]
        )

        horizon = self.forecast_horizons[
            "long"
        ]

        if len(prices) < 50:

            return self._linear_regression_forecast(
                prices
            )

        data = prices[
            -min(200, len(prices)):
        ]

        lookback = min(
            10,
            max(
                5,
                len(data) // 10
            )
        )

        X = []

        y = []

        for i in range(
            lookback,
            len(data)
        ):

            X.append(
                data[
                    i - lookback:i
                ]
            )

            y.append(
                data[i]
            )

        if len(X) < 20:

            return self._linear_regression_forecast(
                prices
            )

        X = np.asarray(
            X,
            dtype=float
        )

        y = np.asarray(
            y,
            dtype=float
        )

        model = RandomForestRegressor(
            n_estimators=100,
            max_depth=8,
            min_samples_leaf=3,
            random_state=self.random_state,
            n_jobs=-1
        )

        model.fit(
            X,
            y
        )

        history = list(
            data[-lookback:]
        )

        predictions = []

        for _ in range(horizon):

            features = np.asarray(
                history[-lookback:]
            ).reshape(
                1,
                -1
            )

            next_price = float(
                model.predict(
                    features
                )[0]
            )

            predictions.append(
                next_price
            )

            history.append(
                next_price
            )

        return np.asarray(
            predictions,
            dtype=float
        )

    # ==========================================================
    # PATTERN RECOGNITION
    # ==========================================================

    def _pattern_recognition_forecast(
        self,
        prices: np.ndarray
    ) -> np.ndarray:

        """
        Pattern recognition yang sudah diperbaiki.

        Sebelumnya:
            pattern['prices'] adalah list

        lalu kemungkinan dipanggil:
            pattern.std()

        Itu menyebabkan:

            'list' object has no attribute 'std'

        Sekarang seluruh pattern selalu diproses
        melalui _safe_price_array().
        """

        prices = self._safe_price_array(
            prices
        )

        horizon = self.forecast_horizons[
            "long"
        ]

        pattern_length = min(
            30,
            len(prices)
        )

        if pattern_length < 10:

            return np.full(
                horizon,
                prices[-1]
            )

        current_pattern = prices[
            -pattern_length:
        ]

        similarities = []

        # ------------------------------------------------------
        # SEARCH DATABASE
        # ------------------------------------------------------

        for pattern in self.pattern_database:

            try:

                historical_pattern = (
                    self._safe_price_array(
                        pattern.get(
                            "prices"
                        )
                    )
                )

                future_prices = (
                    self._safe_price_array(
                        pattern.get(
                            "future_prices"
                        )
                    )
                )

                if (
                    len(historical_pattern)
                    < pattern_length
                    or len(future_prices)
                    < horizon
                ):

                    continue

                historical_pattern = (
                    historical_pattern[
                        :pattern_length
                    ]
                )

                similarity = (
                    self._calculate_pattern_similarity(
                        current_pattern,
                        historical_pattern
                    )
                )

                if not np.isfinite(
                    similarity
                ):

                    continue

                similarities.append(
                    {
                        "similarity": similarity,
                        "future": future_prices[
                            :horizon
                        ]
                    }
                )

            except Exception as e:

                logger.debug(
                    "Skipping invalid pattern: %s",
                    e
                )

        # ------------------------------------------------------
        # NO PATTERN
        # ------------------------------------------------------

        if not similarities:

            return self._pattern_fallback(
                current_pattern,
                horizon
            )

        # ------------------------------------------------------
        # TOP PATTERNS
        # ------------------------------------------------------

        similarities.sort(
            key=lambda x: x["similarity"],
            reverse=True
        )

        top_patterns = similarities[
            :min(
                5,
                len(similarities)
            )
        ]

        weighted_sum = np.zeros(
            horizon,
            dtype=float
        )

        total_weight = 0.0

        for item in top_patterns:

            weight = max(
                0.001,
                float(
                    item["similarity"]
                )
            )

            future = np.asarray(
                item["future"],
                dtype=float
            )

            weighted_sum += (
                future * weight
            )

            total_weight += weight

        if total_weight <= 0:

            return self._pattern_fallback(
                current_pattern,
                horizon
            )

        result = (
            weighted_sum
            / total_weight
        )

        return result

    # ==========================================================
    # PATTERN FALLBACK
    # ==========================================================

    def _pattern_fallback(
        self,
        current_pattern: np.ndarray,
        horizon: int
    ) -> np.ndarray:

        current_pattern = self._safe_price_array(
            current_pattern
        )

        if len(current_pattern) == 0:

            return np.zeros(
                horizon
            )

        current_price = float(
            current_pattern[-1]
        )

        if len(current_pattern) < 5:

            return np.full(
                horizon,
                current_price
            )

        recent_returns = (
            np.diff(current_pattern)
            / current_pattern[:-1]
        )

        momentum = float(
            np.mean(
                recent_returns[-5:]
            )
        )

        momentum = float(
            np.clip(
                momentum,
                -0.01,
                0.01
            )
        )

        predictions = []

        price = current_price

        for _ in range(horizon):

            price *= (
                1 + momentum
            )

            predictions.append(
                price
            )

        return np.asarray(
            predictions
        )

    # ==========================================================
    # PATTERN SIMILARITY
    # ==========================================================

    def _calculate_pattern_similarity(
        self,
        pattern1: Any,
        pattern2: Any
    ) -> float:

        p1 = self._safe_price_array(
            pattern1
        )

        p2 = self._safe_price_array(
            pattern2
        )

        if (
            len(p1) != len(p2)
            or len(p1) < 5
        ):

            return 0.0

        # ------------------------------------------------------
        # Normalize
        # ------------------------------------------------------

        p1_std = float(
            np.std(p1)
        )

        p2_std = float(
            np.std(p2)
        )

        if p1_std <= 1e-12:

            p1_norm = (
                p1 - np.mean(p1)
            )

        else:

            p1_norm = (
                p1 - np.mean(p1)
            ) / p1_std

        if p2_std <= 1e-12:

            p2_norm = (
                p2 - np.mean(p2)
            )

        else:

            p2_norm = (
                p2 - np.mean(p2)
            ) / p2_std

        # ------------------------------------------------------
        # Correlation
        # ------------------------------------------------------

        correlation = np.corrcoef(
            p1_norm,
            p2_norm
        )[0, 1]

        if not np.isfinite(
            correlation
        ):

            correlation = 0.0

        correlation_score = (
            correlation + 1
        ) / 2

        # ------------------------------------------------------
        # Shape
        # ------------------------------------------------------

        shape_similarity = (
            self._compare_pattern_shape(
                p1,
                p2
            )
        )

        # ------------------------------------------------------
        # Return
        # ------------------------------------------------------

        similarity = (
            0.70 * correlation_score
            + 0.30 * shape_similarity
        )

        return float(
            np.clip(
                similarity,
                0.0,
                1.0
            )
        )

    # ==========================================================
    # PATTERN SHAPE
    # ==========================================================

    def _compare_pattern_shape(
        self,
        pattern1: np.ndarray,
        pattern2: np.ndarray
    ) -> float:

        p1 = self._safe_price_array(
            pattern1
        )

        p2 = self._safe_price_array(
            pattern2
        )

        if len(p1) != len(p2):

            return 0.0

        peaks1, _ = find_peaks(
            p1,
            distance=3
        )

        peaks2, _ = find_peaks(
            p2,
            distance=3
        )

        troughs1, _ = find_peaks(
            -p1,
            distance=3
        )

        troughs2, _ = find_peaks(
            -p2,
            distance=3
        )

        # Compare counts
        peak_count_score = (
            1.0
            - min(
                abs(
                    len(peaks1)
                    - len(peaks2)
                ),
                5
            ) / 5.0
        )

        trough_count_score = (
            1.0
            - min(
                abs(
                    len(troughs1)
                    - len(troughs2)
                ),
                5
            ) / 5.0
        )

        count_score = (
            peak_count_score
            + trough_count_score
        ) / 2

        # Compare relative positions
        position_score = 0.5

        if len(peaks1) and len(peaks2):

            n = min(
                len(peaks1),
                len(peaks2)
            )

            pos1 = (
                peaks1[:n]
                / len(p1)
            )

            pos2 = (
                peaks2[:n]
                / len(p2)
            )

            position_score = max(
                0.0,
                1.0
                - float(
                    np.mean(
                        np.abs(
                            pos1 - pos2
                        )
                    )
                )
            )

        return float(
            np.clip(
                0.5 * count_score
                + 0.5 * position_score,
                0.0,
                1.0
            )
        )

    # ==========================================================
    # MONTE CARLO
    # ==========================================================

    def _monte_carlo_forecast(
        self,
        prices: np.ndarray
    ) -> np.ndarray:

        prices = self._safe_price_array(
            prices
        )

        horizon = self.forecast_horizons[
            "long"
        ]

        if len(prices) < 10:

            return np.full(
                horizon,
                prices[-1]
                if len(prices)
                else 0.0
            )

        returns = (
            np.diff(prices)
            / prices[:-1]
        )

        returns = returns[
            np.isfinite(returns)
        ]

        if len(returns) < 10:

            return np.full(
                horizon,
                prices[-1]
            )

        # Log returns lebih stabil
        log_returns = np.log(
            prices[1:]
            / prices[:-1]
        )

        mu = float(
            np.mean(log_returns)
        )

        sigma = float(
            np.std(log_returns)
        )

        sigma = max(
            sigma,
            1e-6
        )

        n_simulations = int(
            self.config.get(
                "monte_carlo_simulations",
                500
            )
        )

        rng = np.random.default_rng(
            self.random_state
        )

        random_returns = rng.normal(
            loc=mu,
            scale=sigma,
            size=(
                n_simulations,
                horizon
            )
        )

        cumulative = np.cumsum(
            random_returns,
            axis=1
        )

        paths = (
            prices[-1]
            * np.exp(
                cumulative
            )
        )

        # Median lebih robust daripada mean
        forecast = np.median(
            paths,
            axis=0
        )

        return np.asarray(
            forecast,
            dtype=float
        )

    # ==========================================================
    # SENTIMENT + TECHNICAL
    # ==========================================================

    def _sentiment_technical_forecast(
        self,
        prices: np.ndarray,
        sentiment_result: Any,
        technical_result: Any
    ) -> np.ndarray:

        prices = self._safe_price_array(
            prices
        )

        horizon = self.forecast_horizons[
            "long"
        ]

        current_price = float(
            prices[-1]
        )

        sentiment_score = (
            self._extract_score(
                sentiment_result,
                [
                    "overall_score",
                    "sentiment_score",
                    "score"
                ]
            )
        )

        technical_score = (
            self._extract_score(
                technical_result,
                [
                    "overall_score",
                    "technical_score",
                    "score"
                ]
            )
        )

        # Assume scores can be:
        # -1 ... +1
        # or
        # 0 ... 1
        sentiment_score = self._normalize_score(
            sentiment_score
        )

        technical_score = self._normalize_score(
            technical_score
        )

        combined_score = (
            sentiment_score * 0.40
            + technical_score * 0.60
        )

        # Historical momentum
        if len(prices) >= 5:

            momentum = (
                prices[-1]
                / prices[-5]
                - 1
            )

        else:

            momentum = 0.0

        # Keep forecast conservative
        momentum = float(
            np.clip(
                momentum,
                -0.03,
                0.03
            )
        )

        predictions = []

        price = current_price

        for i in range(horizon):

            decay = (
                1.0
                / (
                    1.0
                    + i * 0.20
                )
            )

            sentiment_adjustment = (
                combined_score
                * 0.003
                * decay
            )

            momentum_adjustment = (
                momentum
                * 0.20
                * decay
            )

            daily_change = (
                sentiment_adjustment
                + momentum_adjustment
            )

            daily_change = float(
                np.clip(
                    daily_change,
                    -0.02,
                    0.02
                )
            )

            price *= (
                1 + daily_change
            )

            predictions.append(
                price
            )

        return np.asarray(
            predictions
        )

    # ==========================================================
    # SCORE EXTRACTION
    # ==========================================================

    def _extract_score(
        self,
        obj: Any,
        possible_keys: List[str]
    ) -> float:

        if obj is None:

            return 0.0

        for key in possible_keys:

            value = None

            if isinstance(
                obj,
                dict
            ):

                value = obj.get(
                    key
                )

            else:

                value = getattr(
                    obj,
                    key,
                    None
                )

            if value is not None:

                try:

                    value = float(
                        value
                    )

                    if np.isfinite(
                        value
                    ):

                        return value

                except Exception:

                    continue

        return 0.0

    # ==========================================================
    # NORMALIZE SCORE
    # ==========================================================

    @staticmethod
    def _normalize_score(
        score: float
    ) -> float:

        score = float(
            score
        )

        if not np.isfinite(
            score
        ):

            return 0.0

        # Already -1 to 1
        if -1 <= score <= 1:

            return score

        # 0 to 100
        if 0 <= score <= 100:

            return (
                score
                / 50
                - 1
            )

        return float(
            np.clip(
                score,
                -1,
                1
            )
        )

    # ==========================================================
    # ENSEMBLE
    # ==========================================================

    def _ensemble_forecast(
        self,
        predictions: Dict[str, np.ndarray],
        current_price: float,
        horizon: int
    ) -> Tuple[np.ndarray, Dict[str, float]]:

        if not predictions:

            return (
                np.full(
                    horizon,
                    current_price
                ),
                {}
            )

        valid_predictions = {}

        for name, pred in predictions.items():

            arr = np.asarray(
                pred,
                dtype=float
            ).reshape(-1)

            if len(arr) != horizon:

                continue

            if not np.all(
                np.isfinite(arr)
            ):

                continue

            if np.any(
                arr <= 0
            ):

                continue

            valid_predictions[
                name
            ] = arr

        if not valid_predictions:

            return (
                np.full(
                    horizon,
                    current_price
                ),
                {}
            )

        raw_weights = {}

        for name in valid_predictions:

            weight = float(
                self.model_weights.get(
                    name,
                    0.10
                )
            )

            raw_weights[name] = max(
                0.0,
                weight
            )

        total_weight = sum(
            raw_weights.values()
        )

        if total_weight <= 0:

            equal_weight = (
                1.0
                / len(valid_predictions)
            )

            weights = {
                name: equal_weight
                for name
                in valid_predictions
            }

        else:

            weights = {
                name: weight / total_weight
                for name, weight
                in raw_weights.items()
            }

        ensemble = np.zeros(
            horizon,
            dtype=float
        )

        for name, pred in valid_predictions.items():

            ensemble += (
                pred
                * weights[name]
            )

        # ------------------------------------------------------
        # Sanity clamp
        # ------------------------------------------------------

        # Prevent model ensemble from exploding.
        max_daily_move = float(
            self.config.get(
                "max_forecast_daily_move",
                0.05
            )
        )

        for i in range(
            len(ensemble)
        ):

            previous = (
                current_price
                if i == 0
                else ensemble[i - 1]
            )

            lower = (
                previous
                * (
                    1
                    - max_daily_move
                )
            )

            upper = (
                previous
                * (
                    1
                    + max_daily_move
                )
            )

            ensemble[i] = float(
                np.clip(
                    ensemble[i],
                    lower,
                    upper
                )
            )

        return (
            ensemble,
            weights
        )

    # ==========================================================
    # SANITIZE PREDICTION
    # ==========================================================

    @staticmethod
    def _sanitize_prediction(
        prediction: Any,
        current_price: float,
        horizon: int
    ) -> np.ndarray:

        arr = np.asarray(
            prediction,
            dtype=float
        ).reshape(-1)

        arr = arr[
            np.isfinite(arr)
        ]

        arr = arr[
            arr > 0
        ]

        if len(arr) == 0:

            return np.full(
                horizon,
                current_price
            )

        if len(arr) < horizon:

            last = arr[-1]

            arr = np.pad(
                arr,
                (
                    0,
                    horizon - len(arr)
                ),
                mode="constant",
                constant_values=last
            )

        if len(arr) > horizon:

            arr = arr[
                :horizon
            ]

        return arr.astype(
            float
        )

    # ==========================================================
    # SCENARIOS
    # ==========================================================

    def _generate_scenarios(
        self,
        current_price: float,
        ensemble_pred: np.ndarray,
        predictions: Dict[str, np.ndarray],
        prices: np.ndarray
    ) -> Dict[str, Any]:

        horizon = len(
            ensemble_pred
        )

        if not predictions:

            bullish = (
                ensemble_pred
                * 1.03
            )

            bearish = (
                ensemble_pred
                * 0.97
            )

        else:

            stacked = np.vstack(
                list(
                    predictions.values()
                )
            )

            model_high = np.percentile(
                stacked,
                80,
                axis=0
            )

            model_low = np.percentile(
                stacked,
                20,
                axis=0
            )

            bullish = np.maximum(
                model_high,
                ensemble_pred
            )

            bearish = np.minimum(
                model_low,
                ensemble_pred
            )

        # ------------------------------------------------------
        # Volatility adjustment
        # ------------------------------------------------------

        if len(prices) >= 10:

            returns = (
                np.diff(prices)
                / prices[:-1]
            )

            volatility = float(
                np.std(
                    returns
                )
            )

        else:

            volatility = 0.02

        volatility = float(
            np.clip(
                volatility,
                0.005,
                0.10
            )
        )

        bullish = bullish * (
            1
            + volatility * 0.25
        )

        bearish = bearish * (
            1
            - volatility * 0.25
        )

        bullish = np.maximum(
            bullish,
            ensemble_pred
        )

        bearish = np.minimum(
            bearish,
            ensemble_pred
        )

        # ------------------------------------------------------
        # Model agreement
        # ------------------------------------------------------

        if len(predictions) >= 2:

            stacked = np.vstack(
                list(
                    predictions.values()
                )
            )

            relative_std = (
                np.std(
                    stacked,
                    axis=0
                )
                / np.maximum(
                    np.mean(
                        stacked,
                        axis=0
                    ),
                    1e-9
                )
            )

            agreement = float(
                np.clip(
                    1
                    - np.mean(
                        relative_std
                    ) * 10,
                    0,
                    1
                )
            )

        else:

            agreement = 0.25

        most_likely_prob = float(
            np.clip(
                0.40
                + agreement * 0.25,
                0.40,
                0.65
            )
        )

        remaining = (
            1
            - most_likely_prob
        )

        bullish_prob = (
            remaining
            * 0.55
        )

        bearish_prob = (
            remaining
            * 0.45
        )

        return {
            "bullish": bullish,
            "bearish": bearish,
            "most_likely": ensemble_pred,
            "bullish_prob": bullish_prob,
            "bearish_prob": bearish_prob,
            "most_likely_prob": most_likely_prob,
            "agreement": agreement,
        }

    # ==========================================================
    # TREND ANALYSIS
    # ==========================================================

    def _analyze_trend(
        self,
        prices: np.ndarray
    ) -> Tuple[str, float]:

        prices = self._safe_price_array(
            prices
        )

        if len(prices) < 20:

            return (
                "CONSOLIDATING",
                0.0
            )

        ma20 = float(
            np.mean(
                prices[-20:]
            )
        )

        ma50 = float(
            np.mean(
                prices[
                    -min(
                        50,
                        len(prices)
                    ):
                ]
            )
        )

        current_price = float(
            prices[-1]
        )

        # ------------------------------------------------------
        # Trend score
        # ------------------------------------------------------

        bullish_components = 0

        bearish_components = 0

        if current_price > ma20:

            bullish_components += 1

        else:

            bearish_components += 1

        if ma20 > ma50:

            bullish_components += 1

        else:

            bearish_components += 1

        # Linear slope
        window = prices[
            -min(
                30,
                len(prices)
            ):
        ]

        x = np.arange(
            len(window)
        )

        slope = np.polyfit(
            x,
            window,
            1
        )[0]

        normalized_slope = (
            slope
            / max(
                np.mean(window),
                1e-9
            )
        )

        if normalized_slope > 0:

            bullish_components += 1

        elif normalized_slope < 0:

            bearish_components += 1

        if (
            bullish_components
            >= 2
        ):

            trend = "BULLISH"

        elif (
            bearish_components
            >= 2
        ):

            trend = "BEARISH"

        else:

            trend = "CONSOLIDATING"

        # ------------------------------------------------------
        # Strength
        # ------------------------------------------------------

        distance_ma20 = abs(
            current_price
            - ma20
        ) / max(
            ma20,
            1e-9
        )

        distance_ma50 = abs(
            ma20
            - ma50
        ) / max(
            ma50,
            1e-9
        )

        slope_strength = min(
            abs(
                normalized_slope
            ) * 100,
            1.0
        )

        strength = (
            distance_ma20 * 2
            + distance_ma50 * 2
            + slope_strength
        ) / 5

        return (
            trend,
            float(
                np.clip(
                    strength,
                    0,
                    1
                )
            )
        )

    # ==========================================================
    # NEXT MOVE
    # ==========================================================

    def _predict_next_move(
        self,
        prices: np.ndarray,
        ensemble_pred: np.ndarray
    ) -> Dict[str, float]:

        prices = self._safe_price_array(
            prices
        )

        if (
            len(prices) < 5
            or len(ensemble_pred) == 0
        ):

            return {
                "UP": 0.33,
                "DOWN": 0.33,
                "SIDEWAYS": 0.34
            }

        current = float(
            prices[-1]
        )

        predicted = float(
            ensemble_pred[0]
        )

        predicted_change = (
            predicted
            / current
            - 1
        )

        historical_momentum = (
            prices[-1]
            / prices[-5]
            - 1
        )

        combined = (
            predicted_change * 0.60
            + historical_momentum * 0.40
        )

        threshold = 0.002

        if combined > threshold:

            up = float(
                np.clip(
                    0.50
                    + combined * 8,
                    0.35,
                    0.75
                )
            )

            down = 0.15

            sideways = (
                1
                - up
                - down
            )

        elif combined < -threshold:

            down = float(
                np.clip(
                    0.50
                    - combined * 8,
                    0.35,
                    0.75
                )
            )

            up = 0.15

            sideways = (
                1
                - up
                - down
            )

        else:

            up = 0.30

            down = 0.30

            sideways = 0.40

        probabilities = np.array(
            [
                up,
                down,
                sideways
            ],
            dtype=float
        )

        probabilities /= (
            probabilities.sum()
        )

        return {
            "UP": float(
                probabilities[0]
            ),
            "DOWN": float(
                probabilities[1]
            ),
            "SIDEWAYS": float(
                probabilities[2]
            )
        }

    # ==========================================================
    # PRICE PREDICTION OBJECT
    # ==========================================================

    def _create_price_prediction(
        self,
        ensemble_pred: np.ndarray,
        horizon: str,
        current_price: float
    ) -> PricePrediction:

        days = int(
            self.forecast_horizons.get(
                horizon,
                2
            )
        )

        idx = min(
            days - 1,
            len(ensemble_pred) - 1
        )

        idx = max(
            0,
            idx
        )

        predicted_price = float(
            ensemble_pred[idx]
            if len(ensemble_pred)
            else current_price
        )

        change_percent = (
            (
                predicted_price
                / current_price
                - 1
            )
            * 100
            if current_price > 0
            else 0.0
        )

        # Confidence decreases with horizon
        base_confidence = (
            self.BASE_CONFIDENCE.get(
                horizon,
                0.50
            )
        )

        # Keep confidence realistic
        confidence = float(
            np.clip(
                base_confidence,
                0.20,
                0.90
            )
        )

        # Interval based on predicted move
        spread = max(
            abs(
                predicted_price
                - current_price
            )
            * 0.35,
            current_price * 0.005
        )

        return PricePrediction(

            timestamp=(
                datetime.now(
                    timezone.utc
                )
                + timedelta(
                    days=days
                )
            ),

            predicted_price=predicted_price,

            confidence_interval_lower=max(
                0.0,
                predicted_price
                - spread
            ),

            confidence_interval_upper=(
                predicted_price
                + spread
            ),

            confidence=confidence,

            horizon=horizon.upper(),

            predicted_change_percent=float(
                change_percent
            )
        )

    # ==========================================================
    # KEY LEVELS
    # ==========================================================

    def _find_key_levels(
        self,
        df: pd.DataFrame,
        current_price: float
    ) -> Tuple[
        List[float],
        List[float]
    ]:

        prices = self._safe_price_array(
            df["Close"]
        )

        if len(prices) < 20:

            return (
                [],
                []
            )

        # ------------------------------------------------------
        # Use High / Low if available
        # ------------------------------------------------------

        if (
            "High" in df.columns
            and "Low" in df.columns
        ):

            high = pd.to_numeric(
                df["High"],
                errors="coerce"
            ).to_numpy(
                dtype=float
            )

            low = pd.to_numeric(
                df["Low"],
                errors="coerce"
            ).to_numpy(
                dtype=float
            )

            valid = (
                np.isfinite(high)
                & np.isfinite(low)
            )

            high = high[valid]

            low = low[valid]

        else:

            high = prices.copy()

            low = prices.copy()

        # Limit to recent data
        high = high[
            -min(
                120,
                len(high)
            ):
        ]

        low = low[
            -min(
                120,
                len(low)
            ):
        ]

        peaks, _ = find_peaks(
            high,
            distance=5
        )

        troughs, _ = find_peaks(
            -low,
            distance=5
        )

        resistance_candidates = [
            float(
                high[i]
            )
            for i in peaks
            if high[i] > current_price
        ]

        support_candidates = [
            float(
                low[i]
            )
            for i in troughs
            if low[i] < current_price
        ]

        resistance = self._cluster_levels(
            resistance_candidates
        )

        support = self._cluster_levels(
            support_candidates
        )

        # Closest first
        resistance.sort(
            key=lambda x: abs(
                x - current_price
            )
        )

        support.sort(
            key=lambda x: abs(
                x - current_price
            )
        )

        return (
            support[:3],
            resistance[:3]
        )

    # ==========================================================
    # CLUSTER LEVELS
    # ==========================================================

    def _cluster_levels(
        self,
        levels: List[float],
        tolerance: float = 0.015
    ) -> List[float]:

        if not levels:

            return []

        clean = []

        for level in levels:

            try:

                value = float(
                    level
                )

                if (
                    np.isfinite(value)
                    and value > 0
                ):

                    clean.append(
                        value
                    )

            except Exception:

                continue

        if not clean:

            return []

        clean.sort()

        clusters = [
            [clean[0]]
        ]

        for level in clean[1:]:

            cluster = clusters[-1]

            average = (
                sum(cluster)
                / len(cluster)
            )

            if (
                abs(
                    level
                    - average
                )
                / max(
                    average,
                    1e-9
                )
                <= tolerance
            ):

                cluster.append(
                    level
                )

            else:

                clusters.append(
                    [level]
                )

        return [
            float(
                sum(cluster)
                / len(cluster)
            )
            for cluster in clusters
        ]

    # ==========================================================
    # EXPECTED RANGE
    # ==========================================================

    def _calculate_expected_range(
        self,
        predictions: Dict[str, np.ndarray],
        current_price: float,
        prices: np.ndarray
    ) -> Tuple[
        float,
        float
    ]:

        candidates = []

        for pred in predictions.values():

            arr = np.asarray(
                pred,
                dtype=float
            )

            arr = arr[
                np.isfinite(arr)
            ]

            arr = arr[
                arr > 0
            ]

            if len(arr):

                candidates.extend(
                    arr.tolist()
                )

        if not candidates:

            return (
                current_price * 1.03,
                current_price * 0.97
            )

        predicted_high = max(
            candidates
        )

        predicted_low = min(
            candidates
        )

        # Historical volatility
        if len(prices) >= 10:

            returns = (
                np.diff(prices)
                / prices[:-1]
            )

            volatility = float(
                np.std(
                    returns
                )
            )

        else:

            volatility = 0.02

        volatility = float(
            np.clip(
                volatility,
                0.005,
                0.10
            )
        )

        buffer = (
            current_price
            * volatility
            * 0.50
        )

        expected_high = max(
            predicted_high
            + buffer,
            current_price
        )

        expected_low = max(
            0.0,
            min(
                predicted_low
                - buffer,
                current_price
            )
        )

        return (
            float(expected_high),
            float(expected_low)
        )

    # ==========================================================
    # DATA QUALITY
    # ==========================================================

    def _calculate_data_quality(
        self,
        prices: np.ndarray
    ) -> Dict[str, Any]:

        prices = self._safe_price_array(
            prices
        )

        if len(prices) < 2:

            return {
                "observations": len(prices),
                "return_volatility": 0.0,
                "missing_ratio": 0.0,
                "quality_score": 0.0
            }

        returns = (
            np.diff(prices)
            / prices[:-1]
        )

        returns = returns[
            np.isfinite(returns)
        ]

        volatility = (
            float(
                np.std(
                    returns
                )
            )
            if len(returns)
            else 0.0
        )

        quality = 1.0

        if len(prices) < 50:

            quality -= 0.25

        if volatility > 0.10:

            quality -= 0.15

        quality = float(
            np.clip(
                quality,
                0,
                1
            )
        )

        return {
            "observations": int(
                len(prices)
            ),
            "return_volatility": volatility,
            "missing_ratio": 0.0,
            "quality_score": quality
        }

    # ==========================================================
    # SUMMARY
    # ==========================================================

    def _generate_summary(
        self,
        symbol: str,
        current_price: float,
        trend: str,
        trend_strength: float,
        ensemble_pred: np.ndarray,
        short_pred: PricePrediction,
        scenarios: Dict[str, Any],
        data_quality: Dict[str, Any]
    ) -> str:

        symbol_name = (
            symbol
            .replace("-USD", "")
            .replace("-USDT", "")
        )

        short_change = (
            short_pred.predicted_change_percent
        )

        if trend == "BULLISH":

            trend_text = (
                f"Trend BULLISH "
                f"dengan strength "
                f"{trend_strength:.1%}."
            )

        elif trend == "BEARISH":

            trend_text = (
                f"Trend BEARISH "
                f"dengan strength "
                f"{trend_strength:.1%}."
            )

        else:

            trend_text = (
                "Trend berada dalam "
                "fase CONSOLIDATING."
            )

        if short_change > 1:

            direction_text = (
                f"Model ensemble memperkirakan "
                f"kenaikan sekitar "
                f"{short_change:.2f}% "
                f"pada horizon pendek."
            )

        elif short_change < -1:

            direction_text = (
                f"Model ensemble memperkirakan "
                f"penurunan sekitar "
                f"{abs(short_change):.2f}% "
                f"pada horizon pendek."
            )

        else:

            direction_text = (
                "Model ensemble memperkirakan "
                "pergerakan relatif terbatas "
                "pada horizon pendek."
            )

        agreement = scenarios.get(
            "agreement",
            0.0
        )

        return (
            f"Forecast {symbol_name}: "
            f"harga saat ini "
            f"${current_price:.2f}. "
            f"{trend_text} "
            f"{direction_text} "
            f"Prediksi jangka pendek "
            f"${short_pred.predicted_price:.2f}. "
            f"Model agreement "
            f"{agreement:.1%}. "
            f"Data quality "
            f"{data_quality.get('quality_score', 0):.1%}."
        )

    # ==========================================================
    # RECOMMENDATIONS
    # ==========================================================

    def _generate_recommendations(
        self,
        trend: str,
        trend_strength: float,
        ensemble_pred: np.ndarray,
        short_pred: PricePrediction,
        support: List[float],
        resistance: List[float],
        next_move_probability: Dict[str, float]
    ) -> List[str]:

        recommendations = []

        up_prob = next_move_probability.get(
            "UP",
            0.33
        )

        down_prob = next_move_probability.get(
            "DOWN",
            0.33
        )

        sideways_prob = next_move_probability.get(
            "SIDEWAYS",
            0.34
        )

        # ------------------------------------------------------
        # Trend
        # ------------------------------------------------------

        if trend == "BULLISH":

            recommendations.append(
                "Trend bullish; BUY hanya "
                "jika Risk Engine dan Decision "
                "Engine memberikan approval."
            )

        elif trend == "BEARISH":

            recommendations.append(
                "Trend bearish; hindari entry "
                "agresif sebelum confirmation."
            )

        else:

            recommendations.append(
                "Trend konsolidasi; tunggu "
                "confirmation sebelum entry."
            )

        # ------------------------------------------------------
        # Probability
        # ------------------------------------------------------

        if up_prob > 0.55:

            recommendations.append(
                f"Probability UP cukup dominan "
                f"({up_prob:.1%})."
            )

        elif down_prob > 0.55:

            recommendations.append(
                f"Probability DOWN cukup dominan "
                f"({down_prob:.1%})."
            )

        else:

            recommendations.append(
                f"Directional confidence rendah; "
                f"SIDEWAYS={sideways_prob:.1%}."
            )

        # ------------------------------------------------------
        # Support
        # ------------------------------------------------------

        if support:

            recommendations.append(
                f"Support terdekat: "
                f"${support[0]:.2f}."
            )

        # ------------------------------------------------------
        # Resistance
        # ------------------------------------------------------

        if resistance:

            recommendations.append(
                f"Resistance terdekat: "
                f"${resistance[0]:.2f}."
            )

        # ------------------------------------------------------
        # Forecast
        # ------------------------------------------------------

        if abs(
            short_pred.predicted_change_percent
        ) < 1:

            recommendations.append(
                "Forecast jangka pendek relatif "
                "sempit; hindari overtrading."
            )

        return recommendations[:5]

    # ==========================================================
    # PATTERN DATABASE
    # ==========================================================

    def _initialize_pattern_database(self):

        """
        Pattern database demo.

        Pattern dibuat dalam normalized shape agar tidak
        bergantung pada harga absolut.

        Penting:
            Pattern ini hanya fallback/demo.
            Dalam production sebaiknya database pattern
            dibangun dari historical market data aktual.
        """

        self.pattern_database = [

            {
                "prices": [
                    100, 101, 102, 103, 102,
                    104, 105, 106, 108, 107,
                    109, 110, 111, 113, 112,
                    114, 115, 116, 118, 119,
                    118, 120, 121, 123, 124,
                    123, 125, 126, 128, 129
                ],

                "future_prices": [
                    130,
                    131,
                    133,
                    134,
                    136,
                    137,
                    139
                ]
            },

            {
                "prices": [
                    200, 199, 198, 197, 196,
                    197, 195, 194, 193, 192,
                    191, 190, 191, 189, 188,
                    187, 186, 185, 184, 185,
                    183, 182, 181, 180, 179,
                    178, 179, 177, 176, 175
                ],

                "future_prices": [
                    174,
                    173,
                    171,
                    170,
                    169,
                    168,
                    166
                ]
            }

        ]

    # ==========================================================
    # DEFAULT FORECAST
    # ==========================================================

    def _get_default_forecast(
        self,
        symbol: str,
        market_data: Optional[Dict[str, Any]] = None,
        current_price: Optional[float] = None
    ) -> ForecastResult:

        if current_price is None:

            current_price = 0.0

            if isinstance(
                market_data,
                dict
            ):

                try:

                    current_price = float(
                        market_data.get(
                            "current_price",
                            market_data.get(
                                "price",
                                0.0
                            )
                        )
                    )

                except Exception:

                    current_price = 0.0

        current_price = max(
            0.0,
            current_price
        )

        now = datetime.now(
            timezone.utc
        )

        def default_prediction(
            days: int,
            horizon: str
        ):

            return PricePrediction(

                timestamp=(
                    now
                    + timedelta(
                        days=days
                    )
                ),

                predicted_price=current_price,

                confidence_interval_lower=(
                    current_price
                ),

                confidence_interval_upper=(
                    current_price
                ),

                confidence=0.0,

                horizon=horizon,

                predicted_change_percent=0.0
            )

        return ForecastResult(

            symbol=symbol,

            timestamp=now,

            current_price=current_price,

            short_term=default_prediction(
                2,
                "SHORT"
            ),

            medium_term=default_prediction(
                5,
                "MEDIUM"
            ),

            long_term=default_prediction(
                7,
                "LONG"
            ),

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
                    "probability": 0.25
                },

                "bearish": {
                    "path": [
                        current_price
                    ] * 7,
                    "probability": 0.25
                },

                "most_likely": {
                    "path": [
                        current_price
                    ] * 7,
                    "probability": 0.50
                }
            },

            primary_trend="CONSOLIDATING",

            trend_strength=0.0,

            next_move_probability={
                "UP": 0.33,
                "DOWN": 0.33,
                "SIDEWAYS": 0.34
            },

            expected_high=current_price,

            expected_low=current_price,

            expected_range={
                "high": current_price,
                "low": current_price,
                "range_percent": 0.0
            },

            key_resistance=[],

            key_support=[],

            summary=(
                "Forecast unavailable. "
                "System fallback to neutral."
            ),

            recommendations=[
                "Wait for sufficient market data."
            ],

            model_predictions={},

            model_weights={},

            model_status={},

            data_quality={
                "observations": 0,
                "return_volatility": 0.0,
                "missing_ratio": 0.0,
                "quality_score": 0.0
            },

            warnings=[
                "Forecast fallback activated."
            ]
        )


# ==============================================================
# STANDALONE TEST
# ==============================================================


def print_forecast_result(
    result: ForecastResult
):

    print()
    print("=" * 70)
    print(
        f"FORECAST RESULT | {result.symbol}"
    )
    print("=" * 70)

    print(
        f"Current Price : "
        f"${result.current_price:,.2f}"
    )

    print(
        f"Trend         : "
        f"{result.primary_trend}"
    )

    print(
        f"Trend Strength: "
        f"{result.trend_strength:.2%}"
    )

    print()
    print("PRICE FORECAST")
    print("-" * 70)

    print(
        f"Short  (2D): "
        f"${result.short_term.predicted_price:,.2f} "
        f"({result.short_term.predicted_change_percent:+.2f}%)"
    )

    print(
        f"Medium (5D): "
        f"${result.medium_term.predicted_price:,.2f} "
        f"({result.medium_term.predicted_change_percent:+.2f}%)"
    )

    print(
        f"Long   (7D): "
        f"${result.long_term.predicted_price:,.2f} "
        f"({result.long_term.predicted_change_percent:+.2f}%)"
    )

    print()
    print("NEXT MOVE PROBABILITY")
    print("-" * 70)

    for direction, probability in (
        result.next_move_probability.items()
    ):

        print(
            f"{direction:<10}: "
            f"{probability:.2%}"
        )

    print()
    print("EXPECTED RANGE")
    print("-" * 70)

    print(
        f"High: "
        f"${result.expected_high:,.2f}"
    )

    print(
        f"Low : "
        f"${result.expected_low:,.2f}"
    )

    print(
        f"Range: "
        f"{result.expected_range['range_percent']:.2f}%"
    )

    print()
    print("KEY LEVELS")
    print("-" * 70)

    if result.key_support:

        print(
            "Support    : "
            + ", ".join(
                f"${x:,.2f}"
                for x in result.key_support
            )
        )

    else:

        print(
            "Support    : None"
        )

    if result.key_resistance:

        print(
            "Resistance  : "
            + ", ".join(
                f"${x:,.2f}"
                for x in result.key_resistance
            )
        )

    else:

        print(
            "Resistance  : None"
        )

    print()
    print("MODEL STATUS")
    print("-" * 70)

    for model, status in (
        result.model_status.items()
    ):

        print(
            f"{model:<25}: {status}"
        )

    print()
    print("MODEL WEIGHTS")
    print("-" * 70)

    for model, weight in (
        result.model_weights.items()
    ):

        print(
            f"{model:<25}: {weight:.2%}"
        )

    print()
    print("DATA QUALITY")
    print("-" * 70)

    print(
        f"Observations : "
        f"{result.data_quality.get('observations', 0)}"
    )

    print(
        f"Volatility   : "
        f"{result.data_quality.get('return_volatility', 0):.2%}"
    )

    print(
        f"Quality      : "
        f"{result.data_quality.get('quality_score', 0):.2%}"
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


# ==============================================================
# MAIN
# ==============================================================


def main():

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "%(message)s"
        )
    )

    print()
    print("=" * 70)
    print(
        "AI TRADING FORECAST AGENT v4 TEST"
    )
    print("=" * 70)

    agent = ForecastAgent(
        {
            "history_period": "1y",
            "history_interval": "1d",
            "monte_carlo_simulations": 500,
            "random_state": 42,
            "enable_cache": True
        }
    )

    result = agent.analyze(
        "BTC-USD"
    )

    print_forecast_result(
        result
    )


if __name__ == "__main__":

    main()
