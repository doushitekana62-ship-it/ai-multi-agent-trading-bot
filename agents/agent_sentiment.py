"""
Agent 1: Analisis Sentimen Pasar

Bertugas menganalisis sentimen dari:
- berita
- media sosial
- momentum harga
- Fear & Greed
- volume

untuk menentukan apakah pasar:
- bullish
- bearish
- neutral

CATATAN:
Agent ini TIDAK melakukan trading execution.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List
from dataclasses import dataclass

import yfinance as yf
from textblob import TextBlob
import numpy as np


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


# ============================================================
# RESULT
# ============================================================

@dataclass
class SentimentResult:
    """
    Data class untuk hasil analisis sentimen.
    """

    symbol: str

    timestamp: datetime

    # Overall sentiment
    # -1 = sangat bearish
    #  0 = neutral
    # +1 = sangat bullish
    overall_score: float

    # BULLISH / BEARISH / NEUTRAL
    sentiment_label: str

    # 0 - 1
    confidence: float

    # Individual sources
    news_sentiment: float

    social_sentiment: float

    price_momentum: float

    fear_greed_index: float

    # Contribution masing-masing source
    source_contributions: Dict[str, float]

    # Event penting
    key_events: List[str]

    # Summary
    summary: str


# ============================================================
# SENTIMENT AGENT
# ============================================================

class SentimentAgent:

    """
    Agent Sentimen Pasar dengan kemampuan
    multi-source analysis.
    """

    def __init__(
        self,
        config: Dict = None
    ):

        self.config = config or {}

        # ----------------------------------------------------
        # API Keys
        # ----------------------------------------------------

        self.news_api_key = os.getenv(
            "NEWS_API_KEY",
            ""
        )

        self.twitter_api_key = os.getenv(
            "TWITTER_API_KEY",
            ""
        )

        self.reddit_client_id = os.getenv(
            "REDDIT_CLIENT_ID",
            ""
        )

        self.reddit_client_secret = os.getenv(
            "REDDIT_CLIENT_SECRET",
            ""
        )

        # ----------------------------------------------------
        # Weights
        #
        # Total = 1.00
        # ----------------------------------------------------

        self.weights = {

            "news": 0.30,

            "social": 0.20,

            "price_momentum": 0.25,

            "fear_greed": 0.15,

            "volume": 0.10,

        }

        # ----------------------------------------------------
        # Cache
        # ----------------------------------------------------

        self.cache = {}

        self.cache_duration = timedelta(
            minutes=5
        )

        # ----------------------------------------------------
        # Positive keywords
        # ----------------------------------------------------

        self.positive_keywords = [

            "bullish",
            "rally",
            "surge",
            "gain",
            "profit",
            "positive",
            "growth",
            "breakthrough",
            "success",
            "adoption",
            "innovation",
            "upgrade",
            "upbeat",
            "optimistic",
            "outperform",
            "beat",

        ]

        # ----------------------------------------------------
        # Negative keywords
        # ----------------------------------------------------

        self.negative_keywords = [

            "bearish",
            "crash",
            "drop",
            "loss",
            "negative",
            "decline",
            "regulatory",
            "ban",
            "restriction",
            "delay",
            "failure",
            "bear",
            "slump",
            "plunge",
            "concern",
            "risk",
            "warning",

        ]

        logger.info(
            "Sentiment Agent initialized successfully"
        )

    # ========================================================
    # PUBLIC ANALYZE
    # ========================================================

    def analyze(
        self,
        symbol: str,
        market_data: Dict = None
    ) -> SentimentResult:

        """
        Main method untuk melakukan analisis sentimen.

        Args:
            symbol:
                Simbol aset, contoh:
                BTC-USD

            market_data:
                Data pasar opsional.

        Returns:
            SentimentResult
        """

        logger.info(
            f"Analyzing sentiment for {symbol}"
        )

        market_data = market_data or {}

        # ----------------------------------------------------
        # Cache
        # ----------------------------------------------------

        cache_key = f"sentiment_{symbol}"

        if cache_key in self.cache:

            cached_result, cache_time = (
                self.cache[cache_key]
            )

            if (
                datetime.now() - cache_time
                < self.cache_duration
            ):

                logger.info(
                    f"Using cached sentiment for {symbol}"
                )

                return cached_result

        try:

            # ------------------------------------------------
            # 1. News
            # ------------------------------------------------

            news_sentiment = (
                self._analyze_news(symbol)
            )

            # ------------------------------------------------
            # 2. Social media
            # ------------------------------------------------

            social_sentiment = (
                self._analyze_social_media(symbol)
            )

            # ------------------------------------------------
            # 3. Price momentum
            # ------------------------------------------------

            price_momentum = (
                self._analyze_price_momentum(
                    symbol,
                    market_data
                )
            )

            # ------------------------------------------------
            # 4. Fear & Greed
            # ------------------------------------------------

            fear_greed = (
                self._get_fear_greed_index()
            )

            # ------------------------------------------------
            # 5. Volume
            # ------------------------------------------------

            volume_sentiment = (
                self._analyze_volume(
                    symbol,
                    market_data
                )
            )

            # ------------------------------------------------
            # Combine sources
            # ------------------------------------------------

            sentiment_sources = {

                "news": news_sentiment,

                "social": social_sentiment,

                "price_momentum": price_momentum,

                "fear_greed": fear_greed,

                "volume": volume_sentiment,

            }

            overall_score = (
                self._combine_sentiments(
                    sentiment_sources
                )
            )

            # ------------------------------------------------
            # Label
            # ------------------------------------------------

            sentiment_label = (
                self._get_sentiment_label(
                    overall_score
                )
            )

            # ------------------------------------------------
            # Confidence
            # ------------------------------------------------

            confidence = (
                self._calculate_confidence(
                    sentiment_sources
                )
            )

            # ------------------------------------------------
            # Key events
            #
            # Tidak menggunakan random event.
            # ------------------------------------------------

            key_events = (
                self._extract_key_events(
                    symbol
                )
            )

            # ------------------------------------------------
            # Summary
            # ------------------------------------------------

            summary = (
                self._generate_summary(
                    symbol,
                    overall_score,
                    sentiment_label,
                    key_events
                )
            )

            # ------------------------------------------------
            # Source contributions
            # ------------------------------------------------

            source_contributions = {

                "news":
                    news_sentiment
                    * self.weights["news"],

                "social":
                    social_sentiment
                    * self.weights["social"],

                "price_momentum":
                    price_momentum
                    * self.weights["price_momentum"],

                "fear_greed":
                    fear_greed
                    * self.weights["fear_greed"],

                "volume":
                    volume_sentiment
                    * self.weights["volume"],

            }

            # ------------------------------------------------
            # Result
            # ------------------------------------------------

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

                source_contributions=(
                    source_contributions
                ),

                key_events=key_events,

                summary=summary,

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
                f"Error analyzing sentiment "
                f"for {symbol}: {e}"
            )

            return self._get_default_sentiment(
                symbol
            )

    # ========================================================
    # NEWS
    # ========================================================

    def _analyze_news(
        self,
        symbol: str
    ) -> float:

        """
        Analisis sentimen dari berita.

        Returns:
            -1 sampai +1
        """

        try:

            headlines = (
                self._fetch_news_headlines(
                    symbol
                )
            )

            if not headlines:

                return 0.0

            sentiments = []

            for headline in headlines[:10]:

                if not headline:

                    continue

                blob = TextBlob(
                    str(headline)
                )

                polarity = (
                    blob.sentiment.polarity
                )

                headline_lower = (
                    str(headline).lower()
                )

                # --------------------------------------------
                # Positive keyword adjustment
                # --------------------------------------------

                if any(
                    word in headline_lower
                    for word in self.positive_keywords
                ):

                    polarity = min(
                        1.0,
                        polarity + 0.3
                    )

                # --------------------------------------------
                # Negative keyword adjustment
                # --------------------------------------------

                elif any(
                    word in headline_lower
                    for word in self.negative_keywords
                ):

                    polarity = max(
                        -1.0,
                        polarity - 0.3
                    )

                sentiments.append(
                    np.clip(
                        polarity,
                        -1.0,
                        1.0
                    )
                )

            if not sentiments:

                return 0.0

            avg_sentiment = np.mean(
                sentiments
            )

            return float(
                np.clip(
                    avg_sentiment,
                    -1.0,
                    1.0
                )
            )

        except Exception as e:

            logger.error(
                f"Error analyzing news "
                f"for {symbol}: {e}"
            )

            return 0.0

    # ========================================================
    # SOCIAL MEDIA
    # ========================================================

    def _analyze_social_media(
        self,
        symbol: str
    ) -> float:

        """
        Analisis sentimen media sosial.

        Returns:
            -1 sampai +1
        """

        try:

            social_posts = (
                self._fetch_social_posts(
                    symbol
                )
            )

            if not social_posts:

                return 0.0

            sentiments = []

            for post in social_posts[:20]:

                if not post:

                    continue

                blob = TextBlob(
                    str(post)
                )

                polarity = (
                    blob.sentiment.polarity
                )

                post_lower = (
                    str(post).lower()
                )

                # --------------------------------------------
                # Crypto-specific expressions
                # --------------------------------------------

                if (
                    "moon" in post_lower
                    or "to the moon" in post_lower
                ):

                    polarity += 0.5

                elif (
                    "dump" in post_lower
                    or "dead" in post_lower
                ):

                    polarity -= 0.5

                sentiments.append(
                    np.clip(
                        polarity,
                        -1.0,
                        1.0
                    )
                )

            if not sentiments:

                return 0.0

            avg_sentiment = np.mean(
                sentiments
            )

            return float(
                np.clip(
                    avg_sentiment,
                    -1.0,
                    1.0
                )
            )

        except Exception as e:

            logger.error(
                f"Error analyzing social media "
                f"for {symbol}: {e}"
            )

            return 0.0

    # ========================================================
    # PRICE MOMENTUM
    # ========================================================

    def _analyze_price_momentum(
        self,
        symbol: str,
        market_data: Dict = None
    ) -> float:

        """
        Analisis momentum harga.

        Returns:
            -1 sampai +1
        """

        try:

            market_data = (
                market_data or {}
            )

            # ------------------------------------------------
            # Gunakan data dari market_data
            # jika tersedia
            # ------------------------------------------------

            if "prices" in market_data:

                prices = np.asarray(
                    market_data["prices"],
                    dtype=float
                )

            else:

                ticker = yf.Ticker(
                    symbol
                )

                hist = ticker.history(
                    period="5d",
                    interval="1h"
                )

                if hist.empty:

                    return 0.0

                prices = (
                    hist["Close"]
                    .dropna()
                    .values
                )

            if len(prices) < 2:

                return 0.0

            # ------------------------------------------------
            # Short term
            # ------------------------------------------------

            short_term = (
                self._calculate_momentum(
                    prices,
                    window=6
                )
            )

            # ------------------------------------------------
            # Medium term
            # ------------------------------------------------

            medium_term = (
                self._calculate_momentum(
                    prices,
                    window=24
                )
            )

            # ------------------------------------------------
            # Long term
            # ------------------------------------------------

            long_term = (
                self._calculate_momentum(
                    prices,
                    window=72
                )
            )

            # ------------------------------------------------
            # Weighted momentum
            # ------------------------------------------------

            momentum = (

                short_term * 0.50

                +

                medium_term * 0.30

                +

                long_term * 0.20

            )

            momentum_score = float(
                np.clip(
                    momentum,
                    -1.0,
                    1.0
                )
            )

            # ------------------------------------------------
            # RSI adjustment
            # ------------------------------------------------

            rsi = self._calculate_rsi(
                prices
            )

            if rsi > 70:

                momentum_score = min(
                    0.3,
                    momentum_score
                )

            elif rsi < 30:

                momentum_score = max(
                    -0.3,
                    momentum_score
                )

            return float(
                np.clip(
                    momentum_score,
                    -1.0,
                    1.0
                )
            )

        except Exception as e:

            logger.error(
                f"Error analyzing price momentum "
                f"for {symbol}: {e}"
            )

            return 0.0

    # ========================================================
    # FEAR & GREED
    # ========================================================

    def _get_fear_greed_index(
        self
    ) -> float:

        """
        Mendapatkan Fear & Greed Index.

        IMPORTANT:
        Untuk saat ini tidak menggunakan
        nilai random.

        Jika API belum dikonfigurasi,
        return 0.0 (neutral).

        Nanti bisa kita sambungkan ke
        sumber Fear & Greed aktual.
        """

        try:

            # ------------------------------------------------
            # Jika nanti tersedia dari market_data/config,
            # bagian ini dapat dikembangkan.
            #
            # Untuk sekarang:
            # 0.0 = neutral
            # ------------------------------------------------

            configured_value = (
                self.config.get(
                    "fear_greed_index"
                )
            )

            if configured_value is not None:

                try:

                    return float(
                        np.clip(
                            float(
                                configured_value
                            ),
                            -1.0,
                            1.0
                        )
                    )

                except (
                    ValueError,
                    TypeError
                ):

                    pass

            return 0.0

        except Exception as e:

            logger.error(
                f"Error fetching Fear & Greed "
                f"index: {e}"
            )

            return 0.0

    # ========================================================
    # VOLUME
    # ========================================================

    def _analyze_volume(
        self,
        symbol: str,
        market_data: Dict = None
    ) -> float:

        """
        Analisis volume trading.

        Returns:
            -1 sampai +1
        """

        try:

            market_data = (
                market_data or {}
            )

            if "volume" in market_data:

                volume = np.asarray(
                    market_data["volume"],
                    dtype=float
                )

            else:

                ticker = yf.Ticker(
                    symbol
                )

                hist = ticker.history(
                    period="5d"
                )

                if hist.empty:

                    return 0.0

                volume = (
                    hist["Volume"]
                    .dropna()
                    .values
                )

            if len(volume) < 2:

                return 0.0

            # ------------------------------------------------
            # Average previous volume
            # ------------------------------------------------

            avg_volume = np.mean(
                volume[:-1]
            )

            current_volume = (
                volume[-1]
            )

            if avg_volume <= 0:

                return 0.0

            volume_ratio = (
                current_volume
                / avg_volume
            )

            # ------------------------------------------------
            # Volume interpretation
            # ------------------------------------------------

            if volume_ratio > 1.5:

                return 0.5

            elif volume_ratio < 0.5:

                return -0.3

            return 0.0

        except Exception as e:

            logger.error(
                f"Error analyzing volume "
                f"for {symbol}: {e}"
            )

            return 0.0

    # ========================================================
    # COMBINE SENTIMENTS
    # ========================================================

    def _combine_sentiments(
        self,
        sentiments: Dict[str, float]
    ) -> float:

        """
        Menggabungkan seluruh sumber
        berdasarkan weight.

        Returns:
            -1 sampai +1
        """

        total_score = 0.0

        total_weight = 0.0

        for source, score in (
            sentiments.items()
        ):

            weight = self.weights.get(
                source,
                0.0
            )

            if weight <= 0:

                continue

            try:

                score = float(score)

            except (
                ValueError,
                TypeError
            ):

                score = 0.0

            score = np.clip(
                score,
                -1.0,
                1.0
            )

            total_score += (
                score * weight
            )

            total_weight += weight

        if total_weight <= 0:

            return 0.0

        return float(
            np.clip(
                total_score / total_weight,
                -1.0,
                1.0
            )
        )

    # ========================================================
    # SENTIMENT LABEL
    # ========================================================

    def _get_sentiment_label(
        self,
        score: float
    ) -> str:

        """
        Konversi score menjadi label.
        """

        try:

            score = float(score)

        except (
            ValueError,
            TypeError
        ):

            score = 0.0

        if score >= 0.3:

            return "BULLISH"

        elif score <= -0.3:

            return "BEARISH"

        return "NEUTRAL"

    # ========================================================
    # CONFIDENCE
    # ========================================================

    def _calculate_confidence(
        self,
        sentiments: Dict[str, float]
    ) -> float:

        """
        Menghitung confidence berdasarkan
        konsistensi sumber.

        Returns:
            0 sampai 1
        """

        if not sentiments:

            return 0.5

        scores = []

        for value in sentiments.values():

            try:

                scores.append(
                    float(value)
                )

            except (
                ValueError,
                TypeError
            ):

                scores.append(0.0)

        if not scores:

            return 0.5

        # ----------------------------------------------------
        # Konsistensi
        # ----------------------------------------------------

        std_dev = np.std(
            scores
        )

        avg_score = np.mean(
            scores
        )

        # ----------------------------------------------------
        # Base confidence
        # ----------------------------------------------------

        if std_dev < 0.2:

            confidence = 0.9

        elif std_dev < 0.4:

            confidence = 0.7

        elif std_dev < 0.6:

            confidence = 0.5

        else:

            confidence = 0.3

        # ----------------------------------------------------
        # Adjust berdasarkan strength
        # ----------------------------------------------------

        confidence *= (
            0.5
            +
            abs(avg_score) * 0.5
        )

        return float(
            np.clip(
                confidence,
                0.0,
                1.0
            )
        )

    # ========================================================
    # MOMENTUM CALCULATION
    # ========================================================

    def _calculate_momentum(
        self,
        prices: np.ndarray,
        window: int
    ) -> float:

        """
        Menghitung momentum berdasarkan
        perubahan harga.
        """

        if len(prices) < (
            window + 1
        ):

            return 0.0

        current_price = (
            prices[-1]
        )

        past_price = (
            prices[-window - 1]
        )

        if past_price == 0:

            return 0.0

        change_pct = (
            current_price
            - past_price
        ) / past_price

        # ----------------------------------------------------
        # ±5% = ±1 score
        # ----------------------------------------------------

        momentum = np.clip(
            change_pct * 20,
            -1.0,
            1.0
        )

        return float(
            momentum
        )

    # ========================================================
    # RSI
    # ========================================================

    def _calculate_rsi(
        self,
        prices: np.ndarray,
        period: int = 14
    ) -> float:

        """
        Menghitung RSI sederhana.
        """

        if len(prices) < (
            period + 1
        ):

            return 50.0

        deltas = np.diff(
            prices
        )

        seed = deltas[
            :period
        ]

        up = (
            seed[seed >= 0].sum()
            / period
        )

        down = (
            -seed[seed < 0].sum()
            / period
        )

        if down == 0:

            return 100.0

        rs = (
            up / down
        )

        rsi = (
            100
            -
            (
                100
                /
                (1 + rs)
            )
        )

        return float(
            np.clip(
                rsi,
                0.0,
                100.0
            )
        )

    # ========================================================
    # NEWS FETCH
    # ========================================================

    def _fetch_news_headlines(
        self,
        symbol: str
    ) -> List[str]:

        """
        Mengambil headlines.

        IMPORTANT:
        Saat ini masih menggunakan
        sample headlines karena News API
        belum benar-benar dihubungkan.

        Jangan dianggap sebagai berita aktual.
        """

        symbol_name = (
            symbol
            .replace("-USD", "")
            .replace("-USDT", "")
        )

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

            f"Community sentiment on {symbol_name} remains bullish",

        ]

        return sample_headlines[:10]

    # ========================================================
    # SOCIAL FETCH
    # ========================================================

    def _fetch_social_posts(
        self,
        symbol: str
    ) -> List[str]:

        """
        Mengambil social media posts.

        IMPORTANT:
        Saat ini masih menggunakan
        sample posts.

        Nanti kita bisa hubungkan
        ke API yang sebenarnya.
        """

        symbol_name = (
            symbol
            .replace("-USD", "")
            .replace("-USDT", "")
        )

        sample_posts = [

            f"#Bullish on ${symbol_name}",

            f"Just bought more ${symbol_name}",

            f"Why ${symbol_name} is undervalued",

            f"${symbol_name} to the moon",

            f"Concerned about ${symbol_name} future",

            f"Great project, strong team ${symbol_name}",

            f"${symbol_name} just broke resistance",

            f"Looking bearish on ${symbol_name} short-term",

            f"${symbol_name} adoption continues",

            f"Selling ${symbol_name}, it is overvalued",

        ]

        return sample_posts[:20]

    # ========================================================
    # KEY EVENTS
    # ========================================================

    def _extract_key_events(
        self,
        symbol: str
    ) -> List[str]:

        """
        Extract key events dari data yang benar-benar
        tersedia.

        PENTING:
        Tidak lagi menggunakan random event.

        Karena belum ada news/event source nyata
        yang terhubung, kita mengembalikan list kosong.

        Ini lebih aman daripada membuat event
        fiktif yang berubah-ubah setiap run.
        """

        return []

    # ========================================================
    # SUMMARY
    # ========================================================

    def _generate_summary(
        self,
        symbol: str,
        score: float,
        label: str,
        events: List[str]
    ) -> str:

        """
        Generate ringkasan analisis.
        """

        symbol_name = (
            symbol
            .replace("-USD", "")
            .replace("-USDT", "")
        )

        if label == "BULLISH":

            sentiment_desc = "positif"

            action = (
                "bullish sentiment "
                "dengan potensi kenaikan"
            )

        elif label == "BEARISH":

            sentiment_desc = "negatif"

            action = (
                "bearish sentiment "
                "dengan potensi penurunan"
            )

        else:

            sentiment_desc = "netral"

            action = (
                "netral, perlu konfirmasi "
                "lebih lanjut"
            )

        summary = (

            f"Analisis sentimen untuk "
            f"{symbol_name} menunjukkan "
            f"sentimen {sentiment_desc} "
            f"(score: {score:.2f}). "

            f"Indikator pasar menunjukkan "
            f"{action}. "

        )

        if events:

            summary += (
                "Event penting: "
                f"{', '.join(events[:3])}. "
            )

        return summary

    # ========================================================
    # DEFAULT RESULT
    # ========================================================

    def _get_default_sentiment(
        self,
        symbol: str
    ) -> SentimentResult:

        """
        Default neutral result jika
        terjadi error.
        """

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

            summary=(
                f"Unable to analyze sentiment "
                f"for {symbol}. "
                f"Default to neutral."
            )

        )


# ============================================================
# DIRECT TEST
# ============================================================

if __name__ == "__main__":

    agent = SentimentAgent()

    result = agent.analyze(
        "BTC-USD"
    )

    print("=" * 60)

    print(
        "SENTIMENT ANALYSIS RESULT"
    )

    print("=" * 60)

    print(
        f"Symbol: "
        f"{result.symbol}"
    )

    print(
        f"Overall Score: "
        f"{result.overall_score:.3f}"
    )

    print(
        f"Sentiment: "
        f"{result.sentiment_label}"
    )

    print(
        f"Confidence: "
        f"{result.confidence:.2%}"
    )

    print(
        f"News Sentiment: "
        f"{result.news_sentiment:.3f}"
    )

    print(
        f"Social Sentiment: "
        f"{result.social_sentiment:.3f}"
    )

    print(
        f"Price Momentum: "
        f"{result.price_momentum:.3f}"
    )

    print(
        f"Fear & Greed: "
        f"{result.fear_greed_index:.3f}"
    )

    print(
        "\nSource Contributions:"
    )

    for (
        source,
        contribution
    ) in result.source_contributions.items():

        print(
            f"  {source}: "
            f"{contribution:.3f}"
        )

    print(
        "\nKey Events:"
    )

    if result.key_events:

        for event in result.key_events:

            print(
                f"  - {event}"
            )

    else:

        print(
            "  No verified events available"
        )

    print(
        "\nSummary:"
    )

    print(
        result.summary
    )
