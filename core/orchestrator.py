"""
Orchestrator - AI Decision Coordination Layer

Tanggung jawab:
1. Menjalankan AI agents.
2. Menghindari pemanggilan agent yang sama secara berulang.
3. Mengumpulkan hasil agent.
4. Menghitung weighted consensus.
5. Mengukur agent agreement.
6. Menghitung final confidence.
7. Menentukan final action.
8. Menghasilkan preliminary position size.
9. Menghasilkan preliminary Stop Loss / Take Profit.
10. Menyediakan data untuk Risk Engine.
11. TIDAK melakukan order execution.

Arsitektur:

    Market Data
         |
         +--> Sentiment Agent
         |
         +--> Technical Agent
                    |
                    +--> Decision Agent
                    |
                    +--> Forecast Agent
                    |
                    +--> Reflector Agent
                              |
                              v
                       Weighted Consensus
                              |
                              v
                       Final Decision
                              |
                              v
                    Preliminary SL / TP
                              |
                              v
                         Risk Engine
                              |
                              v
                          Executor

PENTING:
Orchestrator bukan Risk Engine.
Orchestrator bukan Executor.
Orchestrator hanya menghasilkan preliminary decision.
"""

import asyncio
import logging

from dataclasses import dataclass
from datetime import datetime, timezone

