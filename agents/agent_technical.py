"""
Agent 2: Analisis Teknikal - Candlestick & Market Demand

Bertugas menganalisis:
- pola candlestick
- support / resistance
- volume
- RSI
- MACD
- Bollinger Bands
- Moving Average
- supply / demand
- indikator teknikal lainnya

untuk mengidentifikasi kondisi pasar.

CATATAN:
Agent ini TIDAK melakukan trading execution.
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


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


# ============================================================
# RESULT DATACLASS
# ============================================================

@dataclass
class TechnicalResult:
    """
    Data class untuk hasil analisis teknikal.
    """

    symbol: str

    timestamp: datetime

    current_price: float

    # --------------------------------------------------------
    # Candlestick patterns
    # --------------------------------------------------------

    detected_patterns: List[Dict[str, Any]]

    pattern_score: float
    # -1 = bearish
    #  0 = neutral
    # +1 = bullish

    # --------------------------------------------------------
    # Support & Resistance
    # --------------------------------------------------------

    support_levels: List[float]

    resistance_levels: List[float]

    current_position: str
    # NEAR_SUPPORT
    # NEAR_RESISTANCE
    # MIDDLE

    # --------------------------------------------------------
    # Technical Indicators
    # --------------------------------------------------------

    rsi: float

    macd: Dict[str, float]

    bollinger_bands: Dict[str, float]

    moving_averages: Dict[str, float]

    # --------------------------------------------------------
    # Volume Analysis
    # --------------------------------------------------------

    volume_score: float

    volume_trend: str
    # INCREASING
    # DECREASING
    # STABLE

    # --------------------------------------------------------
    # Demand / Supply
    # --------------------------------------------------------

    demand_score: float
    # 0 - 1

    supply_score: float
    # 0 - 1

    # --------------------------------------------------------
    # Overall
    # --------------------------------------------------------

    overall_score: float
    # -1 = bearish
    #  0 = neutral
    # +1 = bullish

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    summary: str

    recommendations: List[str]


# ============================================================
# TECHNICAL AGENT
# ============================================================

class TechnicalAgent:

    """
    Agent Analisis Teknikal dengan kemampuan multi-indicator.
    """

    def __init__(
        self,
        config: Dict = None
    ):

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
        # Weights
        #
        # Total = 1.00
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

        self.cache_duration = timedelta(
            minutes=2
        )

        logger.info(
            "Technical Agent initialized successfully"
        )

    # ========================================================
    # PUBLIC ANALYZE
    # ========================================================

    def analyze(
        self,
        symbol: str,
        market_data: Dict = None
    ) -> TechnicalResult:

        """
        Main method untuk analisis teknikal.

        Args:
            symbol:
                Contoh BTC-USD

            market_data:
                Data pasar opsional.

        Returns:
            TechnicalResult
        """

        logger.info(
            f"Analyzing technicals for {symbol}"
        )

        market_data = market_data or {}

        # ----------------------------------------------------
        # Cache
        # ----------------------------------------------------

        cache_key = (
            f"technical_{symbol}"
        )

        if cache_key in self.cache:

            cached_result, cache_time = (
                self.cache[cache_key]
            )

            if (
                datetime.now() - cache_time
                < self.cache_duration
            ):

                logger.info(
                    f"Using cached technical "
                    f"analysis for {symbol}"
                )

                return cached_result

        try:

            # ------------------------------------------------
            # Fetch / use market data
            # ------------------------------------------------

            if (
                market_data
                and "ohlcv" in market_data
            ):

                df = market_data["ohlcv"]

            else:

                df = (
                    self._fetch_historical_data(
                        symbol
                    )
                )

            # ------------------------------------------------
            # Validate data
            # ------------------------------------------------

            if df is None:

                logger.warning(
                    f"No data available for {symbol}"
                )

                return self._get_default_result(
                    symbol
                )

            if not isinstance(
                df,
                pd.DataFrame
            ):

                logger.warning(
                    f"Invalid OHLCV type for {symbol}"
                )

                return self._get_default_result(
                    symbol
                )

            required_cols = [
                "Open",
                "High",
                "Low",
                "Close",
                "Volume",
            ]

            if not all(
                col in df.columns
                for col in required_cols
            ):

                logger.warning(
                    f"Missing OHLCV columns "
                    f"for {symbol}"
                )

                return self._get_default_result(
                    symbol
                )

            # ------------------------------------------------
            # Clean OHLCV
            # ------------------------------------------------

            df = (
                df[required_cols]
                .copy()
            )

            df = df.replace(
                [np.inf, -np.inf],
                np.nan
            )

            df = df.dropna(
                subset=[
                    "Open",
                    "High",
                    "Low",
                    "Close",
                    "Volume",
                ]
            )

            # ------------------------------------------------
            # Minimum data
            # ------------------------------------------------

            if len(df) < 100:

                logger.warning(
                    f"Insufficient data "
                    f"for {symbol}: "
                    f"{len(df)} rows"
                )

                return self._get_default_result(
                    symbol
                )

            # ------------------------------------------------
            # Ensure numeric
            # ------------------------------------------------

            for column in required_cols:

                df[column] = pd.to_numeric(
                    df[column],
                    errors="coerce"
                )

            df = df.dropna(
                subset=required_cols
            )

            if len(df) < 100:

                logger.warning(
                    f"Insufficient valid data "
                    f"for {symbol}"
                )

                return self._get_default_result(
                    symbol
                )

            # ------------------------------------------------
            # 1. Candlestick Patterns
            # ------------------------------------------------

            detected_patterns = (
                self._detect_patterns(df)
            )

            pattern_score = (
                self._score_patterns(
                    detected_patterns
                )
            )

            # ------------------------------------------------
            # 2. Support / Resistance
            # ------------------------------------------------

            (
                support_levels,
                resistance_levels
            ) = self._find_support_resistance(
                df
            )

            current_price = float(
                df["Close"].iloc[-1]
            )

            current_position = (
                self._determine_position(
                    current_price,
                    support_levels,
                    resistance_levels
                )
            )

            # ------------------------------------------------
            # 3. Technical Indicators
            # ------------------------------------------------

            indicators = (
                self._calculate_indicators(
                    df
                )
            )

            # ------------------------------------------------
            # 4. Volume
            # ------------------------------------------------

            (
                volume_score,
                volume_trend
            ) = self._analyze_volume(
                df
            )

            # ------------------------------------------------
            # 5. Supply / Demand
            # ------------------------------------------------

            (
                demand_score,
                supply_score
            ) = self._calculate_supply_demand(
                df
            )

            # ------------------------------------------------
            # 6. Overall Score
            # ------------------------------------------------

            overall_score = (
                self._calculate_overall_score(
                    {
                        "patterns":
                            pattern_score,

                        "indicators":
                            indicators[
                                "composite_score"
                            ],

                        "volume":
                            volume_score,

                        "supply_demand":
                            demand_score
                            - supply_score,
                    }
                )
            )

            # ------------------------------------------------
            # 7. Summary
            # ------------------------------------------------

            summary = (
                self._generate_summary(
                    symbol,
                    overall_score,
                    indicators,
                    detected_patterns
                )
            )

            # ------------------------------------------------
            # 8. Recommendations
            # ------------------------------------------------

            recommendations = (
                self._generate_recommendations(
                    overall_score,
                    indicators,
                    current_position,
                    detected_patterns
                )
            )

            # ------------------------------------------------
            # Build result
            # ------------------------------------------------

            result = TechnicalResult(

                symbol=symbol,

                timestamp=datetime.now(),

                current_price=current_price,

                detected_patterns=(
                    detected_patterns
                ),

                pattern_score=pattern_score,

                support_levels=(
                    support_levels
                ),

                resistance_levels=(
                    resistance_levels
                ),

                current_position=(
                    current_position
                ),

                rsi=indicators["rsi"],

                macd=indicators["macd"],

                bollinger_bands=(
                    indicators[
                        "bollinger_bands"
                    ]
                ),

                moving_averages=(
                    indicators[
                        "moving_averages"
                    ]
                ),

                volume_score=volume_score,

                volume_trend=volume_trend,

                demand_score=demand_score,

                supply_score=supply_score,

                overall_score=overall_score,

                summary=summary,

                recommendations=recommendations,

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
                f"Error analyzing technicals "
                f"for {symbol}: {e}"
            )

            return self._get_default_result(
                symbol
            )

    # ========================================================
    # FETCH HISTORICAL DATA
    # ========================================================

    def _fetch_historical_data(
        self,
        symbol: str
    ) -> Optional[pd.DataFrame]:

        """
        Fetch historical OHLCV data
        dari Yahoo Finance.

        Primary:
            100d / 1h

        Fallback:
            100d / 1d
        """

        try:

            ticker = yf.Ticker(
                symbol
            )

            # ------------------------------------------------
            # Primary
            # ------------------------------------------------

            df = ticker.history(
                period="100d",
                interval="1h"
            )

            if df is None or df.empty:

                # --------------------------------------------
                # Fallback daily
                # --------------------------------------------

                df = ticker.history(
                    period="100d"
                )

            if df is None or df.empty:

                return None

            return df

        except Exception as e:

            logger.error(
                f"Error fetching data "
                f"for {symbol}: {e}"
            )

            return None

    # ========================================================
    # CANDLESTICK PATTERNS
    # ========================================================

    def _detect_patterns(
        self,
        df: pd.DataFrame
    ) -> List[Dict[str, Any]]:

        """
        Mendeteksi candlestick patterns
        menggunakan TA-Lib.

        Returns:
            List pattern dengan signal
            dan confidence.
        """

        patterns = []

        required_cols = [
            "Open",
            "High",
            "Low",
            "Close",
        ]

        if not all(
            col in df.columns
            for col in required_cols
        ):

            return patterns

        # ----------------------------------------------------
        # OHLC arrays
        # ----------------------------------------------------

        open_price = (
            df["Open"]
            .astype(float)
            .values
        )

        high_price = (
            df["High"]
            .astype(float)
            .values
        )

        low_price = (
            df["Low"]
            .astype(float)
            .values
        )

        close_price = (
            df["Close"]
            .astype(float)
            .values
        )

        # ----------------------------------------------------
        # Pattern functions
        #
        # NOTE:
        # Harami sengaja hanya satu detector.
        # TA-Lib menentukan bullish / bearish
        # melalui sign output.
        # ----------------------------------------------------

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
                talib.CDLSPINNINGTOP,
        }

        # ----------------------------------------------------
        # Detect
        # ----------------------------------------------------

        for (
            pattern_name,
            func
        ) in pattern_functions.items():

            try:

                result = func(
                    open_price,
                    high_price,
                    low_price,
                    close_price
                )

                if (
                    result is None
                    or len(result) == 0
                ):

                    continue

                last_value = result[-1]

                if (
                    last_value is None
                    or not np.isfinite(
                        last_value
                    )
                ):

                    continue

                if last_value == 0:

                    continue

                signal = (
                    "BULLISH"
                    if last_value > 0
                    else "BEARISH"
                )

                strength = float(
                    min(
                        abs(
                            float(last_value)
                        ) / 100.0,
                        1.0
                    )
                )

                confidence = strength

                patterns.append(
                    {
                        "name":
                            pattern_name,

                        "signal":
                            signal,

                        "confidence":
                            confidence,

                        "strength":
                            strength,
                    }
                )

            except Exception as e:

                logger.debug(
                    f"Error detecting "
                    f"pattern "
                    f"{pattern_name}: {e}"
                )

                continue

        # ----------------------------------------------------
        # Filter
        # ----------------------------------------------------

        patterns = [
            p
            for p in patterns
            if p["confidence"]
            > 0.3
        ]

        # ----------------------------------------------------
        # Sort strongest first
        # ----------------------------------------------------

        patterns.sort(
            key=lambda x:
                x["confidence"],
            reverse=True
        )

        # ----------------------------------------------------
        # Top 5
        # ----------------------------------------------------

        return patterns[:5]

    # ========================================================
    # PATTERN SCORE
    # ========================================================

    def _score_patterns(
        self,
        patterns: List[Dict[str, Any]]
    ) -> float:

        """
        Score detected patterns.

        Returns:
            -1 sampai +1
        """

        if not patterns:

            return 0.0

        bullish_score = 0.0

        bearish_score = 0.0

        for pattern in patterns:

            confidence = float(
                pattern.get(
                    "confidence",
                    0.0
                )
                or 0.0
            )

            strength = float(
                pattern.get(
                    "strength",
                    0.0
                )
                or 0.0
            )

            contribution = (
                confidence
                * strength
            )

            if (
                pattern.get("signal")
                == "BULLISH"
            ):

                bullish_score += (
                    contribution
                )

            else:

                bearish_score += (
                    contribution
                )

        total_score = (
            bullish_score
            - bearish_score
        )

        total_confidence = (
            bullish_score
            + bearish_score
        )

        if total_confidence <= 0:

            return 0.0

        return float(
            np.clip(
                total_score
                / total_confidence,
                -1.0,
                1.0
            )
        )

    # ========================================================
    # SUPPORT / RESISTANCE
    # ========================================================

    def _find_support_resistance(
        self,
        df: pd.DataFrame
    ) -> Tuple[
        List[float],
        List[float]
    ]:

        """
        Find support dan resistance
        menggunakan local pivot.

        Metode asli dipertahankan.
        """

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

        # ----------------------------------------------------
        # Window
        # ----------------------------------------------------

        window = 20

        local_max = []

        local_min = []

        if len(high) <= (
            window * 2
        ):

            return [], []

        # ----------------------------------------------------
        # Local extrema
        # ----------------------------------------------------

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

            # --------------------------------------------
            # Local maximum
            # --------------------------------------------

            if high[i] == np.max(
                high_window
            ):

                local_max.append(
                    float(high[i])
                )

            # --------------------------------------------
            # Local minimum
            # --------------------------------------------

            if low[i] == np.min(
                low_window
            ):

                local_min.append(
                    float(low[i])
                )

        # ----------------------------------------------------
        # Cluster
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Sort
        #
        # Support:
        # lowest → highest
        #
        # Resistance:
        # lowest → highest
        #
        # Ini membuat pemilihan level terdekat
        # lebih mudah untuk Orchestrator.
        # ----------------------------------------------------

        support_levels = sorted(
            support_levels
        )

        resistance_levels = sorted(
            resistance_levels
        )

        # ----------------------------------------------------
        # Top 3
        #
        # Tetap mempertahankan limit asli.
        # ----------------------------------------------------

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

        """
        Cluster values yang berada
        dalam tolerance tertentu.

        Returns:
            average tiap cluster.
        """

        if not values:

            return []

        # ----------------------------------------------------
        # Clean values
        # ----------------------------------------------------

        clean_values = []

        for value in values:

            try:

                value = float(value)

            except (
                ValueError,
                TypeError
            ):

                continue

            if not np.isfinite(
                value
            ):

                continue

            if value <= 0:

                continue

            clean_values.append(
                value
            )

        if not clean_values:

            return []

        # ----------------------------------------------------
        # Sort
        # ----------------------------------------------------

        values = sorted(
            clean_values
        )

        clusters = []

        current_cluster = [
            values[0]
        ]

        # ----------------------------------------------------
        # Build clusters
        # ----------------------------------------------------

        for val in values[1:]:

            cluster_avg = (
                sum(current_cluster)
                / len(current_cluster)
            )

            if cluster_avg <= 0:

                current_cluster = [
                    val
                ]

                continue

            difference = (
                abs(
                    val
                    - cluster_avg
                )
                / cluster_avg
            )

            if difference <= tolerance:

                current_cluster.append(
                    val
                )

            else:

                clusters.append(
                    sum(
                        current_cluster
                    )
                    /
                    len(
                        current_cluster
                    )
                )

                current_cluster = [
                    val
                ]

        # ----------------------------------------------------
        # Last cluster
        # ----------------------------------------------------

        if current_cluster:

            clusters.append(
                sum(current_cluster)
                /
                len(current_cluster)
            )

        return [
            float(value)
            for value in clusters
        ]

    # ========================================================
    # CURRENT POSITION
    # ========================================================

    def _determine_position(
        self,
        price: float,
        support: List[float],
        resistance: List[float]
    ) -> str:

        """
        Determine posisi harga relatif
        terhadap support / resistance.
        """

        if price <= 0:

            return "MIDDLE"

        if (
            not support
            and not resistance
        ):

            return "MIDDLE"

        # ----------------------------------------------------
        # Nearest support
        # ----------------------------------------------------

        nearest_support = None

        if support:

            nearest_support = min(
                support,
                key=lambda x:
                    abs(x - price)
            )

        # ----------------------------------------------------
        # Nearest resistance
        # ----------------------------------------------------

        nearest_resistance = None

        if resistance:

            nearest_resistance = min(
                resistance,
                key=lambda x:
                    abs(x - price)
            )

        # ----------------------------------------------------
        # Differences
        # ----------------------------------------------------

        support_diff = float("inf")

        resistance_diff = float("inf")

        if nearest_support is not None:

            support_diff = (
                abs(
                    price
                    - nearest_support
                )
                / price
            )

        if nearest_resistance is not None:

            resistance_diff = (
                abs(
                    price
                    - nearest_resistance
                )
                / price
            )

        tolerance = self.thresholds[
            "support_resistance_tolerance"
        ]

        # ----------------------------------------------------
        # If both are near
        #
        # Choose the closest one.
        # ----------------------------------------------------

        support_near = (
            support_diff
            <= tolerance
        )

        resistance_near = (
            resistance_diff
            <= tolerance
        )

        if (
            support_near
            and resistance_near
        ):

            if (
                support_diff
                <= resistance_diff
            ):

                return "NEAR_SUPPORT"

            return "NEAR_RESISTANCE"

        if support_near:

            return "NEAR_SUPPORT"

        if resistance_near:

            return "NEAR_RESISTANCE"

        return "MIDDLE"

    # ========================================================
    # INDICATORS
    # ========================================================

    def _calculate_indicators(
        self,
        df: pd.DataFrame
    ) -> Dict[str, Any]:

        """
        Calculate technical indicators.
        """

        close = (
            df["Close"]
            .astype(float)
            .values
        )

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

        # ----------------------------------------------------
        # Current price
        # ----------------------------------------------------

        current_price = float(
            close[-1]
        )

        # ====================================================
        # RSI
        # ====================================================

        rsi_values = talib.RSI(
            close,
            timeperiod=14
        )

        current_rsi = (
            self._safe_indicator_value(
                rsi_values[-1]
                if len(rsi_values) > 0
                else 50.0,
                default=50.0
            )
        )

        # ====================================================
        # MACD
        # ====================================================

        (
            macd,
            macd_signal,
            macd_hist
        ) = talib.MACD(
            close
        )

        current_macd = {

            "macd":
                self._safe_indicator_value(
                    macd[-1]
                    if len(macd) > 0
                    else 0.0,
                    default=0.0
                ),

            "signal":
                self._safe_indicator_value(
                    macd_signal[-1]
                    if len(macd_signal) > 0
                    else 0.0,
                    default=0.0
                ),

            "histogram":
                self._safe_indicator_value(
                    macd_hist[-1]
                    if len(macd_hist) > 0
                    else 0.0,
                    default=0.0
                ),
        }

        # ====================================================
        # Bollinger Bands
        # ====================================================

        (
            upper,
            middle,
            lower
        ) = talib.BBANDS(
            close,
            timeperiod=20,
            nbdevup=2,
            nbdevdn=2
        )

        upper_value = (
            self._safe_indicator_value(
                upper[-1]
                if len(upper) > 0
                else current_price * 1.10,
                default=current_price * 1.10
            )
        )

        middle_value = (
            self._safe_indicator_value(
                middle[-1]
                if len(middle) > 0
                else current_price,
                default=current_price
            )
        )

        lower_value = (
            self._safe_indicator_value(
                lower[-1]
                if len(lower) > 0
                else current_price * 0.90,
                default=current_price * 0.90
            )
        )

        bb_position = (
            self._get_bb_position(
                current_price,
                upper_value,
                lower_value
            )
        )

        current_bands = {

            "upper":
                upper_value,

            "middle":
                middle_value,

            "lower":
                lower_value,

            "position":
                bb_position,
        }

        # ====================================================
        # Moving Averages
        # ====================================================

        ma_10 = self._safe_sma(
            close,
            10,
            current_price
        )

        ma_20 = self._safe_sma(
            close,
            20,
            current_price
        )

        ma_50 = self._safe_sma(
            close,
            50,
            current_price
        )

        ma_200 = self._safe_sma(
            close,
            200,
            current_price
        )

        ma_trend = (
            self._get_ma_trend(
                current_price,
                [
                    ma_10,
                    ma_20,
                    ma_50
                ]
            )
        )

        # ====================================================
        # Trend Strength
        # ====================================================

        trend_strength = (
            self._calculate_trend_strength(
                high,
                low,
                close
            )
        )

        # ====================================================
        # Composite Score
        # ====================================================

        composite_score = (
            self._score_indicators(
                {
                    "rsi":
                        current_rsi,

                    "macd":
                        current_macd,

                    "bb_position":
                        bb_position,

                    "ma_trend":
                        ma_trend,
                }
            )
        )

        # ====================================================
        # Return
        # ====================================================

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
                    ma_200,
            },

            "trend_strength":
                trend_strength,

            "composite_score":
                composite_score,
        }

    # ========================================================
    # SAFE INDICATOR
    # ========================================================

    def _safe_indicator_value(
        self,
        value: Any,
        default: float = 0.0
    ) -> float:

        """
        Pastikan nilai indikator:
        - numeric
        - finite
        """

        try:

            value = float(
                value
            )

        except (
            ValueError,
            TypeError
        ):

            return float(
                default
            )

        if not np.isfinite(
            value
        ):

            return float(
                default
            )

        return value

    # ========================================================
    # SAFE SMA
    # ========================================================

    def _safe_sma(
        self,
        close: np.ndarray,
        period: int,
        fallback: float
    ) -> float:

        """
        SMA dengan fallback aman.
        """

        try:

            if len(close) < period:

                return float(
                    fallback
                )

            values = talib.SMA(
                close,
                timeperiod=period
            )

            if (
                values is None
                or len(values) == 0
            ):

                return float(
                    fallback
                )

            return self._safe_indicator_value(
                values[-1],
                fallback
            )

        except Exception:

            return float(
                fallback
            )

    # ========================================================
    # BOLLINGER POSITION
    # ========================================================

    def _get_bb_position(
        self,
        price: float,
        upper: float,
        lower: float
    ) -> str:

        """
        Determine posisi harga
        terhadap Bollinger Bands.
        """

        if upper <= lower:

            return "MIDDLE"

        if price >= (
            upper * 0.98
        ):

            return "NEAR_UPPER"

        elif price <= (
            lower * 1.02
        ):

            return "NEAR_LOWER"

        return "MIDDLE"

    # ========================================================
    # MOVING AVERAGE TREND
    # ========================================================

    def _get_ma_trend(
        self,
        price: float,
        ma_values: List[float]
    ) -> str:

        """
        Determine trend berdasarkan
        posisi harga terhadap MA.
        """

        valid_values = []

        for ma in ma_values:

            try:

                ma = float(ma)

            except (
                ValueError,
                TypeError
            ):

                continue

            if np.isfinite(ma):

                valid_values.append(
                    ma
                )

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
    # INDICATOR SCORE
    # ========================================================

    def _score_indicators(
        self,
        indicators: Dict
    ) -> float:

        """
        Score indikator untuk composite score.
        """

        score = 0.0

        # ----------------------------------------------------
        # RSI
        # ----------------------------------------------------

        rsi = self._safe_indicator_value(
            indicators.get(
                "rsi",
                50
            ),
            default=50
        )

        if rsi < 30:

            score += 0.5

        elif rsi > 70:

            score -= 0.5

        else:

            score += (
                50 - rsi
            ) / 100

        # ----------------------------------------------------
        # MACD
        # ----------------------------------------------------

        macd = indicators.get(
            "macd",
            {}
        )

        histogram = self._safe_indicator_value(
            macd.get(
                "histogram",
                0
            ),
            default=0
        )

        if histogram > 0:

            score += 0.3

        elif histogram < 0:

            score -= 0.3

        # ----------------------------------------------------
        # Bollinger Bands
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
        # MA trend
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
    # TREND STRENGTH / ADX
    # ========================================================

    def _calculate_trend_strength(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray
    ) -> float:

        """
        Calculate trend strength menggunakan ADX.

        IMPORTANT:
        ADX membutuhkan:
            High
            Low
            Close

        Bukan Close, Close, Close.
        """

        try:

            if len(close) < 30:

                return 0.0

            adx = talib.ADX(
                high,
                low,
                close,
                timeperiod=14
            )

            if (
                adx is None
                or len(adx) == 0
            ):

                return 0.0

            current_adx = (
                self._safe_indicator_value(
                    adx[-1],
                    default=0.0
                )
            )

            return float(
                np.clip(
                    current_adx / 100.0,
                    0.0,
                    1.0
                )
            )

        except Exception as e:

            logger.debug(
                f"ADX calculation error: {e}"
            )

            return 0.0

    # ========================================================
    # VOLUME
    # ========================================================

    def _analyze_volume(
        self,
        df: pd.DataFrame
    ) -> Tuple[float, str]:

        """
        Analyze volume patterns.

        Returns:
            volume_score,
            volume_trend
        """

        try:

            volume = (
                df["Volume"]
                .astype(float)
                .values
            )

            if len(volume) < 20:

                return (
                    0.0,
                    "STABLE"
                )

            # ------------------------------------------------
            # Average excluding current candle
            # ------------------------------------------------

            avg_volume = float(
                np.mean(
                    volume[-20:-1]
                )
            )

            current_volume = float(
                volume[-1]
            )

            if avg_volume <= 0:

                return (
                    0.0,
                    "STABLE"
                )

            # ------------------------------------------------
            # Volume trend
            # ------------------------------------------------

            volume_trend = "STABLE"

            if (
                current_volume
                >
                avg_volume
                *
                self.thresholds[
                    "volume_threshold"
                ]
            ):

                volume_trend = (
                    "INCREASING"
                )

            elif (
                current_volume
                <
                avg_volume * 0.5
            ):

                volume_trend = (
                    "DECREASING"
                )

            # ------------------------------------------------
            # Price change
            # ------------------------------------------------

            previous_close = float(
                df["Close"].iloc[-2]
            )

            current_close = float(
                df["Close"].iloc[-1]
            )

            if previous_close <= 0:

                return (
                    0.0,
                    volume_trend
                )

            price_change = (
                current_close
                - previous_close
            ) / previous_close

            # ------------------------------------------------
            # Volume score
            # ------------------------------------------------

            if (
                volume_trend
                == "INCREASING"
            ):

                if price_change > 0:

                    volume_score = 0.5

                elif price_change < 0:

                    volume_score = -0.5

                else:

                    volume_score = 0.0

            else:

                volume_score = 0.0

            return (
                float(
                    np.clip(
                        volume_score,
                        -1.0,
                        1.0
                    )
                ),
                volume_trend
            )

        except Exception as e:

            logger.error(
                f"Error analyzing volume: {e}"
            )

            return (
                0.0,
                "STABLE"
            )

    # ========================================================
    # SUPPLY / DEMAND
    # ========================================================

    def _calculate_supply_demand(
        self,
        df: pd.DataFrame
    ) -> Tuple[float, float]:

        """
        Calculate supply dan demand score.
        """

        try:

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

                return (
                    0.5,
                    0.5
                )

            # ------------------------------------------------
            # Price range
            # ------------------------------------------------

            min_price = float(
                np.min(low)
            )

            max_price = float(
                np.max(high)
            )

            if (
                not np.isfinite(
                    min_price
                )
                or
                not np.isfinite(
                    max_price
                )
                or
                max_price <= min_price
            ):

                return (
                    0.5,
                    0.5
                )

            # ------------------------------------------------
            # Price bins
            # ------------------------------------------------

            price_bins = np.linspace(
                min_price,
                max_price,
                20
            )

            volume_profile = []

            # ------------------------------------------------
            # Volume by price region
            # ------------------------------------------------

            for i in range(
                len(price_bins) - 1
            ):

                mask = (
                    (close >= price_bins[i])
                    &
                    (
                        close
                        <
                        price_bins[i + 1]
                    )
                )

                if not np.any(mask):

                    continue

                level_volume = float(
                    volume[mask].sum()
                )

                volume_profile.append(
                    {
                        "price_level":
                            (
                                price_bins[i]
                                +
                                price_bins[i + 1]
                            )
                            / 2,

                        "volume":
                            level_volume,
                    }
                )

            if not volume_profile:

                return (
                    0.5,
                    0.5
                )

            # ------------------------------------------------
            # Normalize volume
            # ------------------------------------------------

            volumes = [
                item["volume"]
                for item
                in volume_profile
            ]

            max_volume = max(
                volumes
            )

            if max_volume <= 0:

                return (
                    0.5,
                    0.5
                )

            for item in volume_profile:

                item[
                    "volume_ratio"
                ] = (
                    item["volume"]
                    / max_volume
                )

            # ------------------------------------------------
            # Demand / supply nodes
            # ------------------------------------------------

            current_close = float(
                close[-1]
            )

            demand_nodes = [

                item
                for item
                in volume_profile

                if (
                    item["volume_ratio"]
                    > 0.5
                    and
                    item["price_level"]
                    < current_close
                )

            ]

            supply_nodes = [

                item
                for item
                in volume_profile

                if (
                    item["volume_ratio"]
                    > 0.5
                    and
                    item["price_level"]
                    > current_close
                )

            ]

            # ------------------------------------------------
            # Scores
            # ------------------------------------------------

            demand_score = min(
                len(demand_nodes)
                / 5.0,
                1.0
            )

            supply_score = min(
                len(supply_nodes)
                / 5.0,
                1.0
            )

            return (
                float(
                    np.clip(
                        demand_score,
                        0.0,
                        1.0
                    )
                ),

                float(
                    np.clip(
                        supply_score,
                        0.0,
                        1.0
                    )
                )
            )

        except Exception as e:

            logger.error(
                f"Error calculating "
                f"supply/demand: {e}"
            )

            return (
                0.5,
                0.5
            )

    # ========================================================
    # OVERALL SCORE
    # ========================================================

    def _calculate_overall_score(
        self,
        components: Dict[str, float]
    ) -> float:

        """
        Calculate weighted overall score.
        """

        total_score = 0.0

        total_weight = 0.0

        for (
            component,
            score
        ) in components.items():

            weight = self.weights.get(
                component,
                0.1
            )

            try:

                score = float(
                    score
                )

            except (
                ValueError,
                TypeError
            ):

                score = 0.0

            score = float(
                np.clip(
                    score,
                    -1.0,
                    1.0
                )
            )

            total_score += (
                score * weight
            )

            total_weight += weight

        if total_weight <= 0:

            return 0.0

        return float(
            np.clip(
                total_score
                / total_weight,
                -1.0,
                1.0
            )
        )

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

        """
        Generate summary dari
        analisis teknikal.
        """

        symbol_name = (
            symbol
            .replace("-USD", "")
            .replace("-USDT", "")
        )

        # ----------------------------------------------------
        # Signal
        # ----------------------------------------------------

        if score > 0.3:

            signal = "bullish"

            action = (
                "mempertimbangkan "
                "posisi BUY"
            )

        elif score < -0.3:

            signal = "bearish"

            action = (
                "mempertimbangkan "
                "posisi SELL"
            )

        else:

            signal = "netral"

            action = (
                "wait and see"
            )

        summary = (
            f"Analisis teknikal "
            f"{symbol_name} menunjukkan "
            f"sinyal {signal} "
            f"(score: {score:.2f}). "
        )

        # ----------------------------------------------------
        # RSI
        # ----------------------------------------------------

        rsi = indicators.get(
            "rsi",
            50
        )

        if rsi > 70:

            summary += (
                f"RSI di {rsi:.1f} "
                f"menunjukkan kondisi "
                f"overbought. "
            )

        elif rsi < 30:

            summary += (
                f"RSI di {rsi:.1f} "
                f"menunjukkan kondisi "
                f"oversold. "
            )

        # ----------------------------------------------------
        # Pattern
        # ----------------------------------------------------

        if patterns:

            top_pattern = patterns[0]

            summary += (
                f"Terdeteksi pola "
                f"{top_pattern['name']} "
                f"dengan sinyal "
                f"{top_pattern['signal']}. "
            )

        # ----------------------------------------------------
        # Recommendation
        # ----------------------------------------------------

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

        """
        Generate recommendations
        berdasarkan analisis.
        """

        recommendations = []

        # ----------------------------------------------------
        # Overall score
        # ----------------------------------------------------

        if score > 0.5:

            recommendations.append(
                "STRONG BUY - "
                "Semua indikator bullish"
            )

        elif score > 0.2:

            recommendations.append(
                "BUY - "
                "Indikator cenderung bullish"
            )

        elif score < -0.5:

            recommendations.append(
                "STRONG SELL - "
                "Semua indikator bearish"
            )

        elif score < -0.2:

            recommendations.append(
                "SELL - "
                "Indikator cenderung bearish"
            )

        else:

            recommendations.append(
                "HOLD - "
                "Tidak ada sinyal jelas"
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
                "RSI sangat oversold - "
                "Potensi rebound"
            )

        elif rsi > 75:

            recommendations.append(
                "RSI sangat overbought - "
                "Waspada koreksi"
            )

        # ----------------------------------------------------
        # Position
        # ----------------------------------------------------

        if position == "NEAR_SUPPORT":

            recommendations.append(
                "Dekat level support - "
                "Potensi bounce"
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
                top_pattern["signal"]
                == "BULLISH"
                and
                top_pattern["confidence"]
                > 0.7
            ):

                recommendations.append(
                    "Konfirmasi bullish "
                    f"dari pola "
                    f"{top_pattern['name']}"
                )

            elif (
                top_pattern["signal"]
                == "BEARISH"
                and
                top_pattern["confidence"]
                > 0.7
            ):

                recommendations.append(
                    "Konfirmasi bearish "
                    f"dari pola "
                    f"{top_pattern['name']}"
                )

        # ----------------------------------------------------
        # Maximum 3
        # ----------------------------------------------------

        return recommendations[:3]

    # ========================================================
    # DEFAULT RESULT
    # ========================================================

    def _get_default_result(
        self,
        symbol: str
    ) -> TechnicalResult:

        """
        Default result jika analisis gagal.
        """

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
                "histogram": 0.0,
            },

            bollinger_bands={
                "upper": 0.0,
                "middle": 0.0,
                "lower": 0.0,
                "position": "MIDDLE",
            },

            moving_averages={
                "MA10": 0.0,
                "MA20": 0.0,
                "MA50": 0.0,
                "MA200": 0.0,
            },

            volume_score=0.0,

            volume_trend="STABLE",

            demand_score=0.5,

            supply_score=0.5,

            overall_score=0.0,

            summary=(
                f"Unable to analyze "
                f"technicals for {symbol}. "
                f"Default to neutral."
            ),

            recommendations=[
                "HOLD - Insufficient data"
            ],
        )


# ============================================================
# DIRECT TEST
# ============================================================

if __name__ == "__main__":

    agent = TechnicalAgent()

    result = agent.analyze(
        "BTC-USD"
    )

    print("=" * 60)

    print(
        f"Technical Analysis Result "
        f"for {result.symbol}"
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

    print(
        "\nSupport Levels:"
    )

    if result.support_levels:

        for level in result.support_levels:

            print(
                f"  ${level:.2f}"
            )

    else:

        print(
            "  None"
        )

    print(
        "\nResistance Levels:"
    )

    if result.resistance_levels:

        for level in result.resistance_levels:

            print(
                f"  ${level:.2f}"
            )

    else:

        print(
            "  None"
        )

    print(
        "\nDetected Patterns:"
    )

    if result.detected_patterns:

        for pattern in (
            result.detected_patterns
        ):

            print(
                f"  - "
                f"{pattern['name']}: "
                f"{pattern['signal']} "
                f"(confidence: "
                f"{pattern['confidence']:.2%})"
            )

    else:

        print(
            "  No pattern detected"
        )

    print(
        "\nSummary:"
    )

    print(
        result.summary
    )

    print(
        "\nRecommendations:"
    )

    for rec in (
        result.recommendations
    ):

        print(
            f"  • {rec}"
        )
