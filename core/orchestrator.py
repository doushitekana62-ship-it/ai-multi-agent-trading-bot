"""
Orchestrator - AI Decision Coordination Layer

Tugas utama:
1. Menjalankan seluruh AI agents.
2. Menghindari pemanggilan agent yang sama secara berulang.
3. Mengumpulkan hasil agent.
4. Menghitung weighted consensus.
5. Menghitung confidence berdasarkan kualitas hasil agent.
6. Menentukan final action.
7. Menghitung preliminary position size.
8. Menghitung preliminary Stop Loss / Take Profit.
9. Menyediakan data yang nantinya digunakan oleh Risk Engine.
10. TIDAK melakukan eksekusi trading.

PENTING:
Orchestrator hanya mengambil keputusan.
Executor akan menangani eksekusi.
Risk Engine akan menangani validasi risiko pada tahap berikutnya.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple


# ============================================================
# AGENTS
# ============================================================

from agents.agent_sentiment import (
    SentimentAgent,
    SentimentResult,
)

from agents.agent_technical import (
    TechnicalAgent,
    TechnicalResult,
)

from agents.agent_decision import (
    DecisionAgent,
    DecisionResult,
)

from agents.agent_reflector import (
    ReflectorAgent,
    ReflectionResult,
    TradeRecord,
)

from agents.agent_forecast import (
    ForecastAgent,
    ForecastResult,
)


# ============================================================
# LOGGING
# ============================================================

logger = logging.getLogger(__name__)


# ============================================================
# RESULT DATACLASS
# ============================================================

@dataclass
class OrchestratorResult:
    """
    Hasil lengkap dari proses analisis Orchestrator.
    """

    timestamp: datetime

    symbol: str

    current_price: float

    # --------------------------------------------------------
    # Agent results
    # --------------------------------------------------------

    sentiment: Optional[SentimentResult]

    technical: Optional[TechnicalResult]

    decision: Optional[DecisionResult]

    reflection: Optional[ReflectionResult]

    forecast: Optional[ForecastResult]

    # --------------------------------------------------------
    # Consensus
    # --------------------------------------------------------

    consensus_action: str

    consensus_score: float

    agent_votes: Dict[str, str]

    # --------------------------------------------------------
    # Final decision
    # --------------------------------------------------------

    final_action: str

    final_confidence: float

    position_size: float

    stop_loss: Optional[float]

    take_profit: Optional[float]

    # --------------------------------------------------------
    # Decision metadata
    # --------------------------------------------------------

    decision_score: float

    confidence_components: Dict[str, float]

    market_scores: Dict[str, float]

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    summary: str


# ============================================================
# ORCHESTRATOR
# ============================================================

class Orchestrator:

    """
    Central coordinator untuk seluruh AI agents.

    Flow:

        Market Data
             ↓
        Agent Analysis
             ↓
        Weighted Consensus
             ↓
        Final Decision
             ↓
        Preliminary Position Size
             ↓
        Preliminary SL / TP

    Orchestrator TIDAK melakukan order execution.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):

        self.config = config or {}

        # ----------------------------------------------------
        # Initialize agents
        # ----------------------------------------------------

        self.sentiment_agent = SentimentAgent()

        self.technical_agent = TechnicalAgent()

        self.decision_agent = DecisionAgent()

        self.reflector_agent = ReflectorAgent()

        self.forecast_agent = ForecastAgent()

        # ----------------------------------------------------
        # Score thresholds
        # ----------------------------------------------------

        self.voting_thresholds = {
            "strong_buy": 0.70,
            "buy": 0.30,
            "hold": 0.30,
            "sell": -0.30,
            "strong_sell": -0.70,
        }

        # ----------------------------------------------------
        # Agent weights
        #
        # Total = 1.0
        # ----------------------------------------------------

        self.agent_weights = {
            "sentiment": 0.25,
            "technical": 0.30,
            "decision": 0.30,
            "forecast": 0.15,
        }

        # ----------------------------------------------------
        # Position size configuration
        # ----------------------------------------------------

        self.max_position_size = self.config.get(
            "max_position_size",
            0.20
        )

        self.default_position_size = self.config.get(
            "default_position_size",
            0.05
        )

        # ----------------------------------------------------
        # History
        # ----------------------------------------------------

        self.history: List[OrchestratorResult] = []

        self.max_history = self.config.get(
            "max_history",
            100
        )

        logger.info(
            "Orchestrator initialized successfully"
        )

    # ========================================================
    # PUBLIC ANALYZE
    # ========================================================

    async def analyze(
        self,
        symbol: str,
        market_data: Optional[Dict[str, Any]] = None
    ) -> OrchestratorResult:

        """
        Menjalankan seluruh proses analisis.

        Tidak melakukan trading execution.
        """

        logger.info(
            f"Starting analysis for {symbol}"
        )

        market_data = market_data or {}

        try:

            # ------------------------------------------------
            # STEP 1
            # Jalankan base agents sekali saja
            # ------------------------------------------------

            sentiment_result, technical_result = (
                await self._run_base_agents(
                    symbol,
                    market_data
                )
            )

            # ------------------------------------------------
            # STEP 2
            # Decision agent
            # Menggunakan hasil sentiment + technical
            # ------------------------------------------------

            decision_result = await self._run_decision(
                symbol,
                sentiment_result,
                technical_result,
                market_data
            )

            # ------------------------------------------------
            # STEP 3
            # Forecast agent
            # Menggunakan hasil sentiment + technical
            # ------------------------------------------------

            forecast_result = await self._run_forecast(
                symbol,
                sentiment_result,
                technical_result,
                market_data
            )

            # ------------------------------------------------
            # STEP 4
            # Reflection agent
            # ------------------------------------------------

            reflection_result = await self._run_reflection(
                symbol,
                market_data
            )

            # ------------------------------------------------
            # STEP 5
            # Current price
            # ------------------------------------------------

            current_price = self._get_current_price(
                market_data,
                technical_result
            )

            # ------------------------------------------------
            # STEP 6
            # Consensus
            # ------------------------------------------------

            consensus_action, consensus_score = (
                self._perform_voting(
                    sentiment=sentiment_result,
                    technical=technical_result,
                    decision=decision_result,
                    forecast=forecast_result
                )
            )

            # ------------------------------------------------
            # STEP 7
            # Agent votes
            # ------------------------------------------------

            agent_votes = self._get_agent_votes(
                sentiment=sentiment_result,
                technical=technical_result,
                decision=decision_result,
                forecast=forecast_result
            )

            # ------------------------------------------------
            # STEP 8
            # Final decision
            # ------------------------------------------------

            (
                final_action,
                final_confidence,
                decision_score,
                confidence_components
            ) = self._determine_final_decision(
                decision=decision_result,
                consensus_action=consensus_action,
                consensus_score=consensus_score,
                sentiment=sentiment_result,
                technical=technical_result,
                forecast=forecast_result
            )

            # ------------------------------------------------
            # STEP 9
            # Preliminary position size
            # ------------------------------------------------

            position_size = self._calculate_position_size(
                confidence=final_confidence,
                decision=decision_result,
                action=final_action
            )

            # ------------------------------------------------
            # STEP 10
            # Preliminary SL / TP
            # ------------------------------------------------

            stop_loss, take_profit = (
                self._calculate_sl_tp(
                    technical=technical_result,
                    action=final_action,
                    current_price=current_price
                )
            )

            # ------------------------------------------------
            # STEP 11
            # Market scores
            # ------------------------------------------------

            market_scores = self._build_market_scores(
                sentiment=sentiment_result,
                technical=technical_result,
                decision=decision_result,
                forecast=forecast_result,
                consensus_score=consensus_score
            )

            # ------------------------------------------------
            # STEP 12
            # Summary
            # ------------------------------------------------

            summary = self._generate_summary(
                symbol=symbol,
                current_price=current_price,
                final_action=final_action,
                final_confidence=final_confidence,
                position_size=position_size,
                consensus_action=consensus_action,
                consensus_score=consensus_score,
                agent_votes=agent_votes,
                stop_loss=stop_loss,
                take_profit=take_profit
            )

            # ------------------------------------------------
            # STEP 13
            # Build result
            # ------------------------------------------------

            result = OrchestratorResult(

                timestamp=datetime.now(),

                symbol=symbol,

                current_price=current_price,

                sentiment=sentiment_result,

                technical=technical_result,

                decision=decision_result,

                reflection=reflection_result,

                forecast=forecast_result,

                consensus_action=consensus_action,

                consensus_score=consensus_score,

                agent_votes=agent_votes,

                final_action=final_action,

                final_confidence=final_confidence,

                position_size=position_size,

                stop_loss=stop_loss,

                take_profit=take_profit,

                decision_score=decision_score,

                confidence_components=confidence_components,

                market_scores=market_scores,

                summary=summary
            )

            # ------------------------------------------------
            # STEP 14
            # History
            # ------------------------------------------------

            self.history.append(result)

            if len(self.history) > self.max_history:

                self.history.pop(0)

            logger.info(
                f"Analysis completed: "
                f"{symbol} → "
                f"{final_action} "
                f"(confidence={final_confidence:.2%})"
            )

            return result

        except Exception as e:

            logger.exception(
                f"Orchestrator analysis failed for {symbol}: {e}"
            )

            return self._get_default_result(symbol)

    # ========================================================
    # BASE AGENTS
    # ========================================================

    async def _run_base_agents(
        self,
        symbol: str,
        market_data: Dict[str, Any]
    ) -> Tuple[
        Optional[SentimentResult],
        Optional[TechnicalResult]
    ]:

        """
        Menjalankan sentiment + technical sekali saja.
        """

        tasks = [

            asyncio.to_thread(
                self.sentiment_agent.analyze,
                symbol,
                market_data
            ),

            asyncio.to_thread(
                self.technical_agent.analyze,
                symbol,
                market_data
            )
        ]

        results = await asyncio.gather(
            *tasks,
            return_exceptions=True
        )

        sentiment_result = None
        technical_result = None

        # ----------------------------------------------------
        # Sentiment
        # ----------------------------------------------------

        if not isinstance(
            results[0],
            Exception
        ):

            sentiment_result = results[0]

        else:

            logger.error(
                f"Sentiment agent failed: {results[0]}"
            )

        # ----------------------------------------------------
        # Technical
        # ----------------------------------------------------

        if not isinstance(
            results[1],
            Exception
        ):

            technical_result = results[1]

        else:

            logger.error(
                f"Technical agent failed: {results[1]}"
            )

        return (
            sentiment_result,
            technical_result
        )

    # ========================================================
    # DECISION AGENT
    # ========================================================

    async def _run_decision(
        self,
        symbol: str,
        sentiment: Optional[SentimentResult],
        technical: Optional[TechnicalResult],
        market_data: Dict[str, Any]
    ) -> Optional[DecisionResult]:

        try:

            return await asyncio.to_thread(
                self.decision_agent.analyze,
                symbol,
                sentiment,
                technical,
                market_data
            )

        except Exception as e:

            logger.error(
                f"Decision agent failed: {e}"
            )

            return None

    # ========================================================
    # FORECAST AGENT
    # ========================================================

    async def _run_forecast(
        self,
        symbol: str,
        sentiment: Optional[SentimentResult],
        technical: Optional[TechnicalResult],
        market_data: Dict[str, Any]
    ) -> Optional[ForecastResult]:

        try:

            return await asyncio.to_thread(
                self.forecast_agent.analyze,
                symbol,
                sentiment,
                technical,
                market_data
            )

        except Exception as e:

            logger.error(
                f"Forecast agent failed: {e}"
            )

            return None

    # ========================================================
    # REFLECTOR
    # ========================================================

    async def _run_reflection(
        self,
        symbol: str,
        market_data: Dict[str, Any]
    ) -> Optional[ReflectionResult]:

        try:

            trades = self._get_recent_trades(symbol)

            return await asyncio.to_thread(
                self.reflector_agent.analyze,
                symbol,
                trades,
                None
            )

        except Exception as e:

            logger.error(
                f"Reflector agent failed: {e}"
            )

            return None

    # ========================================================
    # VOTING
    # ========================================================

    def _perform_voting(
        self,
        sentiment: Optional[SentimentResult],
        technical: Optional[TechnicalResult],
        decision: Optional[DecisionResult],
        forecast: Optional[ForecastResult]
    ) -> Tuple[str, float]:

        """
        Weighted consensus.

        Tidak menggunakan jumlah vote saja.

        Setiap agent memberikan:
            score × weight

        kemudian dinormalisasi berdasarkan
        agent yang benar-benar tersedia.
        """

        weighted_scores = []

        # ----------------------------------------------------
        # Sentiment
        # ----------------------------------------------------

        if sentiment:

            score = self._safe_score(
                sentiment.overall_score
            )

            weight = self.agent_weights[
                "sentiment"
            ]

            weighted_scores.append(
                score * weight
            )

        # ----------------------------------------------------
        # Technical
        # ----------------------------------------------------

        if technical:

            score = self._safe_score(
                technical.overall_score
            )

            weight = self.agent_weights[
                "technical"
            ]

            weighted_scores.append(
                score * weight
            )

        # ----------------------------------------------------
        # Decision
        # ----------------------------------------------------

        if decision:

            score = self._safe_score(
                decision.action_score
            )

            weight = self.agent_weights[
                "decision"
            ]

            weighted_scores.append(
                score * weight
            )

        # ----------------------------------------------------
        # Forecast
        # ----------------------------------------------------

        if forecast:

            score = self._forecast_to_score(
                forecast
            )

            weight = self.agent_weights[
                "forecast"
            ]

            weighted_scores.append(
                score * weight
            )

        # ----------------------------------------------------
        # No valid agents
        # ----------------------------------------------------

        if not weighted_scores:

            return "HOLD", 0.0

        # ----------------------------------------------------
        # Normalize using actual weights
        # ----------------------------------------------------

        available_weight = 0.0

        if sentiment:
            available_weight += self.agent_weights["sentiment"]

        if technical:
            available_weight += self.agent_weights["technical"]

        if decision:
            available_weight += self.agent_weights["decision"]

        if forecast:
            available_weight += self.agent_weights["forecast"]

        if available_weight <= 0:

            return "HOLD", 0.0

        consensus_score = (
            sum(weighted_scores)
            / available_weight
        )

        consensus_score = max(
            -1.0,
            min(1.0, consensus_score)
        )

        consensus_action = self._score_to_action(
            consensus_score
        )

        return (
            consensus_action,
            consensus_score
        )

    # ========================================================
    # SCORE → ACTION
    # ========================================================

    def _score_to_action(
        self,
        score: float
    ) -> str:

        score = self._safe_score(score)

        if score >= self.voting_thresholds["strong_buy"]:
            return "STRONG_BUY"

        if score >= self.voting_thresholds["buy"]:
            return "BUY"

        if score <= self.voting_thresholds["strong_sell"]:
            return "STRONG_SELL"

        if score <= self.voting_thresholds["sell"]:
            return "SELL"

        return "HOLD"

    # ========================================================
    # FORECAST → SCORE
    # ========================================================

    def _forecast_to_score(
        self,
        forecast: ForecastResult
    ) -> float:

        score = 0.0

        # ----------------------------------------------------
        # Trend
        # ----------------------------------------------------

        trend = getattr(
            forecast,
            "primary_trend",
            ""
        )

        if trend == "BULLISH":

            score += 0.40

        elif trend == "BEARISH":

            score -= 0.40

        # ----------------------------------------------------
        # Next move probability
        # ----------------------------------------------------

        next_move = getattr(
            forecast,
            "next_move_probability",
            {}
        )

        if not isinstance(
            next_move,
            dict
        ):

            next_move = {}

        up_probability = float(
            next_move.get("UP", 0)
            or 0
        )

        down_probability = float(
            next_move.get("DOWN", 0)
            or 0
        )

        if up_probability > 0.50:

            score += 0.30

        elif down_probability > 0.50:

            score -= 0.30

        # ----------------------------------------------------
        # Short term prediction
        # ----------------------------------------------------

        try:

            short_term = forecast.short_term

            predicted_price = float(
                short_term.predicted_price
            )

            current_price = float(
                forecast.current_price
            )

            if current_price > 0:

                if predicted_price > current_price:

                    score += 0.20

                elif predicted_price < current_price:

                    score -= 0.20

        except Exception:

            pass

        return max(
            -1.0,
            min(1.0, score)
        )

    # ========================================================
    # AGENT VOTES
    # ========================================================

    def _get_agent_votes(
        self,
        sentiment: Optional[SentimentResult],
        technical: Optional[TechnicalResult],
        decision: Optional[DecisionResult],
        forecast: Optional[ForecastResult]
    ) -> Dict[str, str]:

        votes = {}

        if sentiment:

            votes["sentiment"] = (
                self._score_to_action(
                    sentiment.overall_score
                )
            )

        if technical:

            votes["technical"] = (
                self._score_to_action(
                    technical.overall_score
                )
            )

        if decision:

            votes["decision"] = (
                decision.action
            )

        if forecast:

            votes["forecast"] = (
                self._score_to_action(
                    self._forecast_to_score(
                        forecast
                    )
                )
            )

        return votes

    # ========================================================
    # FINAL DECISION
    # ========================================================

    def _determine_final_decision(
        self,
        decision: Optional[DecisionResult],
        consensus_action: str,
        consensus_score: float,
        sentiment: Optional[SentimentResult],
        technical: Optional[TechnicalResult],
        forecast: Optional[ForecastResult]
    ) -> Tuple[
        str,
        float,
        float,
        Dict[str, float]
    ]:

        """
        Menggabungkan decision agent dengan consensus.

        Tidak memberikan bonus confidence secara arbitrer.

        Confidence dibangun dari:
            1. Decision confidence
            2. Consensus strength
            3. Agent agreement
        """

        # ----------------------------------------------------
        # Decision score
        # ----------------------------------------------------

        if decision:

            decision_score = self._safe_score(
                decision.action_score
            )

            decision_confidence = max(
                0.0,
                min(
                    1.0,
                    float(
                        decision.confidence
                    )
                )
            )

        else:

            decision_score = 0.0
            decision_confidence = 0.0

        # ----------------------------------------------------
        # Consensus
        # ----------------------------------------------------

        consensus_strength = abs(
            self._safe_score(
                consensus_score
            )
        )

        # ----------------------------------------------------
        # Agent agreement
        # ----------------------------------------------------

        votes = self._get_agent_votes(
            sentiment,
            technical,
            decision,
            forecast
        )

        agreement = self._calculate_agreement(
            votes
        )

        # ----------------------------------------------------
        # Combined score
        #
        # Decision = 50%
        # Consensus = 35%
        # Agreement = directional modifier
        # ----------------------------------------------------

        if decision:

            combined_score = (
                decision_score * 0.50
                +
                consensus_score * 0.35
                +
                self._agreement_direction(
                    votes,
                    consensus_score
                ) * 0.15
            )

        else:

            combined_score = consensus_score

        combined_score = max(
            -1.0,
            min(1.0, combined_score)
        )

        # ----------------------------------------------------
        # Final action
        # ----------------------------------------------------

        final_action = self._score_to_action(
            combined_score
        )

        # ----------------------------------------------------
        # Confidence
        #
        # Confidence is NOT:
        #
        #     decision.confidence + 0.1
        #
        # Instead:
        #
        # confidence =
        #   decision confidence
        #   × consensus strength
        #   × agreement
        # ----------------------------------------------------

        if decision:

            raw_confidence = (
                decision_confidence * 0.50
                +
                consensus_strength * 0.30
                +
                agreement * 0.20
            )

        else:

            raw_confidence = (
                consensus_strength * 0.70
                +
                agreement * 0.30
            )

        final_confidence = max(
            0.0,
            min(
                1.0,
                raw_confidence
            )
        )

        # ----------------------------------------------------
        # Confidence components
        # ----------------------------------------------------

        confidence_components = {

            "decision_confidence":
                round(
                    decision_confidence,
                    4
                ),

            "consensus_strength":
                round(
                    consensus_strength,
                    4
                ),

            "agent_agreement":
                round(
                    agreement,
                    4
                ),

            "combined_score":
                round(
                    combined_score,
                    4
                )
        }

        return (
            final_action,
            final_confidence,
            combined_score,
            confidence_components
        )

    # ========================================================
    # AGREEMENT
    # ========================================================

    def _calculate_agreement(
        self,
        votes: Dict[str, str]
    ) -> float:

        """
        Mengukur seberapa konsisten agent.

        1.0 = semua searah
        0.0 = sangat terpecah
        """

        if not votes:

            return 0.0

        scores = []

        for action in votes.values():

            scores.append(
                self._action_to_score(action)
            )

        if not scores:

            return 0.0

        positive = sum(
            1
            for score in scores
            if score > 0
        )

        negative = sum(
            1
            for score in scores
            if score < 0
        )

        neutral = sum(
            1
            for score in scores
            if score == 0
        )

        total = len(scores)

        dominant = max(
            positive,
            negative,
            neutral
        )

        return dominant / total

    # ========================================================
    # AGREEMENT DIRECTION
    # ========================================================

    def _agreement_direction(
        self,
        votes: Dict[str, str],
        consensus_score: float
    ) -> float:

        """
        Memberikan kontribusi directional berdasarkan
        mayoritas agent.

        Jika mayoritas bullish:
            positif

        Jika mayoritas bearish:
            negatif

        Jika netral:
            0
        """

        if not votes:

            return 0.0

        scores = [

            self._action_to_score(action)

            for action in votes.values()

        ]

        if not scores:

            return 0.0

        average = sum(scores) / len(scores)

        # Direction consensus
        if consensus_score > 0:

            return max(
                0.0,
                average
            )

        if consensus_score < 0:

            return min(
                0.0,
                average
            )

        return 0.0

    # ========================================================
    # ACTION → SCORE
    # ========================================================

    def _action_to_score(
        self,
        action: str
    ) -> float:

        mapping = {

            "STRONG_BUY": 1.0,

            "BUY": 0.5,

            "HOLD": 0.0,

            "SELL": -0.5,

            "STRONG_SELL": -1.0,
        }

        return mapping.get(
            str(action).upper(),
            0.0
        )

    # ========================================================
    # POSITION SIZE
    # ========================================================

    def _calculate_position_size(
        self,
        confidence: float,
        decision: Optional[DecisionResult],
        action: str
    ) -> float:

        """
        Preliminary position sizing.

        PENTING:
        Ini BELUM risk engine.

        Risk Engine nantinya akan menjadi
        authority final untuk position sizing.
        """

        if action == "HOLD":

            return 0.0

        if decision:

            base_size = float(
                getattr(
                    decision,
                    "suggested_position_size",
                    self.default_position_size
                )
                or self.default_position_size
            )

        else:

            base_size = (
                self.default_position_size
            )

        confidence_factor = max(
            0.0,
            min(
                1.0,
                confidence
            )
        )

        size = (
            base_size
            * confidence_factor
        )

        return max(
            0.0,
            min(
                self.max_position_size,
                size
            )
        )

    # ========================================================
    # SL / TP
    # ========================================================

    def _calculate_sl_tp(
        self,
        technical: Optional[TechnicalResult],
        action: str,
        current_price: float
    ) -> Tuple[
        Optional[float],
        Optional[float]
    ]:

        if (
            not technical
            or current_price <= 0
        ):

            return None, None

        stop_loss = None
        take_profit = None

        # ----------------------------------------------------
        # BUY
        # ----------------------------------------------------

        if action in [
            "BUY",
            "STRONG_BUY"
        ]:

            support_levels = getattr(
                technical,
                "support_levels",
                None
            )

            resistance_levels = getattr(
                technical,
                "resistance_levels",
                None
            )

            if support_levels:

                stop_loss = (
                    min(support_levels)
                    * 0.99
                )

            else:

                stop_loss = (
                    current_price
                    * 0.95
                )

            if resistance_levels:

                take_profit = (
                    max(resistance_levels)
                    * 1.01
                )

            else:

                take_profit = (
                    current_price
                    * 1.10
                )

        # ----------------------------------------------------
        # SELL
        # ----------------------------------------------------

        elif action in [
            "SELL",
            "STRONG_SELL"
        ]:

            support_levels = getattr(
                technical,
                "support_levels",
                None
            )

            resistance_levels = getattr(
                technical,
                "resistance_levels",
                None
            )

            if resistance_levels:

                stop_loss = (
                    max(resistance_levels)
                    * 1.01
                )

            else:

                stop_loss = (
                    current_price
                    * 1.05
                )

            if support_levels:

                take_profit = (
                    min(support_levels)
                    * 0.99
                )

            else:

                take_profit = (
                    current_price
                    * 0.90
                )

        return (
            stop_loss,
            take_profit
        )

    # ========================================================
    # MARKET SCORES
    # ========================================================

    def _build_market_scores(
        self,
        sentiment: Optional[SentimentResult],
        technical: Optional[TechnicalResult],
        decision: Optional[DecisionResult],
        forecast: Optional[ForecastResult],
        consensus_score: float
    ) -> Dict[str, float]:

        scores = {}

        if sentiment:

            scores["sentiment"] = round(
                self._safe_score(
                    sentiment.overall_score
                ),
                4
            )

        if technical:

            scores["technical"] = round(
                self._safe_score(
                    technical.overall_score
                ),
                4
            )

        if decision:

            scores["decision"] = round(
                self._safe_score(
                    decision.action_score
                ),
                4
            )

        if forecast:

            scores["forecast"] = round(
                self._forecast_to_score(
                    forecast
                ),
                4
            )

        scores["consensus"] = round(
            self._safe_score(
                consensus_score
            ),
            4
        )

        return scores

    # ========================================================
    # CURRENT PRICE
    # ========================================================

    def _get_current_price(
        self,
        market_data: Dict[str, Any],
        technical: Optional[TechnicalResult]
    ) -> float:

        if market_data:

            price = market_data.get(
                "current_price"
            )

            if price is not None:

                try:

                    return float(price)

                except (
                    ValueError,
                    TypeError
                ):

                    pass

        if technical:

            try:

                return float(
                    technical.current_price
                )

            except (
                ValueError,
                TypeError
            ):

                pass

        return 0.0

    # ========================================================
    # RECENT TRADES
    # ========================================================

    def _get_recent_trades(
        self,
        symbol: str
    ) -> List[TradeRecord]:

        trades = []

        for result in self.history[-50:]:

            if result.symbol != symbol:

                continue

            if result.final_action not in [
                "BUY",
                "STRONG_BUY",
                "SELL",
                "STRONG_SELL"
            ]:

                continue

            trade = TradeRecord(

                trade_id=(
                    f"TRADE_"
                    f"{result.timestamp.timestamp()}"
                ),

                symbol=result.symbol,

                entry_price=result.current_price,

                exit_price=0.0,

                entry_time=result.timestamp,

                exit_time=result.timestamp,

                position_size=result.position_size,

                action=result.final_action,

                outcome="PENDING",

                pnl=0.0,

                pnl_percent=0.0,

                holding_period_hours=0.0,

                decision_confidence=(
                    result.final_confidence
                ),

                sentiment_score_at_entry=(
                    result.sentiment.overall_score
                    if result.sentiment
                    else 0
                ),

                technical_score_at_entry=(
                    result.technical.overall_score
                    if result.technical
                    else 0
                ),

                stop_loss=(
                    result.stop_loss
                    or 0
                ),

                take_profit=(
                    result.take_profit
                    or 0
                ),

                reason_closed="PENDING"
            )

            trades.append(trade)

        return trades

    # ========================================================
    # SUMMARY
    # ========================================================

    def _generate_summary(
        self,
        symbol: str,
        current_price: float,
        final_action: str,
        final_confidence: float,
        position_size: float,
        consensus_action: str,
        consensus_score: float,
        agent_votes: Dict[str, str],
        stop_loss: Optional[float],
        take_profit: Optional[float]
    ) -> str:

        summary = ""

        summary += (
            "=== ORCHESTRATOR SUMMARY ===\n"
        )

        summary += (
            f"Symbol: {symbol}\n"
        )

        summary += (
            f"Current Price: "
            f"{current_price:.8f}\n"
        )

        summary += (
            f"Final Action: "
            f"{final_action}\n"
        )

        summary += (
            f"Confidence: "
            f"{final_confidence:.2%}\n"
        )

        summary += (
            f"Position Size: "
            f"{position_size:.2%}\n"
        )

        summary += (
            f"Consensus: "
            f"{consensus_action}\n"
        )

        summary += (
            f"Consensus Score: "
            f"{consensus_score:.4f}\n"
        )

        if stop_loss:

            summary += (
                f"Stop Loss: "
                f"{stop_loss:.8f}\n"
            )

        if take_profit:

            summary += (
                f"Take Profit: "
                f"{take_profit:.8f}\n"
            )

        summary += "\nAgent Votes:\n"

        if agent_votes:

            for agent, vote in agent_votes.items():

                summary += (
                    f"  {agent}: {vote}\n"
                )

        else:

            summary += (
                "  No valid agent votes\n"
            )

        return summary

    # ========================================================
    # SAFE SCORE
    # ========================================================

    def _safe_score(
        self,
        value: Any
    ) -> float:

        try:

            value = float(value)

        except (
            ValueError,
            TypeError
        ):

            return 0.0

        if value != value:

            return 0.0

        return max(
            -1.0,
            min(
                1.0,
                value
            )
        )

    # ========================================================
    # DEFAULT RESULT
    # ========================================================

    def _get_default_result(
        self,
        symbol: str
    ) -> OrchestratorResult:

        return OrchestratorResult(

            timestamp=datetime.now(),

            symbol=symbol,

            current_price=0.0,

            sentiment=None,

            technical=None,

            decision=None,

            reflection=None,

            forecast=None,

            consensus_action="HOLD",

            consensus_score=0.0,

            agent_votes={},

            final_action="HOLD",

            final_confidence=0.0,

            position_size=0.0,

            stop_loss=None,

            take_profit=None,

            decision_score=0.0,

            confidence_components={
                "decision_confidence": 0.0,
                "consensus_strength": 0.0,
                "agent_agreement": 0.0,
                "combined_score": 0.0
            },

            market_scores={},

            summary=(
                "Orchestrator error. "
                "Default decision: HOLD"
            )
        )

    # ========================================================
    # HISTORY
    # ========================================================

    def get_history(
        self,
        n: int = 10
    ) -> List[OrchestratorResult]:

        return self.history[-n:]