from typing import (
    Dict,
    List,
    Optional,
    Any,
    Tuple,
)


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

    TIDAK melakukan:
        - order placement
        - exchange execution
        - portfolio mutation
        - final risk approval

    Tugasnya hanya:
        Analysis
            ->
        Consensus
            ->
        Decision
            ->
        Preliminary Risk Parameters
    """

    # ========================================================
    # INITIALIZATION
    # ========================================================

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None
    ):

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
        # Voting thresholds
        # ----------------------------------------------------

        self.voting_thresholds = {

            "strong_buy": 0.70,

            "buy": 0.30,

            "sell": -0.30,

            "strong_sell": -0.70,
        }

        # ----------------------------------------------------
        # Agent weights
        #
        # Total = 1.0
        #
        # Reflector sengaja tidak dimasukkan ke voting.
        #
        # Reflector bertugas melakukan historical reflection,
        # bukan memberikan direct market direction.
        # ----------------------------------------------------

        self.agent_weights = {

            "sentiment": 0.25,

            "technical": 0.30,

            "decision": 0.30,

            "forecast": 0.15,
        }

        # ----------------------------------------------------
        # Position size
        #
        # Ini BUKAN final risk sizing.
        # Risk Engine akan override nilai ini.
        # ----------------------------------------------------

        self.max_position_size = float(
            self.config.get(
                "max_position_size",
                0.20
            )
        )

        self.default_position_size = float(
            self.config.get(
                "default_position_size",
                0.05
            )
        )

        # ----------------------------------------------------
        # History
        #
        # History hanya menyimpan ANALYSIS RESULT.
        # Tidak dianggap sebagai executed trade.
        # ----------------------------------------------------

        self.history: List[
            OrchestratorResult
        ] = []

        self.max_history = int(
            self.config.get(
                "max_history",
                100
            )
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
        market_data: Optional[
            Dict[str, Any]
        ] = None
    ) -> OrchestratorResult:

        """
        Menjalankan seluruh pipeline analisis.

        Tidak melakukan trading execution.
        """

        logger.info(
            "Starting analysis for %s",
            symbol
        )

        market_data = (
            market_data.copy()
            if isinstance(market_data, dict)
            else {}
        )

        try:

            # ------------------------------------------------
            # STEP 1
            # Base agents
            # ------------------------------------------------

            (
                sentiment_result,
                technical_result
            ) = await self._run_base_agents(
                symbol,
                market_data
            )

            # ------------------------------------------------
            # STEP 2
            # Decision
            # ------------------------------------------------

            decision_result = (
                await self._run_decision(
                    symbol,
                    sentiment_result,
                    technical_result,
                    market_data
                )
            )

            # ------------------------------------------------
            # STEP 3
            # Forecast
            # ------------------------------------------------

            forecast_result = (
                await self._run_forecast(
                    symbol,
                    sentiment_result,
                    technical_result,
                    market_data
                )
            )

            # ------------------------------------------------
            # STEP 4
            # Reflection
            # ------------------------------------------------

            reflection_result = (
                await self._run_reflection(
                    symbol,
                    market_data
                )
            )

            # ------------------------------------------------
            # STEP 5
            # Current price
            # ------------------------------------------------

            current_price = (
                self._get_current_price(
                    market_data,
                    technical_result,
                    forecast_result
                )
            )

            # ------------------------------------------------
            # STEP 6
            # Weighted consensus
            # ------------------------------------------------

            (
                consensus_action,
                consensus_score
            ) = self._perform_voting(
                sentiment=sentiment_result,
                technical=technical_result,
                decision=decision_result,
                forecast=forecast_result
            )

            # ------------------------------------------------
            # STEP 7
            # Agent votes
            # ------------------------------------------------

            agent_votes = (
                self._get_agent_votes(
                    sentiment=sentiment_result,
                    technical=technical_result,
                    decision=decision_result,
                    forecast=forecast_result
                )
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

            position_size = (
                self._calculate_position_size(
                    confidence=final_confidence,
                    decision=decision_result,
                    action=final_action
                )
            )

            # ------------------------------------------------
            # STEP 10
            # Preliminary SL / TP
            # ------------------------------------------------

            (
                stop_loss,
                take_profit
            ) = self._calculate_sl_tp(
                technical=technical_result,
                action=final_action,
                current_price=current_price
            )

            # ------------------------------------------------
            # STEP 11
            # Market scores
            # ------------------------------------------------

            market_scores = (
                self._build_market_scores(
                    sentiment=sentiment_result,
                    technical=technical_result,
                    decision=decision_result,
                    forecast=forecast_result,
                    consensus_score=consensus_score
                )
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

                timestamp=datetime.now(
                    timezone.utc
                ),

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

                confidence_components=(
                    confidence_components
                ),

                market_scores=market_scores,

                summary=summary
            )

            # ------------------------------------------------
            # STEP 14
            # Save history
            # ------------------------------------------------

            self.history.append(result)

            if len(self.history) > self.max_history:

                self.history.pop(0)

            logger.info(
                "Analysis completed: %s -> %s "
                "(confidence=%.2f%%)",
                symbol,
                final_action,
                final_confidence * 100
            )

            return result

        except Exception as e:

            logger.exception(
                "Orchestrator analysis failed for %s: %s",
                symbol,
                e
            )

            return self._get_default_result(
                symbol
            )

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
        Sentiment + Technical dijalankan paralel.

        Keduanya hanya dipanggil satu kali per analysis cycle.
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
            ),
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

        if (
            len(results) > 0
            and not isinstance(
                results[0],
                Exception
            )
        ):

            sentiment_result = results[0]

        else:

            error = (
                results[0]
                if results
                else "Unknown error"
            )

            logger.error(
                "Sentiment agent failed: %s",
                error
            )

        # ----------------------------------------------------
        # Technical
        # ----------------------------------------------------

        if (
            len(results) > 1
            and not isinstance(
                results[1],
                Exception
            )
        ):

            technical_result = results[1]

        else:

            error = (
                results[1]
                if len(results) > 1
                else "Unknown error"
            )

            logger.error(
                "Technical agent failed: %s",
                error
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
        sentiment: Optional[
            SentimentResult
        ],
        technical: Optional[
            TechnicalResult
        ],
        market_data: Dict[str, Any]
    ) -> Optional[DecisionResult]:

        try:

            result = await asyncio.to_thread(
                self.decision_agent.analyze,
                symbol,
                sentiment,
                technical,
                market_data
            )

            return result

        except Exception as e:

            logger.error(
                "Decision agent failed: %s",
                e
            )

            return None

    # ========================================================
    # FORECAST AGENT
    # ========================================================

    async def _run_forecast(
        self,
        symbol: str,
        sentiment: Optional[
            SentimentResult
        ],
        technical: Optional[
            TechnicalResult
        ],
        market_data: Dict[str, Any]
    ) -> Optional[ForecastResult]:

        try:

            result = await asyncio.to_thread(
                self.forecast_agent.analyze,
                symbol,
                sentiment,
                technical,
                market_data
            )

            return result

        except Exception as e:

            logger.error(
                "Forecast agent failed: %s",
                e
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

        """
        Reflector tidak menggunakan analysis history
        sebagai executed trades.

        Jika market_data memiliki:

            recent_trades

        maka data tersebut diberikan ke Reflector.

        Dengan demikian:
            SIGNAL != TRADE
        """

        try:

            trades = market_data.get(
                "recent_trades",
                []
            )

            if trades is None:

                trades = []

            if not isinstance(
                trades,
                list
            ):

                trades = []

            return await asyncio.to_thread(
                self.reflector_agent.analyze,
                symbol,
                trades,
                None
            )

        except Exception as e:

            logger.error(
                "Reflector agent failed: %s",
                e
            )

            return None

    # ========================================================
    # VOTING
    # ========================================================

    def _perform_voting(
        self,
        sentiment: Optional[
            SentimentResult
        ],
        technical: Optional[
            TechnicalResult
        ],
        decision: Optional[
            DecisionResult
        ],
        forecast: Optional[
            ForecastResult
        ]
    ) -> Tuple[str, float]:

        """
        Weighted consensus.

        Rumus:

            sum(score * weight)
            -------------------
              available weight

        Dengan demikian agent yang gagal
        tidak membuat score menjadi bias ke 0.
        """

        weighted_total = 0.0

        available_weight = 0.0

        # ----------------------------------------------------
        # Sentiment
        # ----------------------------------------------------

        if sentiment is not None:

            score = self._safe_score(
                getattr(
                    sentiment,
                    "overall_score",
                    0.0
                )
            )

            weight = self.agent_weights[
                "sentiment"
            ]

            weighted_total += (
                score * weight
            )

            available_weight += weight

        # ----------------------------------------------------
        # Technical
        # ----------------------------------------------------

        if technical is not None:

            score = self._safe_score(
                getattr(
                    technical,
                    "overall_score",
                    0.0
                )
            )

            weight = self.agent_weights[
                "technical"
            ]

            weighted_total += (
                score * weight
            )

            available_weight += weight

        # ----------------------------------------------------
        # Decision
        # ----------------------------------------------------

        if decision is not None:

            score = self._safe_score(
                getattr(
                    decision,
                    "action_score",
                    0.0
                )
            )

            weight = self.agent_weights[
                "decision"
            ]

            weighted_total += (
                score * weight
            )

            available_weight += weight

        # ----------------------------------------------------
        # Forecast
        # ----------------------------------------------------

        if forecast is not None:

            score = self._forecast_to_score(
                forecast
            )

            weight = self.agent_weights[
                "forecast"
            ]

            weighted_total += (
                score * weight
            )

            available_weight += weight

        # ----------------------------------------------------
        # No agents
        # ----------------------------------------------------

        if available_weight <= 0:

            return (
                "HOLD",
                0.0
            )

        # ----------------------------------------------------
        # Normalize
        # ----------------------------------------------------

        consensus_score = (
            weighted_total
            / available_weight
        )

        consensus_score = self._safe_score(
            consensus_score
        )

        consensus_action = (
            self._score_to_action(
                consensus_score
            )
        )

        return (
            consensus_action,
            consensus_score
        )

    # ========================================================
    # SCORE -> ACTION
    # ========================================================

    def _score_to_action(
        self,
        score: float
    ) -> str:

        score = self._safe_score(
            score
        )

        if score >= self.voting_thresholds[
            "strong_buy"
        ]:

            return "STRONG_BUY"

        if score >= self.voting_thresholds[
            "buy"
        ]:

            return "BUY"

        if score <= self.voting_thresholds[
            "strong_sell"
        ]:

            return "STRONG_SELL"

        if score <= self.voting_thresholds[
            "sell"
        ]:

            return "SELL"

        return "HOLD"

    # ========================================================
    # FORECAST -> SCORE
    # ========================================================

    def _forecast_to_score(
        self,
        forecast: ForecastResult
    ) -> float:

        """
        Mengubah ForecastResult menjadi score -1 sampai +1.

        Komponen:

            Trend              40%
            Probability        30%
            Price prediction   30%
        """

        # ----------------------------------------------------
        # Trend
        # ----------------------------------------------------

        trend_score = 0.0

        trend = str(
            getattr(
                forecast,
                "primary_trend",
                ""
            )
        ).upper()

        if trend == "BULLISH":

            trend_score = 1.0

        elif trend == "BEARISH":

            trend_score = -1.0

        # ----------------------------------------------------
        # Probability
        # ----------------------------------------------------

        probability_score = 0.0

        next_move = getattr(
            forecast,
            "next_move_probability",
            {}
        )

        if isinstance(
            next_move,
            dict
        ):

            up_probability = self._safe_probability(
                next_move.get(
                    "UP",
                    0.0
                )
            )

            down_probability = self._safe_probability(
                next_move.get(
                    "DOWN",
                    0.0
                )
            )

            probability_score = (
                up_probability
                -
                down_probability
            )

        # ----------------------------------------------------
        # Predicted price
        # ----------------------------------------------------

        prediction_score = 0.0

        try:

            short_term = getattr(
                forecast,
                "short_term",
                None
            )

            predicted_price = float(
                getattr(
                    short_term,
                    "predicted_price"
                )
            )

            current_price = float(
                getattr(
                    forecast,
                    "current_price"
                )
            )

            if current_price > 0:

                price_change = (
                    predicted_price
                    -
                    current_price
                ) / current_price

                # Clamp price impact.
                #
                # 5% movement = maximum directional score.

                prediction_score = max(
                    -1.0,
                    min(
                        1.0,
                        price_change / 0.05
                    )
                )

        except (
            AttributeError,
            TypeError,
            ValueError,
            ZeroDivisionError
        ):

            prediction_score = 0.0

        # ----------------------------------------------------
        # Combine
        # ----------------------------------------------------

        score = (
            trend_score * 0.40
            +
            probability_score * 0.30
            +
            prediction_score * 0.30
        )

        return self._safe_score(
            score
        )

    # ========================================================
    # AGENT VOTES
    # ========================================================

    def _get_agent_votes(
        self,
        sentiment: Optional[
            SentimentResult
        ],
        technical: Optional[
            TechnicalResult
        ],
        decision: Optional[
            DecisionResult
        ],
        forecast: Optional[
            ForecastResult
        ]
    ) -> Dict[str, str]:

        votes: Dict[str, str] = {}

        if sentiment is not None:

            votes["sentiment"] = (
                self._score_to_action(
                    self._safe_score(
                        getattr(
                            sentiment,
                            "overall_score",
                            0.0
                        )
                    )
                )
            )

        if technical is not None:

            votes["technical"] = (
                self._score_to_action(
                    self._safe_score(
                        getattr(
                            technical,
                            "overall_score",
                            0.0
                        )
                    )
                )
            )

        if decision is not None:

            decision_action = str(
                getattr(
                    decision,
                    "action",
                    "HOLD"
                )
            ).upper()

            # Validate action.
            valid_actions = {
                "STRONG_BUY",
                "BUY",
                "HOLD",
                "SELL",
                "STRONG_SELL",
            }

            if decision_action not in valid_actions:

                decision_action = (
                    self._score_to_action(
                        getattr(
                            decision,
                            "action_score",
                            0.0
                        )
                    )
                )

            votes["decision"] = (
                decision_action
            )

        if forecast is not None:

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
        decision: Optional[
            DecisionResult
        ],
        consensus_action: str,
        consensus_score: float,
        sentiment: Optional[
            SentimentResult
        ],
        technical: Optional[
            TechnicalResult
        ],
        forecast: Optional[
            ForecastResult
        ]
    ) -> Tuple[
        str,
        float,
        float,
        Dict[str, float]
    ]:

        # ----------------------------------------------------
        # Decision data
        # ----------------------------------------------------

        if decision is not None:

            decision_score = (
                self._safe_score(
                    getattr(
                        decision,
                        "action_score",
                        0.0
                    )
                )
            )

            decision_confidence = (
                self._safe_probability(
                    getattr(
                        decision,
                        "confidence",
                        0.0
                    )
                )
            )

        else:

            decision_score = 0.0

            decision_confidence = 0.0

        # ----------------------------------------------------
        # Consensus
        # ----------------------------------------------------

        consensus_score = self._safe_score(
            consensus_score
        )

        consensus_strength = abs(
            consensus_score
        )

        # ----------------------------------------------------
        # Votes
        # ----------------------------------------------------

        votes = self._get_agent_votes(
            sentiment=sentiment,
            technical=technical,
            decision=decision,
            forecast=forecast
        )

        agreement = (
            self._calculate_agreement(
                votes
            )
        )

        agreement_direction = (
            self._agreement_direction(
                votes
            )
        )

        # ----------------------------------------------------
        # Combined score
        # ----------------------------------------------------

        if decision is not None:

            combined_score = (

                decision_score * 0.50

                +

                consensus_score * 0.35

                +

                agreement_direction * 0.15
            )

        else:

            combined_score = (
                consensus_score
            )

        combined_score = self._safe_score(
            combined_score
        )

        # ----------------------------------------------------
        # Final action
        # ----------------------------------------------------

        final_action = (
            self._score_to_action(
                combined_score
            )
        )

        # ----------------------------------------------------
        # Confidence
        # ----------------------------------------------------

        if decision is not None:

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
        # HOLD confidence protection
        #
        # Jangan memberikan confidence tinggi kepada HOLD
        # hanya karena agent sepakat HOLD.
        # ----------------------------------------------------

        if final_action == "HOLD":

            final_confidence = min(
                final_confidence,
                0.50
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

            "agreement_direction":
                round(
                    agreement_direction,
                    4
                ),

            "combined_score":
                round(
                    combined_score,
                    4
                ),
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
        Mengukur directional agreement.

        HOLD tidak dihitung sebagai bullish/bearish.

        Contoh:

            BUY
            STRONG_BUY
            BUY
            SELL

        bullish = 3
        bearish = 1

        agreement = 3 / 4 = 0.75
        """

        if not votes:

            return 0.0

        scores = [

            self._action_to_score(
                action
            )

            for action in votes.values()
        ]

        if not scores:

            return 0.0

        bullish = sum(
            1
            for score in scores
            if score > 0
        )

        bearish = sum(
            1
            for score in scores
            if score < 0
        )

        total_directional = (
            bullish
            +
            bearish
        )

        # ----------------------------------------------------
        # Semua HOLD
        # ----------------------------------------------------

        if total_directional == 0:

            return 0.0

        dominant = max(
            bullish,
            bearish
        )

        return (
            dominant
            /
            len(scores)
        )

    # ========================================================
    # AGREEMENT DIRECTION
    # ========================================================

    def _agreement_direction(
        self,
        votes: Dict[str, str]
    ) -> float:

        """
        Menghasilkan directional score dari vote agent.

        Tidak lagi menggunakan consensus_score sebagai
        input sehingga tidak terjadi circular reinforcement.
        """

        if not votes:

            return 0.0

        scores = [

            self._action_to_score(
                action
            )

            for action in votes.values()
        ]

        if not scores:

            return 0.0

        return self._safe_score(
            sum(scores)
            /
            len(scores)
        )

    # ========================================================
    # ACTION -> SCORE
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
        decision: Optional[
            DecisionResult
        ],
        action: str
    ) -> float:

        """
        Preliminary position sizing.

        BUKAN final risk sizing.

        Risk Engine wajib melakukan validasi ulang.
        """

        if action == "HOLD":

            return 0.0

        confidence = self._safe_probability(
            confidence
        )

        if decision is not None:

            raw_base_size = getattr(
                decision,
                "suggested_position_size",
                self.default_position_size
            )

            try:

                base_size = float(
                    raw_base_size
                )

            except (
                TypeError,
                ValueError
            ):

                base_size = (
                    self.default_position_size
                )

        else:

            base_size = (
                self.default_position_size
            )

        if base_size < 0:

            base_size = 0.0

        size = (
            base_size
            *
            confidence
        )

        size = max(
            0.0,
            min(
                self.max_position_size,
                size
            )
        )

        return size

    # ========================================================
    # SL / TP
    # ========================================================

    def _calculate_sl_tp(
        self,
        technical: Optional[
            TechnicalResult
        ],
        action: str,
        current_price: float
    ) -> Tuple[
        Optional[float],
        Optional[float]
    ]:

        """
        Menghasilkan preliminary SL/TP.

        BUY:
            SL = support terdekat di bawah price
            TP = resistance terdekat di atas price

        SELL:
            SL = resistance terdekat di atas price
            TP = support terdekat di bawah price

        Risk Engine tetap harus memvalidasi semuanya.
        """

        if (
            technical is None
            or current_price <= 0
        ):

            return None, None

        if action == "HOLD":

            return None, None

        support_levels = (
            self._extract_price_levels(
                getattr(
                    technical,
                    "support_levels",
                    None
                )
            )
        )

        resistance_levels = (
            self._extract_price_levels(
                getattr(
                    technical,
                    "resistance_levels",
                    None
                )
            )
        )

        stop_loss = None

        take_profit = None

        # ----------------------------------------------------
        # BUY
        # ----------------------------------------------------

        if action in {
            "BUY",
            "STRONG_BUY"
        }:

            supports_below = [
                level
                for level in support_levels
                if level < current_price
            ]

            resistances_above = [
                level
                for level in resistance_levels
                if level > current_price
            ]

            if supports_below:

                nearest_support = max(
                    supports_below
                )

                stop_loss = (
                    nearest_support
                    * 0.99
                )

            else:

                stop_loss = (
                    current_price
                    * 0.95
                )

            if resistances_above:

                nearest_resistance = min(
                    resistances_above
                )

                take_profit = (
                    nearest_resistance
                    * 0.99
                )

            else:

                take_profit = (
                    current_price
                    * 1.10
                )

        # ----------------------------------------------------
        # SELL
        # ----------------------------------------------------

        elif action in {
            "SELL",
            "STRONG_SELL"
        }:

            resistances_above = [
                level
                for level in resistance_levels
                if level > current_price
            ]

            supports_below = [
                level
                for level in support_levels
                if level < current_price
            ]

            if resistances_above:

                nearest_resistance = min(
                    resistances_above
                )

                stop_loss = (
                    nearest_resistance
                    * 1.01
                )

            else:

                stop_loss = (
                    current_price
                    * 1.05
                )

            if supports_below:

                nearest_support = max(
                    supports_below
                )

                take_profit = (
                    nearest_support
                    * 1.01
                )

            else:

                take_profit = (
                    current_price
                    * 0.90
                )

        # ----------------------------------------------------
        # Validate
        # ----------------------------------------------------

        if stop_loss is not None:

            stop_loss = float(
                stop_loss
            )

        if take_profit is not None:

            take_profit = float(
                take_profit
            )

        return (
            stop_loss,
            take_profit
        )

    # ========================================================
    # EXTRACT PRICE LEVELS
    # ========================================================

    def _extract_price_levels(
        self,
        levels: Any
    ) -> List[float]:

        if levels is None:

            return []

        if not isinstance(
            levels,
            (list, tuple, set)
        ):

            return []

        clean_levels = []

        for level in levels:

            try:

                value = float(level)

            except (
                TypeError,
                ValueError
            ):

                continue

            if value > 0:

                clean_levels.append(
                    value
                )

        return sorted(
            set(clean_levels)
        )

    # ========================================================
    # MARKET SCORES
    # ========================================================

    def _build_market_scores(
        self,
        sentiment: Optional[
            SentimentResult
        ],
        technical: Optional[
            TechnicalResult
        ],
        decision: Optional[
            DecisionResult
        ],
        forecast: Optional[
            ForecastResult
        ],
        consensus_score: float
    ) -> Dict[str, float]:

        scores: Dict[str, float] = {}

        if sentiment is not None:

            scores["sentiment"] = round(
                self._safe_score(
                    getattr(
                        sentiment,
                        "overall_score",
                        0.0
                    )
                ),
                4
            )

        if technical is not None:

            scores["technical"] = round(
                self._safe_score(
                    getattr(
                        technical,
                        "overall_score",
                        0.0
                    )
                ),
                4
            )

        if decision is not None:

            scores["decision"] = round(
                self._safe_score(
                    getattr(
                        decision,
                        "action_score",
                        0.0
                    )
                ),
                4
            )

        if forecast is not None:

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
        technical: Optional[
            TechnicalResult
        ],
        forecast: Optional[
            ForecastResult
        ]
    ) -> float:

        # ----------------------------------------------------
        # 1. Market data
        # ----------------------------------------------------

        if market_data:

            possible_keys = [
                "current_price",
                "price",
                "last_price",
                "close",
            ]

            for key in possible_keys:

                value = market_data.get(
                    key
                )

                if value is None:

                    continue

                try:

                    price = float(
                        value
                    )

                    if price > 0:

                        return price

                except (
                    TypeError,
                    ValueError
                ):

                    continue

        # ----------------------------------------------------
        # 2. Technical
        # ----------------------------------------------------

        if technical is not None:

            try:

                price = float(
                    technical.current_price
                )

                if price > 0:

                    return price

            except (
                AttributeError,
                TypeError,
                ValueError
            ):

                pass

        # ----------------------------------------------------
        # 3. Forecast
        # ----------------------------------------------------

        if forecast is not None:

            try:

                price = float(
                    forecast.current_price
                )

                if price > 0:

                    return price

            except (
                AttributeError,
                TypeError,
                ValueError
            ):

                pass

        return 0.0

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

        lines = []

        lines.append(
            "=== ORCHESTRATOR SUMMARY ==="
        )

        lines.append(
            f"Symbol: {symbol}"
        )

        lines.append(
            f"Current Price: {current_price:.8f}"
        )

        lines.append(
            f"Final Action: {final_action}"
        )

        lines.append(
            f"Confidence: {final_confidence:.2%}"
        )

        lines.append(
            f"Preliminary Position Size: "
            f"{position_size:.2%}"
        )

        lines.append(
            f"Consensus: {consensus_action}"
        )

        lines.append(
            f"Consensus Score: "
            f"{consensus_score:.4f}"
        )

        if stop_loss is not None:

            lines.append(
                f"Preliminary Stop Loss: "
                f"{stop_loss:.8f}"
            )

        else:

            lines.append(
                "Preliminary Stop Loss: N/A"
            )

        if take_profit is not None:

            lines.append(
                f"Preliminary Take Profit: "
                f"{take_profit:.8f}"
            )

        else:

            lines.append(
                "Preliminary Take Profit: N/A"
            )

        lines.append("")

        lines.append(
            "Agent Votes:"
        )

        if agent_votes:

            for agent, vote in (
                agent_votes.items()
            ):

                lines.append(
                    f"  {agent}: {vote}"
                )

        else:

            lines.append(
                "  No valid agent votes"
            )

        lines.append("")

        lines.append(
            "NOTE: Position size and SL/TP "
            "are preliminary only. "
            "Risk Engine must validate them "
            "before execution."
        )

        return "\n".join(
            lines
        )

    # ========================================================
    # SAFE SCORE
    # ========================================================

    def _safe_score(
        self,
        value: Any
    ) -> float:

        try:

            value = float(
                value
            )

        except (
            TypeError,
            ValueError
        ):

            return 0.0

        if value != value:

            return 0.0

        if value == float(
            "inf"
        ):

            return 1.0

        if value == float(
            "-inf"
        ):

            return -1.0

        return max(
            -1.0,
            min(
                1.0,
                value
            )
        )

    # ========================================================
    # SAFE PROBABILITY
    # ========================================================

    def _safe_probability(
        self,
        value: Any
    ) -> float:

        try:

            value = float(
                value
            )

        except (
            TypeError,
            ValueError
        ):

            return 0.0

        if value != value:

            return 0.0

        return max(
            0.0,
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

        timestamp = datetime.now(
            timezone.utc
        )

        summary = (
            "=== ORCHESTRATOR ERROR ===\n"
            f"Symbol: {symbol}\n"
            "Final Action: HOLD\n"
            "Confidence: 0.00%\n"
            "Position Size: 0.00%\n"
            "No trading execution performed."
        )

        return OrchestratorResult(

            timestamp=timestamp,

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

                "agreement_direction": 0.0,

                "combined_score": 0.0,
            },

            market_scores={},

            summary=summary
        )

    # ========================================================
    # HISTORY
    # ========================================================

    def get_history(
        self,
        n: int = 10
    ) -> List[OrchestratorResult]:

        if n <= 0:

            return []

        return self.history[-n:]


