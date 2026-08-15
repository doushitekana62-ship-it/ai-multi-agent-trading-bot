"""
Agent 2: Analisis Teknikal - Candlestick & Market Demand
Bertugas menganalisis pola candlestick, support/resistance, volume,
dan indikator teknikal lainnya untuk mengidentifikasi peluang trading.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

import numpy as np
import pandas as pd
import yfinance as yf
import talib


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# RESULT DATA CLASS
# ============================================================

@dataclass
class TechnicalResult:
    """Data class untuk hasil analisis teknikal"""

    symbol: str
    timestamp: datetime
    current_price: float

    # Candlestick patterns
    detected_patterns: List[Dict[str, Any]]
    pattern_score: float

    # Support & Resistance
    support_levels: List[float]
    resistance_levels: List[float]
    current_position: str

    # Technical Indicators
    rsi: float
    macd: Dict[str, float]
    bollinger_bands: Dict[str, float]
    moving_averages: Dict[str, float]

    # Volume Analysis
    volume_score: float
    volume_trend: str

    # Demand / Supply
    demand_score: float
    supply_score: float

    # Overall
    overall_score: float

    # Summary
    summary: str
    recommendations: List[str]


# ============================================================
# TECHNICAL AGENT
# ============================================================

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

        # ----------------------------------------------------
        # Threshold
        # ----------------------------------------------------

        self.thresholds = {
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "volume_threshold": 1.5,
            "pattern_confidence": 0.6,
            "support_resistance_tolerance": 0.02,
        }

        # ----------------------------------------------------
        # Weight
        # ----------------------------------------------------

        self.weights = {
            "patterns": 0.25,
            "indicators": 0.35,
            "volume": 0.15,
            "supply_demand": 0.25,
        }

        # ----------------------------------------------------
        # Cache
        # ----------------------------------------------------

        self.cache = {}
        self.cache_duration = timedelta(minutes=2)

        logger.info("Technical Agent initialized successfully")

    # ========================================================
    # PUBLIC ANALYZE
    # ========================================================

    def analyze(
        self,
        symbol: str,
        market_data: Dict = None
    ) -> TechnicalResult:

        logger.info(f"Analyzing technicals for {symbol}")

        # ----------------------------------------------------
        # Cache
        # ----------------------------------------------------

        cache_key = f"technical_{symbol}"

        if cache_key in self.cache:

            cached_result, cache_time = self.cache[cache_key]

            if datetime.now() - cache_time < self.cache_duration:

                logger.info(
                    f"Using cached technical analysis for {symbol}"
                )

                return cached_result

        try:

            # ------------------------------------------------
            # Market Data
            # ------------------------------------------------

            if market_data and "ohlcv" in market_data:

                df = market_data["ohlcv"]

            else:

                df = self._fetch_historical_data(symbol)

            # ------------------------------------------------
            # Validate Data
            # ------------------------------------------------

            if df is None or len(df) < 100:

                logger.warning(
                    f"Insufficient data for {symbol}"
                )

                return self._get_default_result(symbol)

            # Pastikan index bersih
            df = df.copy()

            # Pastikan kolom utama tersedia
            required_columns = [
                "Open",
                "High",
                "Low",
                "Close",
                "Volume"
            ]

            missing_columns = [
                col for col in required_columns
                if col not in df.columns
            ]

            if missing_columns:

                logger.error(
                    f"Missing columns for {symbol}: "
                    f"{missing_columns}"
                )

                return self._get_default_result(symbol)

            # Buang baris NaN pada data utama
            df = df.dropna(
                subset=[
                    "Open",
                    "High",
                    "Low",
                    "Close"
                ]
            )

            if len(df) < 100:

                logger.warning(
                    f"Insufficient clean data for {symbol}"
                )

                return self._get_default_result(symbol)

            # ------------------------------------------------
            # 1. Candlestick Patterns
            # ------------------------------------------------

            detected_patterns = self._detect_patterns(df)

            pattern_score = self._score_patterns(
                detected_patterns
            )

            # ------------------------------------------------
            # 2. Support / Resistance
            # ------------------------------------------------

            support_levels, resistance_levels = (
                self._find_support_resistance(df)
            )

            current_price = float(
                df["Close"].iloc[-1]
            )

            current_position = self._determine_position(
                current_price,
                support_levels,
                resistance_levels
            )

            # ------------------------------------------------
            # 3. Technical Indicators
            # ------------------------------------------------

            indicators = self._calculate_indicators(df)

            # ------------------------------------------------
            # 4. Volume
            # ------------------------------------------------

            volume_score, volume_trend = (
                self._analyze_volume(df)
            )

            # ------------------------------------------------
            # 5. Supply / Demand
            # ------------------------------------------------

            demand_score, supply_score = (
                self._calculate_supply_demand(df)
            )

            # ------------------------------------------------
            # 6. Overall Score
            # ------------------------------------------------

            overall_score = self._calculate_overall_score({

                "patterns": pattern_score,

                "indicators": indicators[
                    "composite_score"
                ],

                "volume": volume_score,

                "supply_demand":
                    demand_score - supply_score

            })

            # ------------------------------------------------
            # 7. Summary
            # ------------------------------------------------

            summary = self._generate_summary(
                symbol,
                overall_score,
                indicators,
                detected_patterns
            )

            recommendations = (
                self._generate_recommendations(
                    overall_score,
                    indicators,
                    current_position,
                    detected_patterns
                )
            )

            # ------------------------------------------------
            # Result
            # ------------------------------------------------

            result = TechnicalResult(

                symbol=symbol,

                timestamp=datetime.now(),

                current_price=current_price,

                detected_patterns=detected_patterns,

                pattern_score=pattern_score,

                support_levels=support_levels,

                resistance_levels=resistance_levels,

                current_position=current_position,

                rsi=indicators["rsi"],

                macd=indicators["macd"],

                bollinger_bands=indicators[
                    "bollinger_bands"
                ],

                moving_averages=indicators[
                    "moving_averages"
                ],

                volume_score=volume_score,

                volume_trend=volume_trend,

                demand_score=demand_score,

                supply_score=supply_score,

                overall_score=overall_score,

                summary=summary,

                recommendations=recommendations
            )

            # ------------------------------------------------
            # Cache
            # ------------------------------------------------

            self.cache[cache_key] = (
                result,
                datetime.now()
            )

            return result

        except Exception as e:

            logger.exception(
                f"Error analyzing technicals for {symbol}: {e}"
            )

            return self._get_default_result(symbol)

    # ========================================================
    # FETCH HISTORICAL DATA
    # ========================================================

    def _fetch_historical_data(
        self,
        symbol: str
    ) -> Optional[pd.DataFrame]:

        """
        Fetch historical OHLCV data dari Yahoo Finance
        """

        try:

            ticker = yf.Ticker(symbol)

            # Primary:
            # 100 hari dengan interval 1 jam
            df = ticker.history(
                period="100d",
                interval="1h"
            )

            # Fallback
            if df is None or df.empty:

                logger.warning(
                    f"Hourly data unavailable for {symbol}, "
                    f"using daily fallback"
                )

                df = ticker.history(
                    period="1y",
                    interval="1d"
                )

            if df is None or df.empty:

                logger.warning(
                    f"No historical data available for {symbol}"
                )

                return None

            return df

        except Exception as e:

            logger.error(
                f"Error fetching data for {symbol}: {e}"
            )

            return None

    # ========================================================
    # CANDLESTICK PATTERNS
    # ========================================================

    def _detect_patterns(
        self,
        df: pd.DataFrame
    ) -> List[Dict[str, Any]]:

        patterns = []

        required_cols = [
            "Open",
            "High",
            "Low",
            "Close"
        ]

        if not all(
            col in df.columns
            for col in required_cols
        ):

            return patterns

        open_price = df["Open"].astype(float).values
        high_price = df["High"].astype(float).values
        low_price = df["Low"].astype(float).values
        close_price = df["Close"].astype(float).values

        pattern_functions = {

            "hammer":
                talib.CDLHAMMER,

            "doji":
                talib.CDLDOJI,

            "engulfing":
                talib.CDLENGULFING,

            "morning_star":
                talib.CDLMORNINGSTAR,

            "evening_star":
                talib.CDLEVENINGSTAR,

            "three_white_soldiers":
                talib.CDL3WHITESOLDIERS,

            "three_black_crows":
                talib.CDL3BLACKCROWS,

            "shooting_star":
                talib.CDLSHOOTINGSTAR,

            "hanging_man":
                talib.CDLHANGINGMAN,

            "harami":
                talib.CDLHARAMI,

            "piercing":
                talib.CDLPIERCING,

            "dark_cloud_cover":
                talib.CDLDARKCLOUDCOVER,

            "doji_star":
                talib.CDLDOJISTAR,

            "spinning_top":
                talib.CDLSPINNINGTOP
        }

        for pattern_name, func in pattern_functions.items():

            try:

                result = func(
                    open_price,
                    high_price,
                    low_price,
                    close_price
                )

                last_value = (
                    result[-1]
                    if len(result) > 0
                    else 0
                )

                if last_value != 0:

                    confidence = min(
                        abs(float(last_value)) / 100,
                        1.0
                    )

                    patterns.append({

                        "name":
                            pattern_name,

                        "signal":
                            "BULLISH"
                            if last_value > 0
                            else "BEARISH",

                        "confidence":
                            confidence,

                        "strength":
                            confidence
                    })

            except Exception as e:

                logger.debug(
                    f"Error detecting pattern "
                    f"{pattern_name}: {e}"
                )

                continue

        patterns = [
            p for p in patterns
            if p["confidence"] > 0.3
        ]

        patterns.sort(
            key=lambda x: x["confidence"],
            reverse=True
        )

        return patterns[:5]

    # ========================================================
    # SCORE PATTERNS
    # ========================================================

    def _score_patterns(
        self,
        patterns: List[Dict[str, Any]]
    ) -> float:

        if not patterns:
            return 0.0

        bullish_score = 0.0
        bearish_score = 0.0

        for pattern in patterns:

            contribution = (
                pattern["confidence"]
                * pattern["strength"]
            )

            if pattern["signal"] == "BULLISH":

                bullish_score += contribution

            else:

                bearish_score += contribution

        total_score = (
            bullish_score
            - bearish_score
        )

        total_confidence = (
            bullish_score
            + bearish_score
        )

        if total_confidence > 0:

            return float(
                np.clip(
                    total_score
                    / total_confidence,
                    -1.0,
                    1.0
                )
            )

        return 0.0

    # ========================================================
    # SUPPORT / RESISTANCE
    # ========================================================

    def _find_support_resistance(
        self,
        df: pd.DataFrame
    ) -> Tuple[List[float], List[float]]:

        high = df["High"].astype(float).values
        low = df["Low"].astype(float).values

        window = 20

        local_max = []
        local_min = []

        if len(high) <= window * 2:

            return [], []

        for i in range(
            window,
            len(high) - window
        ):

            high_window = high[
                i - window:
                i + window + 1
            ]

            low_window = low[
                i - window:
                i + window + 1
            ]

            if high[i] >= np.max(high_window):

                local_max.append(
                    float(high[i])
                )

            if low[i] <= np.min(low_window):

                local_min.append(
                    float(low[i])
                )

        resistance_levels = (
            self._cluster_values(
                local_max,
                tolerance=self.thresholds[
                    "support_resistance_tolerance"
                ]
            )
        )

        support_levels = (
            self._cluster_values(
                local_min,
                tolerance=self.thresholds[
                    "support_resistance_tolerance"
                ]
            )
        )

        resistance_levels.sort(
            reverse=True
        )

        support_levels.sort()

        return (
            support_levels[:3],
            resistance_levels[:3]
        )

    # ========================================================
    # CLUSTER VALUES
    # ========================================================

    def _cluster_values(
        self,
        values: List[float],
        tolerance: float = 0.02
    ) -> List[float]:

        if not values:
            return []

        values = sorted(
            float(v)
            for v in values
            if np.isfinite(v)
            and v > 0
        )

        if not values:
            return []

        clusters = []

        current_cluster = [
            values[0]
        ]

        for val in values[1:]:

            cluster_avg = (
                sum(current_cluster)
                / len(current_cluster)
            )

            if cluster_avg != 0:

                relative_difference = (
                    abs(val - cluster_avg)
                    / cluster_avg
                )

            else:

                relative_difference = 0

            if relative_difference <= tolerance:

                current_cluster.append(val)

            else:

                clusters.append(
                    sum(current_cluster)
                    / len(current_cluster)
                )

                current_cluster = [val]

        if current_cluster:

            clusters.append(
                sum(current_cluster)
                / len(current_cluster)
            )

        return clusters

    # ========================================================
    # DETERMINE POSITION
    # ========================================================

    def _determine_position(
        self,
        price: float,
        support: List[float],
        resistance: List[float]
    ) -> str:

        if (
            not support
            and not resistance
        ):

            return "MIDDLE"

        nearest_support = (
            min(
                support,
                key=lambda x: abs(x - price)
            )
            if support
            else None
        )

        nearest_resistance = (
            min(
                resistance,
                key=lambda x: abs(x - price)
            )
            if resistance
            else None
        )

        support_diff = (
            abs(price - nearest_support)
            / price
            if nearest_support is not None
            and price != 0
            else float("inf")
        )

        resistance_diff = (
            abs(price - nearest_resistance)
            / price
            if nearest_resistance is not None
            and price != 0
            else float("inf")
        )

        if support_diff < 0.02:

            return "NEAR_SUPPORT"

        if resistance_diff < 0.02:

            return "NEAR_RESISTANCE"

        return "MIDDLE"

    # ========================================================
    # CALCULATE INDICATORS
    # ========================================================

    def _calculate_indicators(
        self,
        df: pd.DataFrame
    ) -> Dict[str, Any]:

        close = df["Close"].astype(float).values
        high = df["High"].astype(float).values
        low = df["Low"].astype(float).values

        # ----------------------------------------------------
        # RSI
        # ----------------------------------------------------

        rsi = talib.RSI(
            close,
            timeperiod=14
        )

        current_rsi = (
            float(rsi[-1])
            if len(rsi) > 0
            and np.isfinite(rsi[-1])
            else 50.0
        )

        # ----------------------------------------------------
        # MACD
        # ----------------------------------------------------

        macd, macd_signal, macd_hist = talib.MACD(
            close
        )

        current_macd = {

            "macd":
                float(macd[-1])
                if len(macd) > 0
                and np.isfinite(macd[-1])
                else 0.0,

            "signal":
                float(macd_signal[-1])
                if len(macd_signal) > 0
                and np.isfinite(macd_signal[-1])
                else 0.0,

            "histogram":
                float(macd_hist[-1])
                if len(macd_hist) > 0
                and np.isfinite(macd_hist[-1])
                else 0.0
        }

        # ----------------------------------------------------
        # Bollinger Bands
        # ----------------------------------------------------

        upper, middle, lower = talib.BBANDS(
            close,
            timeperiod=20,
            nbdevup=2,
            nbdevdn=2
        )

        current_price = float(
            close[-1]
        )

        upper_value = (
            float(upper[-1])
            if len(upper) > 0
            and np.isfinite(upper[-1])
            else current_price * 1.1
        )

        middle_value = (
            float(middle[-1])
            if len(middle) > 0
            and np.isfinite(middle[-1])
            else current_price
        )

        lower_value = (
            float(lower[-1])
            if len(lower) > 0
            and np.isfinite(lower[-1])
            else current_price * 0.9
        )

        bb_position = self._get_bb_position(
            current_price,
            upper_value,
            lower_value
        )

        current_bands = {

            "upper":
                upper_value,

            "middle":
                middle_value,

            "lower":
                lower_value,

            "position":
                bb_position
        }

        # ----------------------------------------------------
        # Moving Averages
        # ----------------------------------------------------

        ma_10_array = talib.SMA(
            close,
            timeperiod=10
        )

        ma_20_array = talib.SMA(
            close,
            timeperiod=20
        )

        ma_50_array = talib.SMA(
            close,
            timeperiod=50
        )

        ma_200_array = talib.SMA(
            close,
            timeperiod=200
        )

        ma_10 = self._safe_last(
            ma_10_array,
            current_price
        )

        ma_20 = self._safe_last(
            ma_20_array,
            current_price
        )

        ma_50 = self._safe_last(
            ma_50_array,
            current_price
        )

        ma_200 = self._safe_last(
            ma_200_array,
            current_price
        )

        ma_values = [
            ma_10,
            ma_20,
            ma_50
        ]

        ma_trend = self._get_ma_trend(
            current_price,
            ma_values
        )

        # ----------------------------------------------------
        # Trend Strength
        # ----------------------------------------------------

        trend_strength = (
            self._calculate_trend_strength(
                high,
                low,
                close
            )
        )

        # ----------------------------------------------------
        # Composite Score
        # ----------------------------------------------------

        composite_score = (
            self._score_indicators({

                "rsi":
                    current_rsi,

                "macd":
                    current_macd,

                "bb_position":
                    bb_position,

                "ma_trend":
                    ma_trend

            })
        )

        return {

            "rsi":
                current_rsi,

            "macd":
                current_macd,

            "bollinger_bands":
                current_bands,

            "moving_averages": {

                "MA10":
                    ma_10,

                "MA20":
                    ma_20,

                "MA50":
                    ma_50,

                "MA200":
                    ma_200
            },

            "trend_strength":
                trend_strength,

            "composite_score":
                composite_score
        }

    # ========================================================
    # SAFE LAST
    # ========================================================

    def _safe_last(
        self,
        values: np.ndarray,
        fallback: float
    ) -> float:

        if (
            values is not None
            and len(values) > 0
            and np.isfinite(values[-1])
        ):

            return float(values[-1])

        return float(fallback)

    # ========================================================
    # BOLLINGER POSITION
    # ========================================================

    def _get_bb_position(
        self,
        price: float,
        upper: float,
        lower: float
    ) -> str:

        if price >= upper * 0.98:

            return "NEAR_UPPER"

        elif price <= lower * 1.02:

            return "NEAR_LOWER"

        return "MIDDLE"

    # ========================================================
    # MA TREND
    # ========================================================

    def _get_ma_trend(
        self,
        price: float,
        ma_values: List[float]
    ) -> str:

        valid_values = [
            ma for ma in ma_values
            if ma is not None
            and np.isfinite(ma)
            and ma > 0
        ]

        if not valid_values:

            return "NEUTRAL"

        bullish_count = sum(
            1
            for ma in valid_values
            if price > ma
        )

        bearish_count = sum(
            1
            for ma in valid_values
            if price < ma
        )

        if bullish_count >= 2:

            return "BULLISH"

        elif bearish_count >= 2:

            return "BEARISH"

        return "NEUTRAL"

    # ========================================================
    # SCORE INDICATORS
    # ========================================================

    def _score_indicators(
        self,
        indicators: Dict
    ) -> float:

        score = 0.0

        # ----------------------------------------------------
        # RSI
        # ----------------------------------------------------

        rsi = indicators.get(
            "rsi",
            50
        )

        if rsi < 30:

            score += 0.5

        elif rsi > 70:

            score -= 0.5

        else:

            score += (
                (50 - rsi)
                / 100
            )

        # ----------------------------------------------------
        # MACD
        # ----------------------------------------------------

        macd = indicators.get(
            "macd",
            {}
        )

        histogram = macd.get(
            "histogram",
            0
        )

        if histogram > 0:

            score += 0.3

        elif histogram < 0:

            score -= 0.3

        # ----------------------------------------------------
        # Bollinger
        # ----------------------------------------------------

        bb_pos = indicators.get(
            "bb_position",
            "MIDDLE"
        )

        if bb_pos == "NEAR_LOWER":

            score += 0.3

        elif bb_pos == "NEAR_UPPER":

            score -= 0.3

        # ----------------------------------------------------
        # Moving Average
        # ----------------------------------------------------

        ma_trend = indicators.get(
            "ma_trend",
            "NEUTRAL"
        )

        if ma_trend == "BULLISH":

            score += 0.2

        elif ma_trend == "BEARISH":

            score -= 0.2

        return float(
            np.clip(
                score,
                -1.0,
                1.0
            )
        )

    # ========================================================
    # TREND STRENGTH
    # ========================================================

    def _calculate_trend_strength(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray
    ) -> float:

        """
        Calculate trend strength using ADX.

        ADX membutuhkan High, Low, Close.
        """

        try:

            adx = talib.ADX(
                high,
                low,
                close,
                timeperiod=14
            )

            if (
                adx is None
                or len(adx) == 0
                or not np.isfinite(adx[-1])
            ):

                return 0.5

            return float(
                np.clip(
                    adx[-1] / 100,
                    0.0,
                    1.0
                )
            )

        except Exception as e:

            logger.debug(
                f"ADX calculation error: {e}"
            )

            return 0.5

    # ========================================================
    # VOLUME
    # ========================================================

    def _analyze_volume(
        self,
        df: pd.DataFrame
    ) -> Tuple[float, str]:

        volume = (
            df["Volume"]
            .astype(float)
            .values
        )

        if len(volume) < 20:

            return 0.0, "STABLE"

        avg_volume = np.mean(
            volume[-20:-1]
        )

        current_volume = volume[-1]

        if avg_volume <= 0:

            return 0.0, "STABLE"

        volume_trend = "STABLE"

        if (
            current_volume
            > avg_volume
            * self.thresholds[
                "volume_threshold"
            ]
        ):

            volume_trend = "INCREASING"

        elif (
            current_volume
            < avg_volume * 0.5
        ):

            volume_trend = "DECREASING"

        # ----------------------------------------------------
        # Volume Score
        # ----------------------------------------------------

        previous_close = float(
            df["Close"].iloc[-2]
        )

        current_close = float(
            df["Close"].iloc[-1]
        )

        if previous_close != 0:

            price_change = (
                current_close
                - previous_close
            ) / previous_close

        else:

            price_change = 0.0

        if volume_trend == "INCREASING":

            if price_change > 0:

                volume_score = 0.5

            elif price_change < 0:

                volume_score = -0.5

            else:

                volume_score = 0.0

        else:

            volume_score = 0.0

        return (
            float(volume_score),
            volume_trend
        )

    # ========================================================
    # SUPPLY / DEMAND
    # ========================================================

    def _calculate_supply_demand(
        self,
        df: pd.DataFrame
    ) -> Tuple[float, float]:

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

        close = (
            df["Close"]
            .astype(float)
            .values
        )

        volume = (
            df["Volume"]
            .astype(float)
            .values
        )

        if len(close) == 0:

            return 0.5, 0.5

        min_price = np.min(low)
        max_price = np.max(high)

        if (
            not np.isfinite(min_price)
            or not np.isfinite(max_price)
            or min_price >= max_price
        ):

            return 0.5, 0.5

        price_bins = np.linspace(
            min_price,
            max_price,
            20
        )

        volume_profile = []

        for i in range(
            len(price_bins) - 1
        ):

            mask = (
                (close >= price_bins[i])
                &
                (close < price_bins[i + 1])
            )

            if np.any(mask):

                volume_sum = float(
                    np.sum(volume[mask])
                )

                volume_profile.append({

                    "price_level":
                        (
                            price_bins[i]
                            + price_bins[i + 1]
                        ) / 2,

                    "volume":
                        volume_sum
                })

        if not volume_profile:

            return 0.5, 0.5

        volumes = [
            item["volume"]
            for item in volume_profile
        ]

        max_volume = max(
            volumes
        )

        if max_volume <= 0:

            return 0.5, 0.5

        for item in volume_profile:

            item["volume_ratio"] = (
                item["volume"]
                / max_volume
            )

        current_price = close[-1]

        demand_nodes = [

            item
            for item in volume_profile

            if (
                item["volume_ratio"] > 0.5
                and item["price_level"]
                < current_price
            )
        ]

        supply_nodes = [

            item
            for item in volume_profile

            if (
                item["volume_ratio"] > 0.5
                and item["price_level"]
                > current_price
            )
        ]

        demand_score = float(
            min(
                len(demand_nodes) / 5,
                1.0
            )
        )

        supply_score = float(
            min(
                len(supply_nodes) / 5,
                1.0
            )
        )

        return (
            demand_score,
            supply_score
        )

    # ========================================================
    # OVERALL SCORE
    # ========================================================

    def _calculate_overall_score(
        self,
        components: Dict[str, float]
    ) -> float:

        total_score = 0.0
        total_weight = 0.0

        for comp, score in components.items():

            weight = self.weights.get(
                comp,
                0.1
            )

            total_score += (
                float(score)
                * weight
            )

            total_weight += weight

        if total_weight > 0:

            return float(
                np.clip(
                    total_score
                    / total_weight,
                    -1.0,
                    1.0
                )
            )

        return 0.0

    # ========================================================
    # SUMMARY
    # ========================================================

    def _generate_summary(
        self,
        symbol: str,
        score: float,
        indicators: Dict,
        patterns: List
    ) -> str:

        symbol_name = (
            symbol
            .replace("-USD", "")
            .replace("-USDT", "")
        )

        if score > 0.3:

            signal = "bullish"
            action = "mempertimbangkan posisi BUY"

        elif score < -0.3:

            signal = "bearish"
            action = "mempertimbangkan posisi SELL"

        else:

            signal = "netral"
            action = "wait and see"

        summary = (
            f"Analisis teknikal {symbol_name} "
            f"menunjukkan sinyal {signal} "
            f"(score: {score:.2f}). "
        )

        # RSI
        rsi = indicators.get(
            "rsi",
            50
        )

        if rsi > 70:

            summary += (
                f"RSI di {rsi:.1f} "
                f"menunjukkan kondisi overbought. "
            )

        elif rsi < 30:

            summary += (
                f"RSI di {rsi:.1f} "
                f"menunjukkan kondisi oversold. "
            )

        # Pattern
        if patterns:

            top_pattern = patterns[0]

            summary += (
                f"Terdeteksi pola "
                f"{top_pattern['name']} "
                f"dengan sinyal "
                f"{top_pattern['signal']}. "
            )

        summary += (
            f"Rekomendasi: {action}."
        )

        return summary

    # ========================================================
    # RECOMMENDATIONS
    # ========================================================

    def _generate_recommendations(
        self,
        score: float,
        indicators: Dict,
        position: str,
        patterns: List
    ) -> List[str]:

        recommendations = []

        # ----------------------------------------------------
        # Overall
        # ----------------------------------------------------

        if score > 0.5:

            recommendations.append(
                "STRONG BUY - Semua indikator bullish"
            )

        elif score > 0.2:

            recommendations.append(
                "BUY - Indikator cenderung bullish"
            )

        elif score < -0.5:

            recommendations.append(
                "STRONG SELL - Semua indikator bearish"
            )

        elif score < -0.2:

            recommendations.append(
                "SELL - Indikator cenderung bearish"
            )

        else:

            recommendations.append(
                "HOLD - Tidak ada sinyal jelas"
            )

        # ----------------------------------------------------
        # RSI
        # ----------------------------------------------------

        rsi = indicators.get(
            "rsi",
            50
        )

        if rsi < 25:

            recommendations.append(
                "RSI sangat oversold - Potensi rebound"
            )

        elif rsi > 75:

            recommendations.append(
                "RSI sangat overbought - Waspada koreksi"
            )

        # ----------------------------------------------------
        # Support / Resistance
        # ----------------------------------------------------

        if position == "NEAR_SUPPORT":

            recommendations.append(
                "Dekat level support - Potensi bounce"
            )

        elif position == "NEAR_RESISTANCE":

            recommendations.append(
                "Dekat level resistance - "
                "Waspada rejection"
            )

        # ----------------------------------------------------
        # Pattern
        # ----------------------------------------------------

        if patterns:

            top_pattern = patterns[0]

            if (
                top_pattern["signal"] == "BULLISH"
                and top_pattern["confidence"] > 0.7
            ):

                recommendations.append(
                    "Konfirmasi bullish dari pola "
                    f"{top_pattern['name']}"
                )

            elif (
                top_pattern["signal"] == "BEARISH"
                and top_pattern["confidence"] > 0.7
            ):

                recommendations.append(
                    "Konfirmasi bearish dari pola "
                    f"{top_pattern['name']}"
                )

        return recommendations[:3]

    # ========================================================
    # DEFAULT RESULT
    # ========================================================

    def _get_default_result(
        self,
        symbol: str
    ) -> TechnicalResult:

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

            macd={
                "macd": 0.0,
                "signal": 0.0,
                "histogram": 0.0
            },

            bollinger_bands={
                "upper": 0.0,
                "middle": 0.0,
                "lower": 0.0,
                "position": "MIDDLE"
            },

            moving_averages={
                "MA10": 0.0,
                "MA20": 0.0,
                "MA50": 0.0,
                "MA200": 0.0
            },

            volume_score=0.0,

            volume_trend="STABLE",

            demand_score=0.5,

            supply_score=0.5,

            overall_score=0.0,

            summary=(
                f"Unable to analyze technicals "
                f"for {symbol}. Default to neutral."
            ),

            recommendations=[
                "HOLD - Insufficient data"
            ]
        )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    agent = TechnicalAgent()

    symbol = "BTC-USD"

    result = agent.analyze(symbol)

    print("=" * 60)
    print(
        f"Technical Analysis Result for "
        f"{result.symbol}"
    )
    print("=" * 60)

    print(
        f"Current Price: "
        f"${result.current_price:.2f}"
    )

    print(
        f"Overall Score: "
        f"{result.overall_score:.3f}"
    )

    print(
        f"Pattern Score: "
        f"{result.pattern_score:.3f}"
    )

    print(
        f"RSI: "
        f"{result.rsi:.1f}"
    )

    print(
        f"Volume Trend: "
        f"{result.volume_trend}"
    )

    print(
        f"Volume Score: "
        f"{result.volume_score:.3f}"
    )

    print(
        f"Demand Score: "
        f"{result.demand_score:.3f}"
    )

    print(
        f"Supply Score: "
        f"{result.supply_score:.3f}"
    )

    print(
        f"Position: "
        f"{result.current_position}"
    )

    print("\nSupport Levels:")

    for support in result.support_levels:

        print(
            f"  ${support:.2f}"
        )

    print("\nResistance Levels:")

    for resistance in result.resistance_levels:

        print(
            f"  ${resistance:.2f}"
        )

    print("\nDetected Patterns:")

    if result.detected_patterns:

        for pattern in result.detected_patterns:

            print(
                f"  - {pattern['name']}: "
                f"{pattern['signal']} "
                f"(confidence: "
                f"{pattern['confidence']:.2%})"
            )

    else:

        print(
            "  No pattern detected"
        )

    print("\nMACD:")

    print(
        f"  MACD: "
        f"{result.macd['macd']:.4f}"
    )

    print(
        f"  Signal: "
        f"{result.macd['signal']:.4f}"
    )

    print(
        f"  Histogram: "
        f"{result.macd['histogram']:.4f}"
    )

    print("\nBollinger Bands:")

    print(
        f"  Upper: "
        f"${result.bollinger_bands['upper']:.2f}"
    )

    print(
        f"  Middle: "
        f"${result.bollinger_bands['middle']:.2f}"
    )

    print(
        f"  Lower: "
        f"${result.bollinger_bands['lower']:.2f}"
    )

    print(
        f"  Position: "
        f"{result.bollinger_bands['position']}"
    )

    print("\nMoving Averages:")

    for name, value in result.moving_averages.items():

        print(
            f"  {name}: "
            f"${value:.2f}"
        )

    print(
        f"\nSummary:\n"
        f"{result.summary}"
    )

    print("\nRecommendations:")

    for rec in result.recommendations:

        print(
            f"  • {rec}"
        )
