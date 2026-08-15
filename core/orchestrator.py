"""
Orchestrator - AI Decision Coordination Layer
FULLY INTEGRATED WITH AGENTS
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple

# Import agents
from agents.agent_sentiment import SentimentAgent, SentimentResult
from agents.agent_technical import TechnicalAgent, TechnicalResult
from agents.agent_decision import DecisionAgent, DecisionResult
from agents.agent_reflector import ReflectorAgent, ReflectionResult, TradeRecord
from agents.agent_forecast import ForecastAgent, ForecastResult

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorResult:
    """Hasil lengkap dari proses analisis Orchestrator."""
    timestamp: datetime
    symbol: str
    current_price: float
    sentiment: Optional[SentimentResult]
    technical: Optional[TechnicalResult]
    decision: Optional[DecisionResult]
    reflection: Optional[ReflectionResult]
    forecast: Optional[ForecastResult]
    consensus_action: str
    consensus_score: float
    agent_votes: Dict[str, str]
    final_action: str
    final_confidence: float
    position_size: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    decision_score: float
    confidence_components: Dict[str, float]
    market_scores: Dict[str, float]
    summary: str
    execution_reason: Optional[str] = None


class Orchestrator:
    """Central coordinator untuk seluruh AI agents."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        
        # ============================================================
        # INITIALIZE AGENTS - FIXED
        # ============================================================
        
        self.sentiment_agent = SentimentAgent()
        self.technical_agent = TechnicalAgent()
        self.decision_agent = DecisionAgent()
        self.reflector_agent = ReflectorAgent()
        self.forecast_agent = ForecastAgent()
        
        # Voting thresholds
        self.voting_thresholds = {
            "strong_buy": 0.70,
            "buy": 0.30,
            "sell": -0.30,
            "strong_sell": -0.70,
        }
        
        # Agent weights
        self.agent_weights = {
            "sentiment": 0.20,
            "technical": 0.35,
            "decision": 0.35,
            "forecast": 0.10,
        }
        
        # Dynamic weights
        self.enable_dynamic_weights = config.get("enable_dynamic_weights", True)
        self.performance_history = {
            "sentiment": {"correct": 0, "total": 0},
            "technical": {"correct": 0, "total": 0},
            "decision": {"correct": 0, "total": 0},
            "forecast": {"correct": 0, "total": 0},
        }
        
        # Position size
        self.max_position_size = float(config.get("max_position_size", 0.20))
        self.default_position_size = float(config.get("default_position_size", 0.05))
        self.min_position_size = float(config.get("min_position_size", 0.01))
        
        # History
        self.history: List[OrchestratorResult] = []
        self.max_history = int(config.get("max_history", 100))
        
        logger.info("Orchestrator initialized successfully with agents")

    # ============================================================
    # PUBLIC ANALYZE
    # ============================================================
    
    async def analyze(
        self,
        symbol: str,
        market_data: Optional[Dict[str, Any]] = None
    ) -> OrchestratorResult:
        """
        Menjalankan seluruh pipeline analisis dengan agents.
        """
        logger.info("Starting analysis for %s", symbol)
        market_data = market_data.copy() if isinstance(market_data, dict) else {}
        
        try:
            # ============================================================
            # STEP 1: Base Agents (Sentiment + Technical) - PARALLEL
            # ============================================================
            
            sentiment_result, technical_result = await self._run_base_agents(
                symbol, market_data
            )
            
            # ============================================================
            # STEP 2: Decision Agent
            # ============================================================
            
            decision_result = await self._run_decision(
                symbol, sentiment_result, technical_result, market_data
            )
            
            # ============================================================
            # STEP 3: Forecast Agent
            # ============================================================
            
            forecast_result = await self._run_forecast(
                symbol, sentiment_result, technical_result, market_data
            )
            
            # ============================================================
            # STEP 4: Reflection Agent
            # ============================================================
            
            reflection_result = await self._run_reflection(symbol, market_data)
            
            # ============================================================
            # STEP 5: Current price
            # ============================================================
            
            current_price = self._get_current_price(
                market_data, technical_result, forecast_result
            )
            
            # ============================================================
            # STEP 6: Weighted consensus
            # ============================================================
            
            consensus_action, consensus_score = self._perform_voting(
                sentiment=sentiment_result,
                technical=technical_result,
                decision=decision_result,
                forecast=forecast_result
            )
            
            # ============================================================
            # STEP 7: Agent votes
            # ============================================================
            
            agent_votes = self._get_agent_votes(
                sentiment=sentiment_result,
                technical=technical_result,
                decision=decision_result,
                forecast=forecast_result
            )
            
            # ============================================================
            # STEP 8: Final decision
            # ============================================================
            
            final_action, final_confidence, decision_score, confidence_components = \
                self._determine_final_decision(
                    decision=decision_result,
                    consensus_action=consensus_action,
                    consensus_score=consensus_score,
                    sentiment=sentiment_result,
                    technical=technical_result,
                    forecast=forecast_result
                )
            
            # ============================================================
            # STEP 9: Preliminary position size
            # ============================================================
            
            position_size = self._calculate_position_size(
                confidence=final_confidence,
                decision=decision_result,
                action=final_action
            )
            
            # ============================================================
            # STEP 10: Preliminary SL / TP
            # ============================================================
            
            stop_loss, take_profit = self._calculate_sl_tp(
                technical=technical_result,
                action=final_action,
                current_price=current_price
            )
            
            # ============================================================
            # STEP 11: Market scores
            # ============================================================
            
            market_scores = self._build_market_scores(
                sentiment=sentiment_result,
                technical=technical_result,
                decision=decision_result,
                forecast=forecast_result,
                consensus_score=consensus_score
            )
            
            # ============================================================
            # STEP 12: Execution reason
            # ============================================================
            
            consensus_strength = abs(consensus_score)
            agreement = self._calculate_agent_agreement(agent_votes)
            
            execution_reason = None
            if final_action == "HOLD":
                if final_confidence < 0.50:
                    execution_reason = f"Confidence too low: {final_confidence:.1%} < 50%"
                elif consensus_strength < 0.20:
                    execution_reason = f"Weak consensus: {consensus_strength:.1%}"
                elif agreement < 0.50:
                    execution_reason = f"Poor agent agreement: {agreement:.1%}"
                else:
                    execution_reason = "No clear signal from agents"
            else:
                execution_reason = f"Executing {final_action} with {final_confidence:.1%} confidence"
            
            # ============================================================
            # STEP 13: Summary
            # ============================================================
            
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
                take_profit=take_profit,
                execution_reason=execution_reason
            )
            
            # ============================================================
            # STEP 14: Build result
            # ============================================================
            
            result = OrchestratorResult(
                timestamp=datetime.now(timezone.utc),
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
                summary=summary,
                execution_reason=execution_reason
            )
            
            # ============================================================
            # STEP 15: Save history
            # ============================================================
            
            self.history.append(result)
            if len(self.history) > self.max_history:
                self.history.pop(0)
            
            logger.info("Analysis completed: %s -> %s (confidence=%.2f%%)",
                       symbol, final_action, final_confidence * 100)
            
            return result
            
        except Exception as e:
            logger.exception("Orchestrator analysis failed for %s: %s", symbol, e)
            return self._get_default_result(symbol)

    # ============================================================
    # BASE AGENTS - FULL IMPLEMENTATION
    # ============================================================
    
    async def _run_base_agents(
        self,
        symbol: str,
        market_data: Dict[str, Any]
    ) -> Tuple[Optional[SentimentResult], Optional[TechnicalResult]]:
        """
        Run Sentiment + Technical agents in parallel.
        """
        tasks = [
            asyncio.to_thread(self.sentiment_agent.analyze, symbol, market_data),
            asyncio.to_thread(self.technical_agent.analyze, symbol, market_data),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        sentiment_result = None
        technical_result = None
        
        # Sentiment
        if len(results) > 0 and not isinstance(results[0], Exception):
            sentiment_result = results[0]
        else:
            error = results[0] if results else "Unknown error"
            logger.error("Sentiment agent failed: %s", error)
            
        # Technical
        if len(results) > 1 and not isinstance(results[1], Exception):
            technical_result = results[1]
        else:
            error = results[1] if len(results) > 1 else "Unknown error"
            logger.error("Technical agent failed: %s", error)
            
        return sentiment_result, technical_result
    
    async def _run_decision(
        self,
        symbol: str,
        sentiment: Optional[SentimentResult],
        technical: Optional[TechnicalResult],
        market_data: Dict[str, Any]
    ) -> Optional[DecisionResult]:
        """Run Decision agent."""
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
            logger.error("Decision agent failed: %s", e)
            return None
    
    async def _run_forecast(
        self,
        symbol: str,
        sentiment: Optional[SentimentResult],
        technical: Optional[TechnicalResult],
        market_data: Dict[str, Any]
    ) -> Optional[ForecastResult]:
        """Run Forecast agent."""
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
            logger.error("Forecast agent failed: %s", e)
            return None
    
    async def _run_reflection(
        self,
        symbol: str,
        market_data: Dict[str, Any]
    ) -> Optional[ReflectionResult]:
        """Run Reflector agent."""
        try:
            trades = market_data.get("recent_trades", [])
            if trades is None or not isinstance(trades, list):
                trades = []
                
            result = await asyncio.to_thread(
                self.reflector_agent.analyze,
                symbol,
                trades,
                None
            )
            return result
        except Exception as e:
            logger.error("Reflector agent failed: %s", e)
            return None

    # ============================================================
    # VOTING
    # ============================================================
    
    def _perform_voting(
        self,
        sentiment: Optional[SentimentResult],
        technical: Optional[TechnicalResult],
        decision: Optional[DecisionResult],
        forecast: Optional[ForecastResult]
    ) -> Tuple[str, float]:
        """Weighted consensus dengan dynamic weights."""
        weighted_total = 0.0
        available_weight = 0.0
        agent_scores = []
        
        if sentiment is not None:
            score = self._safe_score(getattr(sentiment, "overall_score", 0.0))
            weight = self._get_agent_weight("sentiment")
            weighted_total += score * weight
            available_weight += weight
            agent_scores.append(("sentiment", score))
            
        if technical is not None:
            score = self._safe_score(getattr(technical, "overall_score", 0.0))
            weight = self._get_agent_weight("technical")
            weighted_total += score * weight
            available_weight += weight
            agent_scores.append(("technical", score))
            
        if decision is not None:
            score = self._safe_score(getattr(decision, "action_score", 0.0))
            weight = self._get_agent_weight("decision")
            weighted_total += score * weight
            available_weight += weight
            agent_scores.append(("decision", score))
            
        if forecast is not None:
            score = self._forecast_to_score(forecast)
            weight = self._get_agent_weight("forecast")
            weighted_total += score * weight
            available_weight += weight
            agent_scores.append(("forecast", score))
            
        if available_weight <= 0:
            return ("HOLD", 0.0)
            
        consensus_score = self._safe_score(weighted_total / available_weight)
        consensus_action = self._score_to_action(consensus_score)
        
        # Detect strong directional bias
        if len(agent_scores) >= 2:
            bullish = sum(1 for _, s in agent_scores if s > 0.3)
            bearish = sum(1 for _, s in agent_scores if s < -0.3)
            
            if bullish >= 2 and consensus_action == "HOLD":
                avg_bullish = sum(s for _, s in agent_scores if s > 0.3) / max(bullish, 1)
                if avg_bullish > 0.5:
                    consensus_action = "BUY"
                    consensus_score = max(consensus_score, avg_bullish * 0.7)
                    logger.info("Bullish bias detected: %d agents bullish", bullish)
                    
            elif bearish >= 2 and consensus_action == "HOLD":
                avg_bearish = sum(s for _, s in agent_scores if s < -0.3) / max(bearish, 1)
                if avg_bearish < -0.5:
                    consensus_action = "SELL"
                    consensus_score = min(consensus_score, avg_bearish * 0.7)
                    logger.info("Bearish bias detected: %d agents bearish", bearish)
        
        return (consensus_action, consensus_score)

    def _get_agent_weight(self, agent_name: str) -> float:
        """Get dynamic weight based on historical performance."""
        if not self.enable_dynamic_weights:
            return self.agent_weights.get(agent_name, 0.25)
            
        base_weight = self.agent_weights.get(agent_name, 0.25)
        performance = self.performance_history.get(agent_name, {"correct": 0, "total": 0})
        
        if performance["total"] < 10:
            return base_weight
            
        accuracy = performance["correct"] / performance["total"]
        
        if accuracy > 0.6:
            return min(base_weight * 1.5, 0.50)
        elif accuracy < 0.4:
            return max(base_weight * 0.5, 0.05)
        else:
            return base_weight

    # ============================================================
    # FINAL DECISION
    # ============================================================
    
    def _determine_final_decision(
        self,
        decision: Optional[DecisionResult],
        consensus_action: str,
        consensus_score: float,
        sentiment: Optional[SentimentResult],
        technical: Optional[TechnicalResult],
        forecast: Optional[ForecastResult]
    ) -> Tuple[str, float, float, Dict[str, float]]:
        """Enhanced final decision with confidence boosting."""
        
        # Decision data
        if decision is not None:
            decision_score = self._safe_score(getattr(decision, "action_score", 0.0))
            decision_confidence = self._safe_probability(getattr(decision, "confidence", 0.0))
        else:
            decision_score = 0.0
            decision_confidence = 0.0
            
        # Consensus
        consensus_score = self._safe_score(consensus_score)
        consensus_strength = abs(consensus_score)
        
        # Votes
        votes = self._get_agent_votes(sentiment, technical, decision, forecast)
        agreement = self._calculate_agent_agreement(votes)
        agreement_direction = self._agreement_direction(votes)
        
        # Technical and sentiment scores
        technical_score = 0.0
        if technical is not None:
            technical_score = self._safe_score(getattr(technical, "overall_score", 0.0))
            
        sentiment_score = 0.0
        if sentiment is not None:
            sentiment_score = self._safe_score(getattr(sentiment, "overall_score", 0.0))
            
        tech_sent_agree = (technical_score > 0.1 and sentiment_score > 0.1) or \
                         (technical_score < -0.1 and sentiment_score < -0.1)
        
        # Combined score
        if decision is not None:
            combined_score = (
                decision_score * 0.40 +
                consensus_score * 0.30 +
                agreement_direction * 0.20 +
                technical_score * 0.10
            )
            
            if tech_sent_agree and abs(technical_score) > 0.3:
                combined_score = self._safe_score(combined_score * 1.2)
                logger.info("Tech-Sentiment alignment detected")
                
            if agreement >= 0.75 and abs(agreement_direction) > 0.3:
                combined_score = self._safe_score(combined_score * 1.15)
                logger.info("Strong agent agreement detected")
        else:
            combined_score = consensus_score
            
        combined_score = self._safe_score(combined_score)
        final_action = self._score_to_action(combined_score)
        
        # Confidence calculation
        if decision is not None:
            raw_confidence = (
                decision_confidence * 0.40 +
                consensus_strength * 0.25 +
                agreement * 0.20 +
                abs(agreement_direction) * 0.15
            )
        else:
            raw_confidence = (
                consensus_strength * 0.50 +
                agreement * 0.30 +
                abs(agreement_direction) * 0.20
            )
            
        if final_action != "HOLD":
            if tech_sent_agree and abs(technical_score) > 0.3:
                raw_confidence *= 1.2
            if abs(agreement_direction) > 0.5:
                raw_confidence *= 1.15
            if consensus_strength > 0.3:
                raw_confidence *= 1.1
                
        final_confidence = max(0.0, min(1.0, raw_confidence))
        
        # HOLD confidence protection
        if final_action == "HOLD":
            final_confidence = min(final_confidence, 0.60)
            if agreement >= 0.75 and abs(agreement_direction) < 0.1:
                final_confidence = max(final_confidence, 0.40)
        
        confidence_components = {
            "decision_confidence": round(decision_confidence, 4),
            "consensus_strength": round(consensus_strength, 4),
            "agent_agreement": round(agreement, 4),
            "agreement_direction": round(agreement_direction, 4),
            "combined_score": round(combined_score, 4),
            "tech_sent_alignment": round(1.0 if tech_sent_agree else 0.0, 4),
        }
        
        return (final_action, final_confidence, combined_score, confidence_components)

    # ============================================================
    # POSITION SIZE
    # ============================================================
    
    def _calculate_position_size(
        self,
        confidence: float,
        decision: Optional[DecisionResult],
        action: str
    ) -> float:
        """Enhanced position sizing dengan minimum threshold."""
        if action == "HOLD":
            return 0.0
            
        confidence = self._safe_probability(confidence)
        
        if confidence < 0.50:
            return 0.0
            
        if decision is not None:
            raw_base_size = getattr(decision, "suggested_position_size", self.default_position_size)
            try:
                base_size = float(raw_base_size)
            except (TypeError, ValueError):
                base_size = self.default_position_size
        else:
            base_size = self.default_position_size
            
        if base_size < 0:
            base_size = 0.0
            
        size = base_size * ((confidence - 0.50) / 0.50)
        size = max(self.min_position_size, min(self.max_position_size, size))
        
        return size

    # ============================================================
    # SL / TP
    # ============================================================
    
    def _calculate_sl_tp(
        self,
        technical: Optional[TechnicalResult],
        action: str,
        current_price: float
    ) -> Tuple[Optional[float], Optional[float]]:
        """Calculate preliminary stop loss and take profit."""
        if technical is None or current_price <= 0 or action == "HOLD":
            return None, None
            
        support_levels = self._extract_price_levels(
            getattr(technical, "support_levels", None)
        )
        resistance_levels = self._extract_price_levels(
            getattr(technical, "resistance_levels", None)
        )
        
        stop_loss = None
        take_profit = None
        
        if action in {"BUY", "STRONG_BUY"}:
            supports_below = [l for l in support_levels if l < current_price]
            resistances_above = [l for l in resistance_levels if l > current_price]
            
            if supports_below:
                stop_loss = max(supports_below) * 0.99
            else:
                stop_loss = current_price * 0.95
                
            if resistances_above:
                take_profit = min(resistances_above) * 0.99
            else:
                take_profit = current_price * 1.10
                
        elif action in {"SELL", "STRONG_SELL"}:
            resistances_above = [l for l in resistance_levels if l > current_price]
            supports_below = [l for l in support_levels if l < current_price]
            
            if resistances_above:
                stop_loss = min(resistances_above) * 1.01
            else:
                stop_loss = current_price * 1.05
                
            if supports_below:
                take_profit = max(supports_below) * 1.01
            else:
                take_profit = current_price * 0.90
                
        return (stop_loss, take_profit)

    # ============================================================
    # FORECAST -> SCORE
    # ============================================================
    
    def _forecast_to_score(self, forecast: ForecastResult) -> float:
        """Convert ForecastResult to score -1 to +1."""
        if forecast is None:
            return 0.0
            
        # Trend component
        trend_score = 0.0
        trend = str(getattr(forecast, "primary_trend", "")).upper()
        if trend == "BULLISH":
            trend_score = 1.0
        elif trend == "BEARISH":
            trend_score = -1.0
            
        # Probability component
        probability_score = 0.0
        next_move = getattr(forecast, "next_move_probability", {})
        if isinstance(next_move, dict):
            up = self._safe_probability(next_move.get("UP", 0.0))
            down = self._safe_probability(next_move.get("DOWN", 0.0))
            probability_score = up - down
            
        # Price prediction component
        prediction_score = 0.0
        try:
            short_term = getattr(forecast, "short_term", None)
            if short_term is not None:
                predicted_price = float(getattr(short_term, "predicted_price", 0.0))
                current_price = float(getattr(forecast, "current_price", 0.0))
                if current_price > 0:
                    price_change = (predicted_price - current_price) / current_price
                    prediction_score = max(-1.0, min(1.0, price_change / 0.05))
        except (AttributeError, TypeError, ValueError, ZeroDivisionError):
            prediction_score = 0.0
            
        score = trend_score * 0.40 + probability_score * 0.30 + prediction_score * 0.30
        return self._safe_score(score)

    # ============================================================
    # AGENT VOTES
    # ============================================================
    
    def _get_agent_votes(
        self,
        sentiment: Optional[SentimentResult],
        technical: Optional[TechnicalResult],
        decision: Optional[DecisionResult],
        forecast: Optional[ForecastResult]
    ) -> Dict[str, str]:
        """Get votes from all agents."""
        votes = {}
        
        if sentiment is not None:
            votes["sentiment"] = self._score_to_action(
                self._safe_score(getattr(sentiment, "overall_score", 0.0))
            )
            
        if technical is not None:
            votes["technical"] = self._score_to_action(
                self._safe_score(getattr(technical, "overall_score", 0.0))
            )
            
        if decision is not None:
            decision_action = str(getattr(decision, "action", "HOLD")).upper()
            valid_actions = {"STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"}
            if decision_action not in valid_actions:
                decision_action = self._score_to_action(
                    getattr(decision, "action_score", 0.0)
                )
            votes["decision"] = decision_action
            
        if forecast is not None:
            votes["forecast"] = self._score_to_action(self._forecast_to_score(forecast))
            
        return votes

    # ============================================================
    # AGREEMENT
    # ============================================================
    
    def _calculate_agent_agreement(self, agent_votes: Dict[str, str]) -> float:
        """Calculate agreement level among agents."""
        if not agent_votes:
            return 0.0
            
        actions = []
        for vote in agent_votes.values():
            if vote is None:
                continue
            action = str(vote).upper().strip()
            if action in ("BUY", "SELL", "HOLD"):
                actions.append(action)
                
        if not actions:
            return 0.0
            
        counts = {
            "BUY": actions.count("BUY"),
            "SELL": actions.count("SELL"),
            "HOLD": actions.count("HOLD"),
        }
        
        majority_count = max(counts.values())
        return round(majority_count / len(actions), 4)

    def _agreement_direction(self, votes: Dict[str, str]) -> float:
        """Calculate directional score from agent votes."""
        if not votes:
            return 0.0
            
        scores = [self._action_to_score(action) for action in votes.values()]
        if not scores:
            return 0.0
            
        return self._safe_score(sum(scores) / len(scores))

    # ============================================================
    # SCORE -> ACTION / ACTION -> SCORE
    # ============================================================
    
    def _score_to_action(self, score: float) -> str:
        """Convert score to action."""
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

    def _action_to_score(self, action: str) -> float:
        """Convert action to score."""
        mapping = {
            "STRONG_BUY": 1.0,
            "BUY": 0.5,
            "HOLD": 0.0,
            "SELL": -0.5,
            "STRONG_SELL": -1.0,
        }
        return mapping.get(str(action).upper(), 0.0)

    # ============================================================
    # HELPER METHODS
    # ============================================================
    
    def _safe_score(self, value: Any) -> float:
        """Safely convert value to score between -1 and 1."""
        try:
            value = float(value)
        except (TypeError, ValueError):
            return 0.0
        if value != value:  # NaN
            return 0.0
        if value == float("inf"):
            return 1.0
        if value == float("-inf"):
            return -1.0
        return max(-1.0, min(1.0, value))

    def _safe_probability(self, value: Any) -> float:
        """Safely convert value to probability between 0 and 1."""
        try:
            value = float(value)
        except (TypeError, ValueError):
            return 0.0
        if value != value:  # NaN
            return 0.0
        return max(0.0, min(1.0, value))

    def _extract_price_levels(self, levels: Any) -> List[float]:
        """Extract and clean price levels."""
        if levels is None:
            return []
        if not isinstance(levels, (list, tuple, set)):
            return []
        clean_levels = []
        for level in levels:
            try:
                value = float(level)
            except (TypeError, ValueError):
                continue
            if value > 0:
                clean_levels.append(value)
        return sorted(set(clean_levels))

    def _get_current_price(
        self,
        market_data: Dict[str, Any],
        technical: Optional[TechnicalResult],
        forecast: Optional[ForecastResult]
    ) -> float:
        """Get current price from various sources."""
        # From market data
        if market_data:
            for key in ["current_price", "price", "last_price", "close"]:
                value = market_data.get(key)
                if value is not None:
                    try:
                        price = float(value)
                        if price > 0:
                            return price
                    except (TypeError, ValueError):
                        continue
                        
        # From technical
        if technical is not None:
            try:
                price = float(getattr(technical, "current_price", 0.0))
                if price > 0:
                    return price
            except (TypeError, ValueError):
                pass
                
        # From forecast
        if forecast is not None:
            try:
                price = float(getattr(forecast, "current_price", 0.0))
                if price > 0:
                    return price
            except (TypeError, ValueError):
                pass
                
        return 0.0

    def _build_market_scores(
        self,
        sentiment: Optional[SentimentResult],
        technical: Optional[TechnicalResult],
        decision: Optional[DecisionResult],
        forecast: Optional[ForecastResult],
        consensus_score: float
    ) -> Dict[str, float]:
        """Build market scores dictionary."""
        scores = {}
        
        if sentiment is not None:
            scores["sentiment"] = round(
                self._safe_score(getattr(sentiment, "overall_score", 0.0)), 4
            )
            
        if technical is not None:
            scores["technical"] = round(
                self._safe_score(getattr(technical, "overall_score", 0.0)), 4
            )
            
        if decision is not None:
            scores["decision"] = round(
                self._safe_score(getattr(decision, "action_score", 0.0)), 4
            )
            
        if forecast is not None:
            scores["forecast"] = round(self._forecast_to_score(forecast), 4)
            
        scores["consensus"] = round(self._safe_score(consensus_score), 4)
        
        return scores

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
        take_profit: Optional[float],
        execution_reason: Optional[str] = None
    ) -> str:
        """Generate summary string."""
        lines = [
            "=== ORCHESTRATOR SUMMARY ===",
            f"Symbol: {symbol}",
            f"Current Price: {current_price:.8f}",
            f"Final Action: {final_action}",
            f"Confidence: {final_confidence:.2%}",
            f"Preliminary Position Size: {position_size:.2%}",
            f"Consensus: {consensus_action}",
            f"Consensus Score: {consensus_score:.4f}",
        ]
        
        if execution_reason:
            lines.append(f"Execution Reason: {execution_reason}")
            
        if stop_loss is not None:
            lines.append(f"Preliminary Stop Loss: {stop_loss:.8f}")
        else:
            lines.append("Preliminary Stop Loss: N/A")
            
        if take_profit is not None:
            lines.append(f"Preliminary Take Profit: {take_profit:.8f}")
        else:
            lines.append("Preliminary Take Profit: N/A")
            
        lines.append("")
        lines.append("Agent Votes:")
        if agent_votes:
            for agent, vote in agent_votes.items():
                lines.append(f"  {agent}: {vote}")
        else:
            lines.append("  No valid agent votes")
            
        lines.append("")
        lines.append("NOTE: Position size and SL/TP are preliminary only.")
        lines.append("Risk Engine must validate them before execution.")
        
        return "\n".join(lines)

    def _get_default_result(self, symbol: str) -> OrchestratorResult:
        """Return default result on error."""
        timestamp = datetime.now(timezone.utc)
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
                "tech_sent_alignment": 0.0,
            },
            market_scores={},
            summary=summary,
            execution_reason="Error during analysis"
        )

    def update_agent_performance(self, agent_name: str, was_correct: bool):
        """Update performance history for dynamic weights."""
        if agent_name not in self.performance_history:
            self.performance_history[agent_name] = {"correct": 0, "total": 0}
            
        perf = self.performance_history[agent_name]
        perf["total"] += 1
        if was_correct:
            perf["correct"] += 1
            
        accuracy = perf["correct"] / perf["total"] if perf["total"] > 0 else 0
        logger.debug("Agent %s performance: %.2f%% (%d/%d)",
                    agent_name, accuracy * 100, perf["correct"], perf["total"])

    def get_history(self, n: int = 10) -> List[OrchestratorResult]:
        """Get recent history."""
        if n <= 0:
            return []
        return self.history[-n:]