# ============================================================
# TEST / DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":

    async def main():

        print("=" * 70)

        print(
            "AI TRADING ORCHESTRATOR"
        )

        print(
            "Starting..."
        )

        print("=" * 70)

        orchestrator = Orchestrator()

        result = await orchestrator.analyze(
            "BTC-USD"
        )

        print()

        print("=" * 70)

        print(
            "ORCHESTRATOR RESULT"
        )

        print("=" * 70)

        print(
            f"Timestamp      : "
            f"{result.timestamp.isoformat()}"
        )

        print(
            f"Symbol         : "
            f"{result.symbol}"
        )

        print(
            f"Current Price  : "
            f"{result.current_price}"
        )

        print()

        print(
            "--- AGENT STATUS ---"
        )

        print(
            f"Sentiment      : "
            f"{'OK' if result.sentiment else 'FAILED'}"
        )

        print(
            f"Technical      : "
            f"{'OK' if result.technical else 'FAILED'}"
        )

        print(
            f"Decision       : "
            f"{'OK' if result.decision else 'FAILED'}"
        )

        print(
            f"Forecast       : "
            f"{'OK' if result.forecast else 'FAILED'}"
        )

        print(
            f"Reflector      : "
            f"{'OK' if result.reflection else 'FAILED'}"
        )

        print()

        print(
            "--- CONSENSUS ---"
        )

        print(
            f"Consensus Action : "
            f"{result.consensus_action}"
        )

        print(
            f"Consensus Score  : "
            f"{result.consensus_score:.4f}"
        )

        print()

        print(
            "--- AGENT VOTES ---"
        )

        if result.agent_votes:

            for agent, vote in (
                result.agent_votes.items()
            ):

                print(
                    f"{agent:<15}: {vote}"
                )

        else:

            print(
                "No valid votes."
            )

        print()

        print(
            "--- FINAL DECISION ---"
        )

        print(
            f"Final Action     : "
            f"{result.final_action}"
        )

        print(
            f"Final Confidence : "
            f"{result.final_confidence:.2%}"
        )

        print(
            f"Decision Score   : "
            f"{result.decision_score:.4f}"
        )

        print()

        print(
            "--- POSITION ---"
        )

        print(
            f"Preliminary Size : "
            f"{result.position_size:.2%}"
        )

        if result.stop_loss is not None:

            print(
                f"Stop Loss        : "
                f"{result.stop_loss}"
            )

        else:

            print(
                "Stop Loss        : N/A"
            )

        if result.take_profit is not None:

            print(
                f"Take Profit      : "
                f"{result.take_profit}"
            )

        else:

            print(
                "Take Profit      : N/A"
            )

        print()

        print(
            "--- MARKET SCORES ---"
        )

        if result.market_scores:

            for name, score in (
                result.market_scores.items()
            ):

                print(
                    f"{name:<15}: {score:.4f}"
                )

        else:

            print(
                "No market scores."
            )

        print()

        print(
            "--- CONFIDENCE COMPONENTS ---"
        )

        for name, value in (
            result.confidence_components.items()
        ):

            print(
                f"{name:<22}: {value:.4f}"
            )

        print()

        print(
            "--- SUMMARY ---"
        )

        print(
            result.summary
        )

        print()

        print("=" * 70)

        print(
            "ORCHESTRATOR TEST COMPLETED"
        )

        print("=" * 70)

        print(
            "No order was executed."
        )

    asyncio.run(
        main()
    )
