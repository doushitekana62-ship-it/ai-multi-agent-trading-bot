"""
Agent 5: Forecasting Pergerakan Harga - V4

Design goals:
- Robust multi-model forecasting
- Model sanity validation
- Dynamic model weighting
- No synthetic/dummy price patterns
- Pattern recognition menggunakan historical relative returns
- Volatility-aware forecast scoring
- Direction dan tradeability dipisahkan
- Tidak menghasilkan STRONG_BUY/STRONG_SELL hanya karena
  predicted price bergerak sedikit
- ForecastResult tetap kompatibel dengan Orchestrator lama
"""

import logging
import warnings
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd
import yfinance as yf

from scipy.signal import find_peaks
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor

warnings.filterwarnings("ignore")

logger = logging.getLogger(__name__)


# ============================================================
# DATA CLASSES
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

    # --------------------------------------------------------
    # V4 diagnostic / orchestration fields
    # --------------------------------------------------------
    model_predictions: Dict[str, List[float]]
    model_weights: Dict[str, float]
    model_status: Dict[str, str]

    data_quality: Dict[str, float]

    model_agreement: float
    forecast_score: float
    forecast_action: str

    warnings: List[str]


# ============================================================
# FORECAST AGENT
# ============================================================

class ForecastAgent:

    def __init__(self, config: Dict = None):

        self.config = config or {}

        # ----------------------------------------------------
        # Horizons
        # ----------------------------------------------------
        self.forecast_horizons = {
            "short": 2,
            "medium": 5,
            "long": 7
        }

        # ----------------------------------------------------
        # Base weights
        #
        # These are NOT final weights.
        # They are starting reliability priors.
        # ----------------------------------------------------
        self.base_model_weights = {
            "arima": 0.20,
            "linear_regression": 0.12,
            "random_forest": 0.20,
            "pattern_recognition": 0.13,
            "monte_carlo": 0.15,
            "sentiment_technical": 0.20,
        }

        self.model_weights = dict(self.base_model_weights)

        # ----------------------------------------------------
        # Validation
        # ----------------------------------------------------
        self.max_reasonable_move = float(
            self.config.get("max_reasonable_move", 0.15)
        )

        self.pattern_window = int(
            self.config.get("pattern_window", 30)
        )

        self.min_pattern_history = int(
            self.config.get("min_pattern_history", 90)
        )

        # ----------------------------------------------------
        # Cache
        # ----------------------------------------------------
        self.cache = {}
        self.cache_duration = timedelta(
            minutes=int(self.config.get("cache_minutes", 10))
        )

        logger.info("Forecast Agent initialized successfully")

    # ========================================================
    # MAIN ANALYZE
    # ========================================================

    def analyze(
        self,
        symbol: str,
        sentiment_result: Any = None,
        technical_result: Any = None,
        market_data: Dict = None
    ) -> ForecastResult:

        logger.info(f"Generating forecast for {symbol}")

        cache_key = f"forecast_{symbol}"

        # ----------------------------------------------------
        # Cache
        # ----------------------------------------------------
        if cache_key in self.cache:

            cached_result, cache_time = self.cache[cache_key]

            if (
                datetime.now(timezone.utc) - cache_time
                < self.cache_duration
            ):
                logger.info(
                    f"Using cached forecast for {symbol}"
                )
                return cached_result

        warnings_list: List[str] = []

        try:

            # ------------------------------------------------
            # Fetch data
            # ------------------------------------------------
            df = self._fetch_historical_data(symbol)

            if df is None or len(df) < 80:

                warnings_list.append(
                    "Insufficient historical data"
                )

                return self._get_default_forecast(
                    symbol,
                    reason="Insufficient historical data"
                )

            # ------------------------------------------------
            # Clean OHLCV
            # ------------------------------------------------
            df = self._clean_market_data(df)

            prices = (
                pd.to_numeric(
                    df["Close"],
                    errors="coerce"
                )
                .dropna()
                .astype(float)
                .values
            )

            if len(prices) < 80:

                warnings_list.append(
                    "Insufficient valid closing prices"
                )

                return self._get_default_forecast(
                    symbol,
                    reason="Insufficient valid price data"
                )

            # ------------------------------------------------
            # Reference price
            #
            # If caller explicitly provides current_price,
            # use it. Otherwise use latest OHLC close.
            # ------------------------------------------------
            current_price = self._resolve_current_price(
                df,
                market_data
            )

            if current_price <= 0:

                warnings_list.append(
                    "Invalid current price"
                )

                return self._get_default_forecast(
                    symbol,
                    reason="Invalid current price"
                )

            # ------------------------------------------------
            # Data quality
            # ------------------------------------------------
            data_quality = self._calculate_data_quality(
                df,
                prices
            )

            if data_quality["quality_score"] < 0.70:

                warnings_list.append(
                    "Historical data quality is below preferred threshold"
                )

            # ------------------------------------------------
            # Historical volatility
            # ------------------------------------------------
            returns = self._calculate_returns(prices)

            volatility = self._annualized_or_daily_volatility(
                returns
            )

            # ------------------------------------------------
            # Model predictions
            # ------------------------------------------------
            raw_predictions: Dict[str, np.ndarray] = {}
            model_status: Dict[str, str] = {}

            # =================================================
            # 1. ARIMA-LIKE / AR(2)
            # =================================================
            raw_predictions["arima"] = (
                self._safe_model_call(
                    "arima",
                    lambda: self._arima_forecast(
                        prices,
                        self.forecast_horizons["long"]
                    ),
                    current_price,
                    model_status,
                    warnings_list
                )
            )

            # =================================================
            # 2. LINEAR REGRESSION
            # =================================================
            raw_predictions["linear_regression"] = (
                self._safe_model_call(
                    "linear_regression",
                    lambda: self._linear_regression_forecast(
                        prices
                    ),
                    current_price,
                    model_status,
                    warnings_list
                )
            )

            # =================================================
            # 3. RANDOM FOREST
            # =================================================
            raw_predictions["random_forest"] = (
                self._safe_model_call(
                    "random_forest",
                    lambda: self._random_forest_forecast(
                        df
                    ),
                    current_price,
                    model_status,
                    warnings_list
                )
            )

            # =================================================
            # 4. PATTERN RECOGNITION
            # =================================================
            raw_predictions["pattern_recognition"] = (
                self._safe_model_call(
                    "pattern_recognition",
                    lambda: self._pattern_recognition_forecast(
                        prices
                    ),
                    current_price,
                    model_status,
                    warnings_list
                )
            )

            # =================================================
            # 5. MONTE CARLO
            # =================================================
            raw_predictions["monte_carlo"] = (
                self._safe_model_call(
                    "monte_carlo",
                    lambda: self._monte_carlo_forecast(
                        prices
                    ),
                    current_price,
                    model_status,
                    warnings_list
                )
            )

            # =================================================
            # 6. SENTIMENT + TECHNICAL
            # =================================================
            if (
                sentiment_result is not None
                and technical_result is not None
            ):

                raw_predictions["sentiment_technical"] = (
                    self._safe_model_call(
                        "sentiment_technical",
                        lambda: self._sentiment_technical_forecast(
                            prices,
                            sentiment_result,
                            technical_result
                        ),
                        current_price,
                        model_status,
                        warnings_list
                    )
                )

            else:

                model_status["sentiment_technical"] = "SKIPPED"

            # ------------------------------------------------
            # Validate predictions
            # ------------------------------------------------
            validated_predictions = {}

            for model_name, prediction in raw_predictions.items():

                if prediction is None:
                    continue

                clean_prediction = self._validate_prediction(
                    prediction,
                    current_price,
                    model_name,
                    warnings_list
                )

                if clean_prediction is not None:

                    validated_predictions[
                        model_name
                    ] = clean_prediction

                    model_status[model_name] = "OK"

                else:

                    model_status[model_name] = "REJECTED"

            # ------------------------------------------------
            # Need at least one model
            # ------------------------------------------------
            if not validated_predictions:

                warnings_list.append(
                    "All forecasting models failed validation"
                )

                return self._get_default_forecast(
                    symbol,
                    current_price=current_price,
                    reason="All forecast models rejected"
                )

            # ------------------------------------------------
            # Dynamic weights
            # ------------------------------------------------
            dynamic_weights = (
                self._calculate_dynamic_weights(
                    validated_predictions,
                    current_price,
                    volatility,
                    data_quality["quality_score"]
                )
            )

            self.model_weights = dynamic_weights

            # ------------------------------------------------
            # Ensemble
            # ------------------------------------------------
            ensemble_prediction = self._ensemble_forecast(
                validated_predictions,
                dynamic_weights,
                current_price
            )

            # ------------------------------------------------
            # Final ensemble validation
            # ------------------------------------------------
            ensemble_prediction = self._repair_prediction_path(
                ensemble_prediction,
                current_price
            )

            # ------------------------------------------------
            # Model agreement
            # ------------------------------------------------
            model_agreement = (
                self._calculate_model_agreement(
                    validated_predictions,
                    current_price
                )
            )

            # ------------------------------------------------
            # Trend
            # ------------------------------------------------
            primary_trend, trend_strength = (
                self._analyze_trend(prices)
            )

            # ------------------------------------------------
            # Probability
            # ------------------------------------------------
            next_move_probability = (
                self._predict_next_move(
                    prices=prices,
                    ensemble_pred=ensemble_prediction,
                    volatility=volatility,
                    model_agreement=model_agreement
                )
            )

            # ------------------------------------------------
            # Scenario generation
            # ------------------------------------------------
            scenarios = self._generate_scenarios(
                current_price=current_price,
                ensemble_pred=ensemble_prediction,
                predictions=validated_predictions,
                volatility=volatility,
                model_agreement=model_agreement,
                trend=primary_trend
            )

            # ------------------------------------------------
            # Price predictions
            # ------------------------------------------------
            short_pred = self._create_price_prediction(
                ensemble_prediction,
                "short",
                current_price,
                volatility,
                model_agreement
            )

            medium_pred = self._create_price_prediction(
                ensemble_prediction,
                "medium",
                current_price,
                volatility,
                model_agreement
            )

            long_pred = self._create_price_prediction(
                ensemble_prediction,
                "long",
                current_price,
                volatility,
                model_agreement
            )

            # ------------------------------------------------
            # Support / resistance
            # ------------------------------------------------
            key_support, key_resistance = (
                self._find_key_levels(df)
            )

            # ------------------------------------------------
            # Expected range
            # ------------------------------------------------
            expected_high, expected_low = (
                self._calculate_expected_range(
                    validated_predictions,
                    current_price,
                    volatility
                )
            )

            # ------------------------------------------------
            # Forecast score
            # ------------------------------------------------
            forecast_score = (
                self._calculate_forecast_score(
                    current_price=current_price,
                    short_prediction=short_pred,
                    primary_trend=primary_trend,
                    trend_strength=trend_strength,
                    next_move_probability=next_move_probability,
                    model_agreement=model_agreement,
                    volatility=volatility
                )
            )

            # ------------------------------------------------
            # Forecast action
            # ------------------------------------------------
            forecast_action = (
                self._translate_forecast_to_action(
                    forecast_score=forecast_score,
                    primary_trend=primary_trend,
                    trend_strength=trend_strength,
                    probabilities=next_move_probability,
                    model_agreement=model_agreement,
                    short_prediction=short_pred,
                    volatility=volatility
                )
            )

            # ------------------------------------------------
            # Model predictions -> JSON safe
            # ------------------------------------------------
            model_predictions = {
                name: [
                    float(x)
                    for x in prediction
                ]
                for name, prediction
                in validated_predictions.items()
            }

            # ------------------------------------------------
            # Summary
            # ------------------------------------------------
            summary = self._generate_summary(
                symbol=symbol,
                current_price=current_price,
                primary_trend=primary_trend,
                trend_strength=trend_strength,
                short_pred=short_pred,
                medium_pred=medium_pred,
                long_pred=long_pred,
                next_move_probability=next_move_probability,
                model_agreement=model_agreement,
                forecast_score=forecast_score,
                forecast_action=forecast_action
            )

            # ------------------------------------------------
            # Recommendations
            # ------------------------------------------------
            recommendations = self._generate_recommendations(
                trend=primary_trend,
                trend_strength=trend_strength,
                forecast_action=forecast_action,
                forecast_score=forecast_score,
                short_pred=short_pred,
                support=key_support,
                resistance=key_resistance,
                probabilities=next_move_probability,
                model_agreement=model_agreement,
                volatility=volatility
            )

            # ------------------------------------------------
            # Build result
            # ------------------------------------------------
            result = ForecastResult(

                symbol=symbol,

                timestamp=datetime.now(
                    timezone.utc
                ),

                current_price=float(
                    current_price
                ),

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
                    k: float(v)
                    for k, v
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
                            expected_high -
                            expected_low
                        ) /
                        current_price *
                        100
                    )
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
                    k: float(v)
                    for k, v
                    in dynamic_weights.items()
                },

                model_status=model_status,

                data_quality={
                    k: float(v)
                    for k, v
                    in data_quality.items()
                },

                model_agreement=float(
                    model_agreement
                ),

                forecast_score=float(
                    forecast_score
                ),

                forecast_action=forecast_action,

                warnings=warnings_list
            )

            # ------------------------------------------------
            # Cache
            # ------------------------------------------------
            self.cache[cache_key] = (
                result,
                datetime.now(timezone.utc)
            )

            logger.info(
                f"Forecast completed for {symbol} | "
                f"trend={primary_trend} | "
                f"score={forecast_score:.3f} | "
                f"action={forecast_action} | "
                f"agreement={model_agreement:.1%}"
            )

            return result

        except Exception as e:

            logger.exception(
                f"Error generating forecast for {symbol}: {e}"
            )

            warnings_list.append(
                f"Forecast exception: {str(e)}"
            )

            return self._get_default_forecast(
                symbol,
                reason="Forecast engine exception",
                warnings_list=warnings_list
            )

    # ========================================================
    # DATA
    # ========================================================

    def _fetch_historical_data(
        self,
        symbol: str
    ) -> Optional[pd.DataFrame]:

        try:

            ticker = yf.Ticker(symbol)

            df = ticker.history(
                period="2y",
                interval="1d",
                auto_adjust=False
            )

            if df is None or df.empty:
                return None

            return df

        except Exception as e:

            logger.error(
                f"Error fetching data for {symbol}: {e}"
            )

            return None

    def _clean_market_data(
        self,
        df: pd.DataFrame
    ) -> pd.DataFrame:

        df = df.copy()

        required_columns = [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume"
        ]

        for column in required_columns:

            if column not in df.columns:

                if column == "Volume":
                    df[column] = 0.0

                else:
                    df[column] = np.nan

        for column in required_columns:

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce"
            )

        df = df.replace(
            [np.inf, -np.inf],
            np.nan
        )

        df = df.dropna(
            subset=["Close"]
        )

        df = df[
            df["Close"] > 0
        ]

        return df

    def _resolve_current_price(
        self,
        df: pd.DataFrame,
        market_data: Optional[Dict]
    ) -> float:

        # Explicit market price gets priority
        if isinstance(market_data, dict):

            for key in [
                "current_price",
                "price",
                "last_price"
            ]:

                value = market_data.get(key)

                if value is not None:

                    try:

                        value = float(value)

                        if np.isfinite(value) and value > 0:
                            return value

                    except Exception:
                        pass

        return float(
            df["Close"].iloc[-1]
        )

    # ========================================================
    # DATA QUALITY
    # ========================================================

    def _calculate_data_quality(
        self,
        df: pd.DataFrame,
        prices: np.ndarray
    ) -> Dict[str, float]:

        observations = len(prices)

        missing_ratio = float(
            df["Close"].isna().mean()
        )

        returns = self._calculate_returns(
            prices
        )

        volatility = (
            float(np.std(returns))
            if len(returns)
            else 0.0
        )

        observation_score = min(
            observations / 365.0,
            1.0
        )

        missing_score = max(
            0.0,
            1.0 - missing_ratio
        )

        finite_score = (
            1.0
            if np.all(np.isfinite(prices))
            else 0.0
        )

        quality_score = (
            observation_score * 0.40
            + missing_score * 0.35
            + finite_score * 0.25
        )

        return {
            "observations": float(observations),
            "return_volatility": volatility,
            "missing_ratio": missing_ratio,
            "quality_score": float(
                np.clip(
                    quality_score,
                    0.0,
                    1.0
                )
            )
        }

    def _calculate_returns(
        self,
        prices: np.ndarray
    ) -> np.ndarray:

        prices = np.asarray(
            prices,
            dtype=float
        )

        if len(prices) < 2:
            return np.array([])

        previous = prices[:-1]

        valid = previous != 0

        returns = (
            prices[1:][valid] /
            previous[valid] -
            1.0
        )

        returns = returns[
            np.isfinite(returns)
        ]

        return returns

    def _annualized_or_daily_volatility(
        self,
        returns: np.ndarray
    ) -> float:

        if len(returns) < 10:
            return 0.02

        volatility = float(
            np.std(
                returns[-90:]
            )
        )

        return float(
            np.clip(
                volatility,
                0.002,
                0.20
            )
        )

    # ========================================================
    # SAFE MODEL EXECUTION
    # ========================================================

    def _safe_model_call(
        self,
        model_name: str,
        function,
        current_price: float,
        model_status: Dict[str, str],
        warnings_list: List[str]
    ) -> Optional[np.ndarray]:

        try:

            prediction = function()

            if prediction is None:

                model_status[
                    model_name
                ] = "FAILED"

                warnings_list.append(
                    f"{model_name}: returned None"
                )

                return None

            prediction = np.asarray(
                prediction,
                dtype=float
            )

            if len(prediction) == 0:

                model_status[
                    model_name
                ] = "FAILED"

                warnings_list.append(
                    f"{model_name}: empty prediction"
                )

                return None

            return prediction

        except Exception as e:

            model_status[
                model_name
            ] = "FAILED"

            warnings_list.append(
                f"{model_name}: {str(e)}"
            )

            logger.warning(
                f"{model_name} failed: {e}"
            )

            return None

    # ========================================================
    # MODEL VALIDATION
    # ========================================================

    def _validate_prediction(
        self,
        prediction: np.ndarray,
        current_price: float,
        model_name: str,
        warnings_list: List[str]
    ) -> Optional[np.ndarray]:

        prediction = np.asarray(
            prediction,
            dtype=float
        )

        prediction = prediction[
            np.isfinite(prediction)
        ]

        if len(prediction) == 0:
            return None

        # Ensure exactly long horizon
        horizon = self.forecast_horizons["long"]

        if len(prediction) < horizon:

            last = prediction[-1]

            prediction = np.pad(
                prediction,
                (
                    0,
                    horizon - len(prediction)
                ),
                mode="edge"
            )

        elif len(prediction) > horizon:

            prediction = prediction[:horizon]

        # ----------------------------------------------------
        # Hard sanity check
        #
        # A BTC forecast of $156 while BTC is $62k is not
        # "low confidence". It is an INVALID MODEL OUTPUT.
        # ----------------------------------------------------
        relative_moves = (
            prediction /
            current_price -
            1.0
        )

        max_move = np.max(
            np.abs(relative_moves)
        )

        if (
            not np.isfinite(max_move)
            or max_move >
            self.max_reasonable_move
        ):

            warnings_list.append(
                f"{model_name}: rejected abnormal "
                f"forecast ({max_move:.1%} from reference price)"
            )

            logger.warning(
                f"Rejected {model_name} prediction: "
                f"max move={max_move:.2%}"
            )

            return None

        # ----------------------------------------------------
        # Prices must remain positive
        # ----------------------------------------------------
        if np.any(prediction <= 0):

            warnings_list.append(
                f"{model_name}: rejected non-positive price"
            )

            return None

        # ----------------------------------------------------
        # Smooth pathological jumps
        # ----------------------------------------------------
        for i in range(1, len(prediction)):

            step_return = (
                prediction[i] /
                prediction[i - 1] -
                1.0
            )

            if abs(step_return) > 0.10:

                warnings_list.append(
                    f"{model_name}: rejected unstable path"
                )

                return None

        return prediction

    # ========================================================
    # AR MODEL
    # ========================================================

    def _arima_forecast(
        self,
        prices: np.ndarray,
        horizon: int
    ) -> np.ndarray:

        data = np.asarray(
            prices[-60:],
            dtype=float
        )

        if len(data) < 15:
            return self._simple_moving_average_forecast(
                prices,
                horizon
            )

        y = data[2:]

        X = np.column_stack(
            [
                data[1:-1],
                data[:-2],
                np.ones(
                    len(data) - 2
                )
            ]
        )

        coef, *_ = np.linalg.lstsq(
            X,
            y,
            rcond=None
        )

        predictions = []

        last_values = [
            float(data[-2]),
            float(data[-1])
        ]

        for _ in range(horizon):

            next_price = (
                coef[0] * last_values[-1]
                + coef[1] * last_values[-2]
                + coef[2]
            )

            if not np.isfinite(next_price):
                raise ValueError(
                    "AR forecast became non-finite"
                )

            predictions.append(
                float(next_price)
            )

            last_values = [
                last_values[-1],
                next_price
            ]

        return np.asarray(
            predictions
        )

    def _simple_moving_average_forecast(
        self,
        prices: np.ndarray,
        horizon: int
    ) -> np.ndarray:

        if len(prices) == 0:
            return np.zeros(horizon)

        window = min(
            20,
            len(prices)
        )

        recent = prices[-window:]

        weights = np.arange(
            1,
            window + 1,
            dtype=float
        )

        weights /= weights.sum()

        baseline = float(
            np.sum(
                recent * weights
            )
        )

        last_price = float(
            prices[-1]
        )

        # Very conservative reversion
        predictions = []

        for i in range(horizon):

            alpha = min(
                0.10,
                0.03 * (i + 1)
            )

            value = (
                last_price * (1 - alpha)
                + baseline * alpha
            )

            predictions.append(
                value
            )

        return np.asarray(
            predictions
        )

    # ========================================================
    # LINEAR REGRESSION
    # ========================================================

    def _linear_regression_forecast(
        self,
        prices: np.ndarray
    ) -> np.ndarray:

        horizon = self.forecast_horizons["long"]

        if len(prices) < 30:

            return np.full(
                horizon,
                prices[-1]
            )

        data = prices[-90:]

        # Work in log-price space to reduce scale problems
        y = np.log(
            np.maximum(
                data,
                1e-12
            )
        )

        X = np.arange(
            len(data)
        ).reshape(-1, 1)

        model = LinearRegression()

        model.fit(
            X,
            y
        )

        future_X = np.arange(
            len(data),
            len(data) + horizon
        ).reshape(-1, 1)

        predicted_log = model.predict(
            future_X
        )

        return np.exp(
            predicted_log
        )

    # ========================================================
    # RANDOM FOREST
    # ========================================================

    def _random_forest_forecast(
        self,
        df: pd.DataFrame
    ) -> np.ndarray:

        prices = (
            df["Close"]
            .astype(float)
            .values
        )

        horizon = self.forecast_horizons["long"]

        if len(prices) < 80:

            return np.full(
                horizon,
                prices[-1]
            )

        data = prices[-180:]

        lag = 10

        X = []
        y = []

        for i in range(
            lag,
            len(data)
        ):

            X.append(
                data[i-lag:i]
            )

            y.append(
                data[i]
            )

        X = np.asarray(X)
        y = np.asarray(y)

        if len(X) < 40:

            return np.full(
                horizon,
                prices[-1]
            )

        rf = RandomForestRegressor(
            n_estimators=150,
            max_depth=8,
            min_samples_leaf=3,
            random_state=42,
            n_jobs=-1
        )

        rf.fit(
            X,
            y
        )

        last_features = (
            data[-lag:]
            .astype(float)
            .tolist()
        )

        predictions = []

        for _ in range(horizon):

            features = np.asarray(
                last_features,
                dtype=float
            ).reshape(
                1,
                -1
            )

            next_price = float(
                rf.predict(features)[0]
            )

            predictions.append(
                next_price
            )

            last_features = (
                last_features[1:]
                + [next_price]
            )

        return np.asarray(
            predictions
        )

    # ========================================================
    # PATTERN RECOGNITION
    # ========================================================

    def _pattern_recognition_forecast(
        self,
        prices: np.ndarray
    ) -> np.ndarray:

        horizon = self.forecast_horizons["long"]
        window = self.pattern_window

        if len(prices) < (
            self.min_pattern_history
        ):
            return np.full(
                horizon,
                prices[-1]
            )

        current = prices[-window:]

        current_returns = (
            np.diff(current) /
            current[:-1]
        )

        current_norm = self._normalize_pattern(
            current_returns
        )

        candidates = []

        # ----------------------------------------------------
        # Search historical windows.
        #
        # IMPORTANT:
        # We use RELATIVE future returns, never raw sample
        # prices. This prevents the old $100/$200 dummy
        # pattern bug.
        # ----------------------------------------------------
        max_start = (
            len(prices)
            - window
            - horizon
        )

        for start in range(
            0,
            max_start
        ):

            historical_window = (
                prices[
                    start:
                    start + window
                ]
            )

            future_window = (
                prices[
                    start + window:
                    start + window + horizon
                ]
            )

            if len(future_window) < horizon:
                continue

            hist_returns = (
                np.diff(
                    historical_window
                ) /
                historical_window[:-1]
            )

            hist_norm = self._normalize_pattern(
                hist_returns
            )

            correlation = (
                self._safe_correlation(
                    current_norm,
                    hist_norm
                )
            )

            shape_score = (
                self._compare_pattern_shape(
                    current,
                    historical_window
                )
            )

            similarity = (
                0.75 * correlation
                + 0.25 * shape_score
            )

            if similarity < 0.60:
                continue

            # Future relative return
            base_price = (
                historical_window[-1]
            )

            future_returns = (
                future_window /
                base_price -
                1.0
            )

            candidates.append(
                (
                    similarity,
                    future_returns
                )
            )

        if not candidates:

            return np.full(
                horizon,
                prices[-1]
            )

        # Best historical matches
        candidates.sort(
            key=lambda x: x[0],
            reverse=True
        )

        top = candidates[:8]

        weighted_returns = []
        total_weight = 0.0

        for similarity, future_returns in top:

            weight = max(
                similarity - 0.50,
                0.01
            )

            weighted_returns.append(
                future_returns * weight
            )

            total_weight += weight

        if total_weight <= 0:
            return np.full(
                horizon,
                prices[-1]
            )

        average_returns = (
            np.sum(
                weighted_returns,
                axis=0
            )
            / total_weight
        )

        # Convert relative returns back to current BTC price
        predictions = []
        base = float(prices[-1])

        for future_return in average_returns:

            # Cap each historical-derived move
            future_return = float(
                np.clip(
                    future_return,
                    -0.05,
                    0.05
                )
            )

            base *= (
                1.0 +
                future_return
            )

            predictions.append(
                base
            )

        return np.asarray(
            predictions
        )

    def _normalize_pattern(
        self,
        values: np.ndarray
    ) -> np.ndarray:

        values = np.asarray(
            values,
            dtype=float
        )

        if len(values) == 0:
            return values

        mean = np.mean(values)
        std = np.std(values)

        if std < 1e-12:
            return np.zeros_like(values)

        return (
            values - mean
        ) / std

    def _safe_correlation(
        self,
        a: np.ndarray,
        b: np.ndarray
    ) -> float:

        if (
            len(a) != len(b)
            or len(a) < 2
        ):
            return 0.0

        if (
            np.std(a) < 1e-12
            or np.std(b) < 1e-12
        ):
            return 0.0

        correlation = np.corrcoef(
            a,
            b
        )[0, 1]

        if not np.isfinite(
            correlation
        ):
            return 0.0

        return float(
            np.clip(
                (correlation + 1.0) / 2.0,
                0.0,
                1.0
            )
        )

    def _compare_pattern_shape(
        self,
        pattern1: np.ndarray,
        pattern2: np.ndarray
    ) -> float:

        try:

            peaks1, _ = find_peaks(
                pattern1,
                distance=3
            )

            peaks2, _ = find_peaks(
                pattern2,
                distance=3
            )

            troughs1, _ = find_peaks(
                -pattern1,
                distance=3
            )

            troughs2, _ = find_peaks(
                -pattern2,
                distance=3
            )

            count_difference = (
                abs(
                    len(peaks1)
                    - len(peaks2)
                )
                +
                abs(
                    len(troughs1)
                    - len(troughs2)
                )
            )

            count_score = max(
                0.0,
                1.0 -
                count_difference / 6.0
            )

            return float(
                np.clip(
                    count_score,
                    0.0,
                    1.0
                )
            )

        except Exception:
            return 0.5

    # ========================================================
    # MONTE CARLO
    # ========================================================

    def _monte_carlo_forecast(
        self,
        prices: np.ndarray
    ) -> np.ndarray:

        horizon = self.forecast_horizons["long"]

        returns = self._calculate_returns(
            prices
        )

        if len(returns) < 30:

            return np.full(
                horizon,
                prices[-1]
            )

        returns = returns[-180:]

        mu = float(
            np.mean(returns)
        )

        sigma = float(
            np.std(returns)
        )

        sigma = max(
            sigma,
            0.001
        )

        n_simulations = 500

        rng = np.random.default_rng(
            42
        )

        simulations = np.zeros(
            (
                n_simulations,
                horizon
            )
        )

        for simulation in range(
            n_simulations
        ):

            price = float(
                prices[-1]
            )

            for step in range(
                horizon
            ):

                random_return = rng.normal(
                    mu,
                    sigma
                )

                # Prevent pathological one-day jumps
                random_return = np.clip(
                    random_return,
                    -0.15,
                    0.15
                )

                price *= (
                    1.0 +
                    random_return
                )

                simulations[
                    simulation,
                    step
                ] = price

        return np.median(
            simulations,
            axis=0
        )

    # ========================================================
    # SENTIMENT + TECHNICAL
    # ========================================================

    def _sentiment_technical_forecast(
        self,
        prices: np.ndarray,
        sentiment_result: Any,
        technical_result: Any
    ) -> np.ndarray:

        horizon = self.forecast_horizons["long"]

        sentiment_score = float(
            getattr(
                sentiment_result,
                "overall_score",
                0.0
            )
        )

        technical_score = float(
            getattr(
                technical_result,
                "overall_score",
                0.0
            )
        )

        sentiment_score = float(
            np.clip(
                sentiment_score,
                -1.0,
                1.0
            )
        )

        technical_score = float(
            np.clip(
                technical_score,
                -1.0,
                1.0
            )
        )

        combined_score = (
            sentiment_score * 0.40
            +
            technical_score * 0.60
        )

        combined_score = float(
            np.clip(
                combined_score,
                -1.0,
                1.0
            )
        )

        last_price = float(
            prices[-1]
        )

        # Recent momentum
        if len(prices) >= 6:

            momentum = (
                prices[-1] /
                prices[-6] -
                1.0
            )

        else:

            momentum = 0.0

        # Conservative daily adjustment
        daily_bias = (
            combined_score * 0.003
            +
            np.clip(
                momentum * 0.10,
                -0.003,
                0.003
            )
        )

        predictions = []

        price = last_price

        for i in range(
            horizon
        ):

            decay = 1.0 / (
                1.0 +
                0.20 * i
            )

            step_bias = (
                daily_bias *
                decay
            )

            price *= (
                1.0 +
                step_bias
            )

            predictions.append(
                price
            )

        return np.asarray(
            predictions
        )

    # ========================================================
    # DYNAMIC WEIGHTING
    # ========================================================

    def _calculate_dynamic_weights(
        self,
        predictions: Dict[str, np.ndarray],
        current_price: float,
        volatility: float,
        quality_score: float
    ) -> Dict[str, float]:

        raw_weights = {}

        for model_name, prediction in predictions.items():

            base_weight = (
                self.base_model_weights.get(
                    model_name,
                    0.10
                )
            )

            short_return = (
                prediction[0] /
                current_price -
                1.0
            )

            # ------------------------------------------------
            # Stability factor
            # ------------------------------------------------
            path_returns = (
                prediction /
                current_price -
                1.0
            )

            max_move = float(
                np.max(
                    np.abs(
                        path_returns
                    )
                )
            )

            stability = max(
                0.20,
                1.0 -
                min(
                    max_move /
                    self.max_reasonable_move,
                    1.0
                )
            )

            # ------------------------------------------------
            # Magnitude plausibility
            #
            # A model predicting movement 20x normal volatility
            # should not dominate the ensemble.
            # ------------------------------------------------
            volatility_ratio = (
                abs(short_return) /
                max(
                    volatility,
                    0.001
                )
            )

            if volatility_ratio > 5.0:

                magnitude_factor = 0.25

            elif volatility_ratio > 3.0:

                magnitude_factor = 0.50

            elif volatility_ratio > 2.0:

                magnitude_factor = 0.75

            else:

                magnitude_factor = 1.0

            weight = (
                base_weight
                * stability
                * magnitude_factor
                * (
                    0.75 +
                    0.25 * quality_score
                )
            )

            raw_weights[
                model_name
            ] = max(
                weight,
                0.001
            )

        total = sum(
            raw_weights.values()
        )

        if total <= 0:

            count = max(
                len(raw_weights),
                1
            )

            return {
                name: 1.0 / count
                for name in raw_weights
            }

        return {
            name: weight / total
            for name, weight
            in raw_weights.items()
        }

    # ========================================================
    # ENSEMBLE
    # ========================================================

    def _ensemble_forecast(
        self,
        predictions: Dict[str, np.ndarray],
        weights: Dict[str, float],
        current_price: float
    ) -> np.ndarray:

        horizon = self.forecast_horizons["long"]

        weighted_sum = np.zeros(
            horizon,
            dtype=float
        )

        total_weight = 0.0

        for model_name, prediction in predictions.items():

            weight = weights.get(
                model_name,
                0.0
            )

            if weight <= 0:
                continue

            prediction = np.asarray(
                prediction,
                dtype=float
            )

            if len(prediction) != horizon:
                continue

            weighted_sum += (
                prediction *
                weight
            )

            total_weight += weight

        if total_weight <= 0:

            return np.full(
                horizon,
                current_price
            )

        ensemble = (
            weighted_sum /
            total_weight
        )

        return self._repair_prediction_path(
            ensemble,
            current_price
        )

    def _repair_prediction_path(
        self,
        prediction: np.ndarray,
        current_price: float
    ) -> np.ndarray:

        prediction = np.asarray(
            prediction,
            dtype=float
        )

        prediction = np.where(
            np.isfinite(prediction),
            prediction,
            current_price
        )

        # Limit total forecast displacement
        lower = (
            current_price *
            (1.0 -
             self.max_reasonable_move)
        )

        upper = (
            current_price *
            (1.0 +
             self.max_reasonable_move)
        )

        prediction = np.clip(
            prediction,
            lower,
            upper
        )

        # Ensure positive
        prediction = np.maximum(
            prediction,
            current_price * 0.01
        )

        return prediction

    # ========================================================
    # MODEL AGREEMENT
    # ========================================================

    def _calculate_model_agreement(
        self,
        predictions: Dict[str, np.ndarray],
        current_price: float
    ) -> float:

        if len(predictions) < 2:
            return 0.35

        short_returns = []

        for prediction in predictions.values():

            if len(prediction) == 0:
                continue

            short_return = (
                prediction[0] /
                current_price -
                1.0
            )

            short_returns.append(
                short_return
            )

        if len(short_returns) < 2:
            return 0.35

        short_returns = np.asarray(
            short_returns
        )

        dispersion = float(
            np.std(
                short_returns
            )
        )

        # 2% dispersion -> roughly 0 agreement
        agreement = (
            1.0 -
            dispersion / 0.02
        )

        # Direction agreement
        signs = np.sign(
            short_returns
        )

        positive = np.mean(
            signs > 0
        )

        negative = np.mean(
            signs < 0
        )

        neutral = np.mean(
            signs == 0
        )

        direction_agreement = max(
            positive,
            negative,
            neutral
        )

        final_agreement = (
            agreement * 0.60
            +
            direction_agreement * 0.40
        )

        return float(
            np.clip(
                final_agreement,
                0.0,
                1.0
            )
        )

    # ========================================================
    # TREND
    # ========================================================

    def _analyze_trend(
        self,
        prices: np.ndarray
    ) -> Tuple[str, float]:

        if len(prices) < 50:

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
                prices[-50:]
            )
        )

        ma100 = float(
            np.mean(
                prices[-100:]
            )
        ) if len(prices) >= 100 else ma50

        current_price = float(
            prices[-1]
        )

        # ----------------------------------------------------
        # Trend
        # ----------------------------------------------------
        if (
            current_price >
            ma20 >
            ma50 >
            ma100
        ):

            trend = "BULLISH"

        elif (
            current_price <
            ma20 <
            ma50 <
            ma100
        ):

            trend = "BEARISH"

        else:

            trend = "CONSOLIDATING"

        # ----------------------------------------------------
        # Trend strength
        # ----------------------------------------------------
        if trend == "BULLISH":

            distance = (
                current_price -
                ma50
            ) / ma50

            slope = (
                ma20 -
                ma50
            ) / ma50

            strength = (
                abs(distance) * 3
                +
                abs(slope) * 2
            )

        elif trend == "BEARISH":

            distance = (
                ma50 -
                current_price
            ) / ma50

            slope = (
                ma50 -
                ma20
            ) / ma50

            strength = (
                abs(distance) * 3
                +
                abs(slope) * 2
            )

        else:

            recent = prices[-20:]

            range_percent = (
                np.max(recent) -
                np.min(recent)
            ) / np.mean(recent)

            strength = max(
                0.0,
                1.0 -
                min(
                    range_percent / 0.08,
                    1.0
                )
            )

        return (
            trend,
            float(
                np.clip(
                    strength,
                    0.0,
                    1.0
                )
            )
        )

    # ========================================================
    # NEXT MOVE PROBABILITY
    # ========================================================

    def _predict_next_move(
        self,
        prices: np.ndarray,
        ensemble_pred: np.ndarray,
        volatility: float,
        model_agreement: float
    ) -> Dict[str, float]:

        if len(ensemble_pred) == 0:

            return {
                "UP": 0.33,
                "DOWN": 0.33,
                "SIDEWAYS": 0.34
            }

        current_price = float(
            prices[-1]
        )

        predicted_return = (
            ensemble_pred[0] /
            current_price -
            1.0
        )

        if len(prices) >= 6:

            historical_momentum = (
                prices[-1] /
                prices[-6] -
                1.0
            )

        else:

            historical_momentum = 0.0

        # ----------------------------------------------------
        # Normalize movement by volatility
        # ----------------------------------------------------
        vol = max(
            volatility,
            0.001
        )

        normalized_move = (
            predicted_return /
            vol
        )

        normalized_momentum = (
            historical_momentum /
            vol
        )

        signal = (
            normalized_move * 0.65
            +
            normalized_momentum * 0.35
        )

        # Model disagreement reduces directional certainty
        directional_strength = (
            abs(signal) *
            model_agreement
        )

        # ----------------------------------------------------
        # Sideways dominates if move is small compared to vol
        # ----------------------------------------------------
        if abs(signal) < 0.35:

            up = 0.25
            down = 0.25
            sideways = 0.50

        elif signal > 0:

            directional = min(
                0.70,
                0.40 +
                directional_strength * 0.12
            )

            up = directional

            sideways = max(
                0.10,
                0.40 -
                directional_strength * 0.08
            )

            down = 1.0 - up - sideways

        else:

            directional = min(
                0.70,
                0.40 +
                directional_strength * 0.12
            )

            down = directional

            sideways = max(
                0.10,
                0.40 -
                directional_strength * 0.08
            )

            up = 1.0 - down - sideways

        probabilities = {
            "UP": max(
                0.0,
                float(up)
            ),
            "DOWN": max(
                0.0,
                float(down)
            ),
            "SIDEWAYS": max(
                0.0,
                float(sideways)
            )
        }

        total = sum(
            probabilities.values()
        )

        return {
            key: value / total
            for key, value
            in probabilities.items()
        }

    # ========================================================
    # SCENARIOS
    # ========================================================

    def _generate_scenarios(
        self,
        current_price: float,
        ensemble_pred: np.ndarray,
        predictions: Dict[str, np.ndarray],
        volatility: float,
        model_agreement: float,
        trend: str
    ) -> Dict[str, Any]:

        horizon = len(
            ensemble_pred
        )

        if horizon == 0:

            ensemble_pred = np.full(
                self.forecast_horizons["long"],
                current_price
            )

            horizon = len(
                ensemble_pred
            )

        # ----------------------------------------------------
        # Forecast dispersion
        # ----------------------------------------------------
        if predictions:

            matrix = np.vstack(
                [
                    prediction[:horizon]
                    for prediction
                    in predictions.values()
                ]
            )

            dispersion = np.std(
                matrix,
                axis=0
            )

        else:

            dispersion = np.full(
                horizon,
                current_price *
                volatility
            )

        # ----------------------------------------------------
        # Scenario volatility buffer
        # ----------------------------------------------------
        time_scale = np.sqrt(
            np.arange(
                1,
                horizon + 1
            )
        )

        volatility_buffer = (
            current_price *
            volatility *
            1.5 *
            time_scale
        )

        dispersion_buffer = (
            dispersion *
            0.50
        )

        total_buffer = (
            volatility_buffer
            +
            dispersion_buffer
        )

        bullish = (
            ensemble_pred +
            total_buffer
        )

        bearish = (
            ensemble_pred -
            total_buffer
        )

        # ----------------------------------------------------
        # Keep scenarios realistic
        # ----------------------------------------------------
        bullish = np.clip(
            bullish,
            current_price * 0.85,
            current_price * 1.15
        )

        bearish = np.clip(
            bearish,
            current_price * 0.85,
            current_price * 1.15
        )

        most_likely = (
            ensemble_pred
        )

        # ----------------------------------------------------
        # Scenario probabilities
        # ----------------------------------------------------
        if trend == "BULLISH":

            bullish_prob = (
                0.30 +
                model_agreement * 0.20
            )

            bearish_prob = (
                0.20 -
                model_agreement * 0.05
            )

        elif trend == "BEARISH":

            bearish_prob = (
                0.30 +
                model_agreement * 0.20
            )

            bullish_prob = (
                0.20 -
                model_agreement * 0.05
            )

        else:

            bullish_prob = 0.25
            bearish_prob = 0.25

        bullish_prob = float(
            np.clip(
                bullish_prob,
                0.10,
                0.45
            )
        )

        bearish_prob = float(
            np.clip(
                bearish_prob,
                0.10,
                0.45
            )
        )

        most_likely_prob = max(
            0.10,
            1.0 -
            bullish_prob -
            bearish_prob
        )

        total = (
            bullish_prob
            +
            bearish_prob
            +
            most_likely_prob
        )

        bullish_prob /= total
        bearish_prob /= total
        most_likely_prob /= total

        return {
            "bullish": bullish,
            "bearish": bearish,
            "most_likely": most_likely,
            "bullish_prob": bullish_prob,
            "bearish_prob": bearish_prob,
            "most_likely_prob": most_likely_prob
        }

    # ========================================================
    # PRICE PREDICTION
    # ========================================================

    def _create_price_prediction(
        self,
        ensemble_pred: np.ndarray,
        horizon: str,
        current_price: float,
        volatility: float,
        model_agreement: float
    ) -> PricePrediction:

        horizon_days = {
            "short": 2,
            "medium": 5,
            "long": 7
        }

        days = horizon_days.get(
            horizon,
            2
        )

        index = min(
            days - 1,
            len(ensemble_pred) - 1
        )

        predicted_price = float(
            ensemble_pred[index]
        )

        predicted_change = (
            predicted_price /
            current_price -
            1.0
        )

        # ----------------------------------------------------
        # Confidence based on:
        # - model agreement
        # - movement plausibility
        # ----------------------------------------------------
        magnitude_vs_vol = (
            abs(predicted_change) /
            max(
                volatility *
                np.sqrt(days),
                0.001
            )
        )

        if magnitude_vs_vol <= 1.0:

            plausibility = 0.85

        elif magnitude_vs_vol <= 2.0:

            plausibility = 0.70

        elif magnitude_vs_vol <= 3.0:

            plausibility = 0.50

        else:

            plausibility = 0.30

        confidence = (
            0.45 * model_agreement
            +
            0.35 * plausibility
            +
            0.20 * 0.70
        )

        confidence = float(
            np.clip(
                confidence,
                0.35,
                0.90
            )
        )

        # ----------------------------------------------------
        # Confidence interval
        # ----------------------------------------------------
        interval_width = (
            current_price *
            volatility *
            np.sqrt(days) *
            (
                1.20 -
                0.50 * model_agreement
            )
        )

        lower = max(
            0.0,
            predicted_price -
            interval_width
        )

        upper = (
            predicted_price +
            interval_width
        )

        return PricePrediction(

            timestamp=(
                datetime.now(
                    timezone.utc
                )
                +
                timedelta(days=days)
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
                predicted_change * 100
            )
        )

    # ========================================================
    # FORECAST SCORE
    # ========================================================

    def _calculate_forecast_score(
        self,
        current_price: float,
        short_prediction: PricePrediction,
        primary_trend: str,
        trend_strength: float,
        next_move_probability: Dict[str, float],
        model_agreement: float,
        volatility: float
    ) -> float:

        predicted_return = (
            short_prediction.predicted_price /
            current_price -
            1.0
        )

        vol = max(
            volatility,
            0.001
        )

        # ----------------------------------------------------
        # Magnitude normalized by volatility
        # ----------------------------------------------------
        normalized_return = (
            predicted_return /
            vol
        )

        magnitude_score = float(
            np.tanh(
                normalized_return
            )
        )

        # ----------------------------------------------------
        # Probability imbalance
        # ----------------------------------------------------
        probability_score = (
            next_move_probability["UP"]
            -
            next_move_probability["DOWN"]
        )

        # ----------------------------------------------------
        # Trend component
        # ----------------------------------------------------
        if primary_trend == "BULLISH":

            trend_score = (
                trend_strength
            )

        elif primary_trend == "BEARISH":

            trend_score = (
                -trend_strength
            )

        else:

            trend_score = 0.0

        # ----------------------------------------------------
        # Combine
        # ----------------------------------------------------
        score = (
            magnitude_score * 0.45
            +
            probability_score * 0.30
            +
            trend_score * 0.15
            +
            (
                probability_score *
                model_agreement
            ) * 0.10
        )

        return float(
            np.clip(
                score,
                -1.0,
                1.0
            )
        )

    # ========================================================
    # ACTION TRANSLATION
    # ========================================================

    def _translate_forecast_to_action(
        self,
        forecast_score: float,
        primary_trend: str,
        trend_strength: float,
        probabilities: Dict[str, float],
        model_agreement: float,
        short_prediction: PricePrediction,
        volatility: float
    ) -> str:

        predicted_move = abs(
            short_prediction.predicted_change_percent
        ) / 100.0

        vol = max(
            volatility,
            0.001
        )

        movement_ratio = (
            predicted_move /
            vol
        )

        up_probability = (
            probabilities["UP"]
        )

        down_probability = (
            probabilities["DOWN"]
        )

        # ====================================================
        # STRONG BUY
        # ====================================================
        if (
            forecast_score >= 0.65
            and up_probability >= 0.62
            and model_agreement >= 0.60
            and movement_ratio >= 0.75
            and primary_trend == "BULLISH"
        ):

            return "STRONG_BUY"

        # ====================================================
        # BUY
        # ====================================================
        if (
            forecast_score >= 0.25
            and up_probability >= 0.52
            and model_agreement >= 0.45
            and movement_ratio >= 0.35
        ):

            return "BUY"

        # ====================================================
        # STRONG SELL
        #
        # Much harder to trigger than old version.
        # ====================================================
        if (
            forecast_score <= -0.65
            and down_probability >= 0.62
            and model_agreement >= 0.60
            and movement_ratio >= 0.75
            and primary_trend == "BEARISH"
        ):

            return "STRONG_SELL"

        # ====================================================
        # SELL
        # ====================================================
        if (
            forecast_score <= -0.25
            and down_probability >= 0.52
            and model_agreement >= 0.45
            and movement_ratio >= 0.35
        ):

            return "SELL"

        # ====================================================
        # Otherwise HOLD
        # ====================================================
        return "HOLD"

    # ========================================================
    # SUPPORT / RESISTANCE
    # ========================================================

    def _find_key_levels(
        self,
        df: pd.DataFrame
    ) -> Tuple[List[float], List[float]]:

        high = (
            df["High"]
            .astype(float)
            .values
        )

        low = (
            df["Low"]
            .astype(float)
            .values
        )

        window = 10

        peaks = []
        troughs = []

        if len(high) < (
            window * 2 + 1
        ):

            return [], []

        for i in range(
            window,
            len(high) - window
        ):

            local_high = high[
                i-window:
                i+window+1
            ]

            local_low = low[
                i-window:
                i+window+1
            ]

            if high[i] == np.max(
                local_high
            ):

                peaks.append(
                    float(high[i])
                )

            if low[i] == np.min(
                local_low
            ):

                troughs.append(
                    float(low[i])
                )

        resistance = (
            self._cluster_levels(
                peaks,
                tolerance=0.02
            )
        )

        support = (
            self._cluster_levels(
                troughs,
                tolerance=0.02
            )
        )

        current_price = float(
            df["Close"].iloc[-1]
        )

        # ----------------------------------------------------
        # Only levels around current market price are useful.
        # ----------------------------------------------------
        support = [
            level
            for level in support
            if level < current_price
        ]

        resistance = [
            level
            for level in resistance
            if level > current_price
        ]

        support.sort(
            reverse=True
        )

        resistance.sort()

        return (
            support[:3],
            resistance[:3]
        )

    def _cluster_levels(
        self,
        levels: List[float],
        tolerance: float = 0.02
    ) -> List[float]:

        if not levels:
            return []

        levels = sorted(
            float(x)
            for x in levels
            if np.isfinite(x)
            and x > 0
        )

        if not levels:
            return []

        clusters = []

        current_cluster = [
            levels[0]
        ]

        for level in levels[1:]:

            average = (
                sum(current_cluster)
                /
                len(current_cluster)
            )

            if (
                abs(
                    level -
                    average
                )
                /
                max(
                    average,
                    1e-12
                )
                <= tolerance
            ):

                current_cluster.append(
                    level
                )

            else:

                clusters.append(
                    sum(current_cluster)
                    /
                    len(current_cluster)
                )

                current_cluster = [
                    level
                ]

        clusters.append(
            sum(current_cluster)
            /
            len(current_cluster)
        )

        return clusters

    # ========================================================
    # EXPECTED RANGE
    # ========================================================

    def _calculate_expected_range(
        self,
        predictions: Dict[str, np.ndarray],
        current_price: float,
        volatility: float
    ) -> Tuple[float, float]:

        if not predictions:

            buffer = (
                current_price *
                volatility *
                2.0
            )

            return (
                current_price + buffer,
                max(
                    0.0,
                    current_price - buffer
                )
            )

        # ----------------------------------------------------
        # Instead of min/max, use robust quantiles.
        # This prevents one outlier from producing a 104% range.
        # ----------------------------------------------------
        final_prices = []

        for prediction in predictions.values():

            if len(prediction):

                final_prices.append(
                    float(
                        prediction[-1]
                    )
                )

        if not final_prices:

            return (
                current_price * 1.05,
                current_price * 0.95
            )

        final_prices = np.asarray(
            final_prices
        )

        low_model = float(
            np.percentile(
                final_prices,
                20
            )
        )

        high_model = float(
            np.percentile(
                final_prices,
                80
            )
        )

        volatility_buffer = (
            current_price *
            volatility *
            1.25
        )

        expected_low = max(
            0.0,
            min(
                low_model -
                volatility_buffer,
                current_price * 0.85
            )
        )

        expected_high = min(
            high_model +
            volatility_buffer,
            current_price * 1.15
        )

        return (
            expected_high,
            expected_low
        )

    # ========================================================
    # SUMMARY
    # ========================================================

    def _generate_summary(
        self,
        symbol: str,
        current_price: float,
        primary_trend: str,
        trend_strength: float,
        short_pred: PricePrediction,
        medium_pred: PricePrediction,
        long_pred: PricePrediction,
        next_move_probability: Dict[str, float],
        model_agreement: float,
        forecast_score: float,
        forecast_action: str
    ) -> str:

        symbol_name = (
            symbol
            .replace("-USD", "")
            .replace("-USDT", "")
        )

        summary = (
            f"Forecast {symbol_name}: "
            f"harga saat ini "
            f"${current_price:.2f}. "
        )

        summary += (
            f"Trend {primary_trend} "
            f"dengan strength "
            f"{trend_strength:.1%}. "
        )

        summary += (
            f"Forecast SHORT "
            f"${short_pred.predicted_price:.2f} "
            f"("
            f"{short_pred.predicted_change_percent:+.2f}%"
            f"). "
        )

        summary += (
            f"MEDIUM "
            f"{medium_pred.predicted_change_percent:+.2f}%, "
            f"LONG "
            f"{long_pred.predicted_change_percent:+.2f}%. "
        )

        summary += (
            f"Probability "
            f"UP={next_move_probability['UP']:.1%}, "
            f"DOWN={next_move_probability['DOWN']:.1%}, "
            f"SIDEWAYS={next_move_probability['SIDEWAYS']:.1%}. "
        )

        summary += (
            f"Model agreement "
            f"{model_agreement:.1%}. "
        )

        summary += (
            f"Forecast score "
            f"{forecast_score:+.3f}. "
        )

        summary += (
            f"Forecast action "
            f"{forecast_action}."
        )

        return summary

    # ========================================================
    # RECOMMENDATIONS
    # ========================================================

    def _generate_recommendations(
        self,
        trend: str,
        trend_strength: float,
        forecast_action: str,
        forecast_score: float,
        short_pred: PricePrediction,
        support: List[float],
        resistance: List[float],
        probabilities: Dict[str, float],
        model_agreement: float,
        volatility: float
    ) -> List[str]:

        recommendations = []

        # ----------------------------------------------------
        # Regime
        # ----------------------------------------------------
        if trend == "BULLISH":

            recommendations.append(
                "Trend bullish; tunggu confirmation "
                "sebelum entry agresif."
            )

        elif trend == "BEARISH":

            recommendations.append(
                "Trend bearish; hindari entry agresif "
                "tanpa confirmation."
            )

        else:

            recommendations.append(
                "Trend masih konsolidasi; "
                "wait and see lebih aman."
            )

        # ----------------------------------------------------
        # Forecast action
        # ----------------------------------------------------
        if forecast_action == "STRONG_BUY":

            recommendations.append(
                "Forecast bullish kuat dengan "
                "confirmation antar-model."
            )

        elif forecast_action == "BUY":

            recommendations.append(
                "Forecast memiliki bullish bias, "
                "tetapi tetap membutuhkan confirmation."
            )

        elif forecast_action == "STRONG_SELL":

            recommendations.append(
                "Forecast bearish kuat dengan "
                "confirmation antar-model."
            )

        elif forecast_action == "SELL":

            recommendations.append(
                "Forecast memiliki bearish bias, "
                "tetapi tetap membutuhkan confirmation."
            )

        else:

            recommendations.append(
                "Belum ada directional edge yang cukup "
                "kuat untuk trade."
            )

        # ----------------------------------------------------
        # Probability
        # ----------------------------------------------------
        highest_direction = max(
            probabilities,
            key=probabilities.get
        )

        highest_probability = (
            probabilities[
                highest_direction
            ]
        )

        if highest_probability >= 0.55:

            recommendations.append(
                f"Probability {highest_direction} "
                f"{highest_probability:.1%}."
            )

        else:

            recommendations.append(
                "Tidak ada probabilitas arah "
                "yang cukup dominan."
            )

        # ----------------------------------------------------
        # Support
        # ----------------------------------------------------
        if support:

            recommendations.append(
                f"Support terdekat: "
                f"${support[0]:.2f}."
            )

        # ----------------------------------------------------
        # Resistance
        # ----------------------------------------------------
        if resistance:

            recommendations.append(
                f"Resistance terdekat: "
                f"${resistance[0]:.2f}."
            )

        # ----------------------------------------------------
        # Agreement warning
        # ----------------------------------------------------
        if model_agreement < 0.45:

            recommendations.append(
                "Model agreement rendah; "
                "forecast perlu dianggap low confidence."
            )

        return recommendations[:6]

    # ========================================================
    # DEFAULT
    # ========================================================

    def _get_default_forecast(
        self,
        symbol: str,
        current_price: float = 0.0,
        reason: str = "No forecast available",
        warnings_list: Optional[List[str]] = None
    ) -> ForecastResult:

        if warnings_list is None:
            warnings_list = []

        if reason not in warnings_list:
            warnings_list.append(
                reason
            )

        now = datetime.now(
            timezone.utc
        )

        if current_price <= 0:

            current_price = 0.0

        def default_prediction(
            horizon: str,
            days: int
        ):

            return PricePrediction(

                timestamp=(
                    now +
                    timedelta(days=days)
                ),

                predicted_price=float(
                    current_price
                ),

                confidence_interval_lower=float(
                    current_price
                ),

                confidence_interval_upper=float(
                    current_price
                ),

                confidence=0.0,

                horizon=horizon,

                predicted_change_percent=0.0
            )

        return ForecastResult(

            symbol=symbol,

            timestamp=now,

            current_price=float(
                current_price
            ),

            short_term=default_prediction(
                "SHORT",
                2
            ),

            medium_term=default_prediction(
                "MEDIUM",
                5
            ),

            long_term=default_prediction(
                "LONG",
                7
            ),

            bullish_path=[
                float(current_price)
            ] * 7,

            bearish_path=[
                float(current_price)
            ] * 7,

            most_likely_path=[
                float(current_price)
            ] * 7,

            scenarios={
                "bullish": {
                    "path": [
                        float(current_price)
                    ] * 7,
                    "probability": 0.25
                },

                "bearish": {
                    "path": [
                        float(current_price)
                    ] * 7,
                    "probability": 0.25
                },

                "most_likely": {
                    "path": [
                        float(current_price)
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

            expected_high=float(
                current_price
            ),

            expected_low=float(
                current_price
            ),

            expected_range={
                "high": float(current_price),
                "low": float(current_price),
                "range_percent": 0.0
            },

            key_resistance=[],
            key_support=[],

            summary=(
                f"Forecast unavailable for "
                f"{symbol}: {reason}"
            ),

            recommendations=[
                "Wait for valid historical data."
            ],

            model_predictions={},

            model_weights={},

            model_status={},

            data_quality={
                "observations": 0.0,
                "return_volatility": 0.0,
                "missing_ratio": 1.0,
                "quality_score": 0.0
            },

            model_agreement=0.0,

            forecast_score=0.0,

            forecast_action="HOLD",

            warnings=warnings_list
        )


# ============================================================
# TEST / MANUAL EXECUTION
# ============================================================

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s"
    )

    print("=" * 70)
    print("FORECAST AGENT V4 TEST")
    print("=" * 70)

    agent = ForecastAgent()

    result = agent.analyze(
        "BTC-USD"
    )

    print("\n" + "=" * 70)
    print("RESULT")
    print("=" * 70)

    print(
        f"Symbol          : {result.symbol}"
    )

    print(
        f"Current Price   : ${result.current_price:,.2f}"
    )

    print(
        f"Trend           : {result.primary_trend}"
    )

    print(
        f"Trend Strength  : {result.trend_strength:.2%}"
    )

    print(
        f"Forecast Score  : {result.forecast_score:+.3f}"
    )

    print(
        f"Forecast Action : {result.forecast_action}"
    )

    print(
        f"Model Agreement : {result.model_agreement:.2%}"
    )

    print("\nNEXT MOVE")

    for direction, probability in (
        result.next_move_probability.items()
    ):

        print(
            f"  {direction:<10}: "
            f"{probability:.2%}"
        )

    print("\nPRICE FORECAST")

    for prediction in [
        result.short_term,
        result.medium_term,
        result.long_term
    ]:

        print(
            f"  {prediction.horizon:<8}: "
            f"${prediction.predicted_price:,.2f} "
            f"({prediction.predicted_change_percent:+.2f}%) "
            f"confidence={prediction.confidence:.2%}"
        )

    print("\nMODEL STATUS")

    for model, status in (
        result.model_status.items()
    ):

        weight = result.model_weights.get(
            model,
            0.0
        )

        print(
            f"  {model:<22} "
            f"{status:<10} "
            f"weight={weight:.2%}"
        )

    print("\nDATA QUALITY")

    for key, value in (
        result.data_quality.items()
    ):

        print(
            f"  {key:<20}: {value}"
        )

    print("\nSUMMARY")
    print(
        result.summary
    )

    print("\nRECOMMENDATIONS")

    for recommendation in (
        result.recommendations
    ):

        print(
            f"  - {recommendation}"
        )

    if result.warnings:

        print("\nWARNINGS")

        for warning in result.warnings:

            print(
                f"  - {warning}"
            )

    print("\n" + "=" * 70)
    print("FORECAST AGENT V4 TEST COMPLETE")
    print("=" * 70)