# ============================================================
# TEST / DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":

    async def main():

        orchestrator = Orchestrator()

        result = await orchestrator.analyze(
            "BTC-USD"
        )

        print("=" * 60)

        print(
            "ORCHESTRATOR RESULT"
        )

        print("=" * 60)

        print(
            f"Symbol: "
            f"{result.symbol}"
        )

        print(
            f"Price: "
            f"{result.current_price}"
        )

        print(
            f"Action: "
            f"{result.final_action}"
        )

        print(
            f"Confidence: "
            f"{result.final_confidence:.2%}"
        )

        print(
            f"Position Size: "
            f"{result.position_size:.2%}"
        )

        print(
            f"Consensus: "
            f"{result.consensus_action}"
        )

        print(
            f"Consensus Score: "
            f"{result.consensus_score:.4f}"
        )

        print(
            "\nAgent Votes:"
        )

        for agent, vote in result.agent_votes.items():

            print(
                f"  {agent}: {vote}"
            )

        print(
            "\nMarket Scores:"
        )

        for name, score in result.market_scores.items():

            print(
                f"  {name}: {score:.4f}"
            )

        print(
            "\nConfidence Components:"
        )

        for name, value in result.confidence_components.items():

            print(
                f"  {name}: {value:.4f}"
            )

        print(
            "\n"
            + result.summary
        )

    asyncio.run(main())
