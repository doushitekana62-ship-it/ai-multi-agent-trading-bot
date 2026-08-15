"""
Orchestrator - AI Decision Coordination Layer
Dengan perbaikan untuk menangani sinyal mixed dan meningkatkan confidence
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple

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
    execution_reason: Optional[str] = None  # NEW: Alasan eksekusi/ditolak


class Orchestrator:
    """Central coordinator untuk seluruh AI agents."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        
        # Initialize agents
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
        
        # ============================================================
        # PERBAIKAN 1: Agent Weights - Lebih fleksibel
        # ============================================================
        self.agent_weights = {
            "sentiment": 0.20,    # Turunkan dari 0.25
            "technical": 0.35,    # Naikkan dari 0.30
            "decision": 0.35,     # Naikkan dari 0.30
            "forecast": 0.10,     # Turunkan dari 0.15
        }
        
        # ============================================================
        # PERBAIKAN 2: Dynamic Weight Adjustment
        # ============================================================
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
        
        logger.info("Orchestrator initialized successfully with dynamic weights=%s", 
                   self.enable_dynamic_weights)

    # ============================================================
    # PERBAIKAN 3: Enhanced Voting dengan Directional Bias
    # ============================================================
    
    def _perform_voting(
        self,
        sentiment: Optional[SentimentResult],
        technical: Optional[TechnicalResult],
        decision: Optional[DecisionResult],
        forecast: Optional[ForecastResult]
    ) -> Tuple[str, float]:
        """
        Weighted consensus dengan dynamic weights dan directional bias detection.
        """
        weighted_total = 0.0
        available_weight = 0.0
        agent_scores = []
        
        # Collect all scores with weights
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
            
        # Normalize
        consensus_score = weighted_total / available_weight
        consensus_score = self._safe_score(consensus_score)
        
        # ============================================================
        # PERBAIKAN 4: Detect Strong Directional Bias
        # ============================================================
        consensus_action = self._score_to_action(consensus_score)
        
        # Check if there's a strong directional bias despite consensus
        if len(agent_scores) >= 2:
            # Count agents on each side
            bullish = sum(1 for _, s in agent_scores if s > 0.3)
            bearish = sum(1 for _, s in agent_scores if s < -0.3)
            neutral = len(agent_scores) - bullish - bearish
            
            # If 2+ agents strongly agree on direction
            if bullish >= 2 and consensus_action == "HOLD":
                # Override to BUY if there's bullish bias
                avg_bullish = sum(s for _, s in agent_scores if s > 0.3) / max(bullish, 1)
                if avg_bullish > 0.5:
                    consensus_action = "BUY"
                    consensus_score = max(consensus_score, avg_bullish * 0.7)
                    logger.info("Bullish bias detected: %d agents bullish, avg=%.3f", 
                               bullish, avg_bullish)
                    
            elif bearish >= 2 and consensus_action == "HOLD":
                avg_bearish = sum(s for _, s in agent_scores if s < -0.3) / max(bearish, 1)
                if avg_bearish < -0.5:
                    consensus_action = "SELL"
                    consensus_score = min(consensus_score, avg_bearish * 0.7)
                    logger.info("Bearish bias detected: %d agents bearish, avg=%.3f", 
                               bearish, avg_bearish)
        
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
        
        # Boost weight for accurate agents, reduce for poor performers
        if accuracy > 0.6:
            return min(base_weight * 1.5, 0.50)
        elif accuracy < 0.4:
            return max(base_weight * 0.5, 0.05)
        else:
            return base_weight

    # ============================================================
    # PERBAIKAN 5: Enhanced Final Decision dengan Confidence Boost
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
        """
        Enhanced final decision with confidence boosting for clear signals.
        """
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
        votes = self._get_agent_votes(
            sentiment=sentiment,
            technical=technical,
            decision=decision,
            forecast=forecast
        )
        
        agreement = self._calculate_agent_agreement(votes)
        agreement_direction = self._agreement_direction(votes)
        
        # ============================================================
        # PERBAIKAN 6: More Sophisticated Combined Score
        # ============================================================
        
        # Check for strong technical signal
        technical_score = 0.0
        if technical is not None:
            technical_score = self._safe_score(getattr(technical, "overall_score", 0.0))
            
        # Check for strong sentiment signal
        sentiment_score = 0.0
        if sentiment is not None:
            sentiment_score = self._safe_score(getattr(sentiment, "overall_score", 0.0))
            
        # Detect alignment between technical and sentiment
        tech_sent_alignment = abs(technical_score - sentiment_score) < 0.3
        tech_sent_agree = (technical_score > 0.1 and sentiment_score > 0.1) or \
                         (technical_score < -0.1 and sentiment_score < -0.1)
        
        if decision is not None:
            # Base combined score
            combined_score = (
                decision_score * 0.40 +
                consensus_score * 0.30 +
                agreement_direction * 0.20 +
                (technical_score * 0.10)
            )
            
            # ============================================================
            # PERBAIKAN 7: Confidence Boost for Strong Signals
            # ============================================================
            
            # Boost if technical and sentiment agree
            if tech_sent_agree and abs(technical_score) > 0.3:
                combined_score = combined_score * 1.2
                combined_score = self._safe_score(combined_score)
                logger.info("Tech-Sentiment alignment detected: tech=%.3f, sent=%.3f", 
                           technical_score, sentiment_score)
                
            # Boost if there's strong agreement (3+ agents same direction)
            if agreement >= 0.75 and abs(agreement_direction) > 0.3:
                combined_score = combined_score * 1.15
                combined_score = self._safe_score(combined_score)
                logger.info("Strong agent agreement detected: agreement=%.2f", agreement)
                
        else:
            combined_score = consensus_score
            
        combined_score = self._safe_score(combined_score)
        
        # Final action
        final_action = self._score_to_action(combined_score)
        
        # ============================================================
        # PERBAIKAN 8: Enhanced Confidence Calculation
        # ============================================================
        
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
            
        # Confidence boost for strong signals
        if final_action != "HOLD":
            # Boost if tech and sentiment align
            if tech_sent_agree and abs(technical_score) > 0.3:
                raw_confidence *= 1.2
                
            # Boost if there's strong directional bias
            if abs(agreement_direction) > 0.5:
                raw_confidence *= 1.15
                
            # Boost if consensus is strong
            if consensus_strength > 0.3:
                raw_confidence *= 1.1
                
        final_confidence = max(0.0, min(1.0, raw_confidence))
        
        # ============================================================
        # PERBAIKAN 9: HOLD Confidence Protection - Kurangi Penalti
        # ============================================================
        if final_action == "HOLD":
            # Kurangi penalti dari 0.50 menjadi 0.60
            final_confidence = min(final_confidence, 0.60)
            
            # Tapi jika ada agreement yang kuat, beri confidence lebih
            if agreement >= 0.75 and abs(agreement_direction) < 0.1:
                final_confidence = max(final_confidence, 0.40)
        
        # Confidence components
        confidence_components = {
            "decision_confidence": round(decision_confidence, 4),
            "consensus_strength": round(consensus_strength, 4),
            "agent_agreement": round(agreement, 4),
            "agreement_direction": round(agreement_direction, 4),
            "combined_score": round(combined_score, 4),
            "tech_sent_alignment": round(1.0 if tech_sent_agree else 0.0, 4),  # NEW
        }
        
        return (final_action, final_confidence, combined_score, confidence_components)

    # ============================================================
    # PERBAIKAN 10: Enhanced Position Size
    # ============================================================
    
    def _calculate_position_size(
        self,
        confidence: float,
        decision: Optional[DecisionResult],
        action: str
    ) -> float:
        """
        Enhanced position sizing dengan minimum threshold.
        """
        if action == "HOLD":
            return 0.0
            
        confidence = self._safe_probability(confidence)
        
        # Jika confidence di bawah 50%, tidak ada posisi
        if confidence < 0.50:
            return 0.0
            
        if decision is not None:
            raw_base_size = getattr(
                decision,
                "suggested_position_size",
                self.default_position_size
            )
            try:
                base_size = float(raw_base_size)
            except (TypeError, ValueError):
                base_size = self.default_position_size
        else:
            base_size = self.default_position_size
            
        if base_size < 0:
            base_size = 0.0
            
        # Scale position by confidence
        size = base_size * ((confidence - 0.50) / 0.50)  # 0.5 = 0%, 1.0 = 100%
        size = max(self.min_position_size, min(self.max_position_size, size))
        
        return size

    # ============================================================
    # PERBAIKAN 11: Enhanced Summary dengan Execution Reason
    # ============================================================
    
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
        execution_reason: Optional[str] = None  # NEW
    ) -> str:
        lines = []
        lines.append("=== ORCHESTRATOR SUMMARY ===")
        lines.append(f"Symbol: {symbol}")
        lines.append(f"Current Price: {current_price:.8f}")
        lines.append(f"Final Action: {final_action}")
        lines.append(f"Confidence: {final_confidence:.2%}")
        lines.append(f"Preliminary Position Size: {position_size:.2%}")
        lines.append(f"Consensus: {consensus_action}")
        lines.append(f"Consensus Score: {consensus_score:.4f}")
        
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

    # ============================================================
    # PERBAIKAN 12: Track Performance untuk Dynamic Weights
    # ============================================================
    
    def update_agent_performance(self, agent_name: str, was_correct: bool):
        """Update performance history for dynamic weight adjustment."""
        if agent_name not in self.performance_history:
            self.performance_history[agent_name] = {"correct": 0, "total": 0}
            
        perf = self.performance_history[agent_name]
        perf["total"] += 1
        if was_correct:
            perf["correct"] += 1
            
        # Log performance changes
        accuracy = perf["correct"] / perf["total"] if perf["total"] > 0 else 0
        logger.debug("Agent %s performance: %.2f%% (%d/%d)", 
                    agent_name, accuracy * 100, perf["correct"], perf["total"])
    
    # ============================================================
    # PERBAIKAN 13: Public Analyze dengan Execution Reason
    # ============================================================
    
    async def analyze(
        self,
        symbol: str,
        market_data: Optional[Dict[str, Any]] = None
    ) -> OrchestratorResult:
        """
        Menjalankan seluruh pipeline analisis dengan execution reason.
        """
        logger.info("Starting analysis for %s", symbol)
        market_data = market_data.copy() if isinstance(market_data, dict) else {}
        
        try:
            # ... (kode yang sama seperti sebelumnya) ...
            # Saya sertakan bagian yang dimodifikasi
            
            # STEP 8: Final decision dengan execution reason
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
            
            # ============================================================
            # PERBAIKAN 14: Determine Execution Reason
            # ============================================================
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
                
            # ... (lanjutkan dengan step selanjutnya) ...
            
        except Exception as e:
            logger.exception("Orchestrator analysis failed for %s: %s", symbol, e)
            return self._get_default_result(symbol)

    # ============================================================
    # Helper Methods (tanpa perubahan signifikan)
    # ============================================================
    
    def _safe_score(self, value: Any) -> float:
        try:
            value = float(value)
        except (TypeError, ValueError):
            return 0.0
        if value != value:
            return 0.0
        if value == float("inf"):
            return 1.0
        if value == float("-inf"):
            return -1.0
        return max(-1.0, min(1.0, value))
    
    def _safe_probability(self, value: Any) -> float:
        try:
            value = float(value)
        except (TypeError, ValueError):
            return 0.0
        if value != value:
            return 0.0
        return max(0.0, min(1.0, value))
    
    def _score_to_action(self, score: float) -> str:
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
    
    def _forecast_to_score(self, forecast: ForecastResult) -> float:
        # ... (sama seperti sebelumnya, dengan perbaikan untuk short_term) ...
        pass
    
    def _get_agent_votes(self, sentiment, technical, decision, forecast) -> Dict[str, str]:
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
            votes["forecast"] = self._score_to_action(
                self._forecast_to_score(forecast)
            )
        return votes
    
    def _calculate_agent_agreement(self, agent_votes: Dict[str, str]) -> float:
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
        counts = {"BUY": actions.count("BUY"), "SELL": actions.count("SELL"), "HOLD": actions.count("HOLD")}
        majority_count = max(counts.values())
        agreement = majority_count / len(actions)
        return round(agreement, 4)
    
    def _agreement_direction(self, votes: Dict[str, str]) -> float:
        if not votes:
            return 0.0
        scores = [self._action_to_score(action) for action in votes.values()]
        if not scores:
            return 0.0
        return self._safe_score(sum(scores) / len(scores))
    
    def _action_to_score(self, action: str) -> float:
        mapping = {"STRONG_BUY": 1.0, "BUY": 0.5, "HOLD": 0.0, "SELL": -0.5, "STRONG_SELL": -1.0}
        return mapping.get(str(action).upper(), 0.0)
    
    def _extract_price_levels(self, levels: Any) -> List[float]:
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
    
    def _get_current_price(self, market_data, technical, forecast) -> float:
        # ... (sama seperti sebelumnya) ...
        pass
    
    def _build_market_scores(self, sentiment, technical, decision, forecast, consensus_score) -> Dict[str, float]:
        # ... (sama seperti sebelumnya) ...
        pass
    
    def _calculate_sl_tp(self, technical, action, current_price):
        # ... (sama seperti sebelumnya) ...
        pass
    
    def _get_default_result(self, symbol) -> OrchestratorResult:
        # ... (sama seperti sebelumnya) ...
        pass
    
    def get_history(self, n: int = 10) -> List[OrchestratorResult]:
        if n <= 0:
            return []
        return self.history[-n:]
