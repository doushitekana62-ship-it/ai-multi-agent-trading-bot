"""
Orchestrator - AI Decision Coordination Layer
Dengan peningkatan transparansi dan formula consensus yang lebih baik
"""

import asyncio
import logging
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple

from agents.agent_sentiment import SentimentAgent, SentimentResult
from agents.agent_technical import TechnicalAgent, TechnicalResult
from agents.agent_decision import DecisionAgent, DecisionResult
from agents.agent_reflector import ReflectorAgent, ReflectionResult, TradeRecord
from agents.agent_forecast import ForecastAgent, ForecastResult

logger = logging.getLogger(__name__)


@dataclass
class ConsensusDebug:
    """Structured debug data untuk consensus process"""
    timestamp: datetime
    symbol: str
    
    # Agent votes
    agent_votes: Dict[str, str]
    agent_scores: Dict[str, float]
    agent_weights: Dict[str, float]
    
    # Weighted consensus
    weighted_total: float
    available_weight: float
    consensus_score: float
    consensus_action: str
    
    # Agreement analysis
    agent_agreement: float
    agreement_direction: float
    directional_bias: str
    conflict_detected: bool
    
    # Confidence breakdown
    confidence_components: Dict[str, float]
    final_confidence: float
    
    # Decision
    final_action: str
    decision_reasoning: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "agent_votes": self.agent_votes,
            "agent_scores": self.agent_scores,
            "agent_weights": self.agent_weights,
            "weighted_total": self.weighted_total,
            "available_weight": self.available_weight,
            "consensus_score": self.consensus_score,
            "consensus_action": self.consensus_action,
            "agent_agreement": self.agent_agreement,
            "agreement_direction": self.agreement_direction,
            "directional_bias": self.directional_bias,
            "conflict_detected": self.conflict_detected,
            "confidence_components": self.confidence_components,
            "final_confidence": self.final_confidence,
            "final_action": self.final_action,
            "decision_reasoning": self.decision_reasoning
        }


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
    consensus_debug: Optional[ConsensusDebug] = None  # NEW: Debug info


class Orchestrator:
    """Central coordinator untuk seluruh AI agents dengan consensus transparency."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        
        # ============================================================
        # INITIALIZE AGENTS
        # ============================================================
        
        self.sentiment_agent = SentimentAgent()
        self.technical_agent = TechnicalAgent()
        self.decision_agent = DecisionAgent()
        self.reflector_agent = ReflectorAgent()
        self.forecast_agent = ForecastAgent()
        
        # ============================================================
        # VOTING THRESHOLDS
        # ============================================================
        
        self.voting_thresholds = {
            "strong_buy": 0.70,
            "buy": 0.30,
            "sell": -0.30,
            "strong_sell": -0.70,
        }
        
        # ============================================================
        # AGENT WEIGHTS - DIOPTIMALKAN
        # ============================================================
        # Total = 1.0
        # - Technical: bobot tertinggi karena lebih objektif
        # - Decision: kedua tertinggi karena menggabungkan berbagai faktor
        # - Sentiment: ketiga, sebagai konfirmasi
        # - Forecast: terendah, karena bersifat prediktif
        # - Reflector: TIDAK dimasukkan voting (hanya untuk refleksi historis)
        # ============================================================
        
        self.agent_weights = {
            "sentiment": 0.20,
            "technical": 0.35,
            "decision": 0.30,
            "forecast": 0.15,
        }
        
        # ============================================================
        # QUALITY SCORES - untuk menimbang kualitas sinyal
        # ============================================================
        # Agent dengan confidence tinggi mendapat bobot lebih
        # ============================================================
        
        self.quality_weights = {
            "sentiment": 1.0,
            "technical": 1.0,
            "decision": 1.0,
            "forecast": 1.0,
        }
        
        # ============================================================
        # DYNAMIC WEIGHTS
        # ============================================================
        
        self.enable_dynamic_weights = config.get("enable_dynamic_weights", True)
        self.performance_history = {
            "sentiment": {"correct": 0, "total": 0, "avg_score": 0.0, "total_score": 0.0},
            "technical": {"correct": 0, "total": 0, "avg_score": 0.0, "total_score": 0.0},
            "decision": {"correct": 0, "total": 0, "avg_score": 0.0, "total_score": 0.0},
            "forecast": {"correct": 0, "total": 0, "avg_score": 0.0, "total_score": 0.0},
        }
        
        # ============================================================
        # POSITION SIZING
        # ============================================================
        
        self.max_position_size = float(config.get("max_position_size", 0.20))
        self.default_position_size = float(config.get("default_position_size", 0.05))
        self.min_position_size = float(config.get("min_position_size", 0.01))
        
        # ============================================================
        # CONFIDENCE THRESHOLDS
        # ============================================================
        
        self.min_confidence_threshold = float(config.get("min_confidence", 0.50))
        self.high_confidence_threshold = float(config.get("high_confidence", 0.70))
        
        # ============================================================
        # HISTORY
        # ============================================================
        
        self.history: List[OrchestratorResult] = []
        self.max_history = int(config.get("max_history", 100))
        self.debug_enabled = config.get("debug_enabled", True)
        
        logger.info("Orchestrator initialized with optimized weights: %s", self.agent_weights)

    # ============================================================
    # PUBLIC ANALYZE
    # ============================================================
    
    async def analyze(
        self,
        symbol: str,
        market_data: Optional[Dict[str, Any]] = None
    ) -> OrchestratorResult:
        """
        Menjalankan seluruh pipeline analisis dengan consensus transparency.
        """
        logger.info("Starting analysis for %s", symbol)
        market_data = market_data.copy() if isinstance(market_data, dict) else {}
        
        try:
            # ============================================================
            # STEP 1-4: RUN AGENTS
            # ============================================================
            
            sentiment_result, technical_result = await self._run_base_agents(symbol, market_data)
            decision_result = await self._run_decision(symbol, sentiment_result, technical_result, market_data)
            forecast_result = await self._run_forecast(symbol, sentiment_result, technical_result, market_data)
            reflection_result = await self._run_reflection(symbol, market_data)
            
            # ============================================================
            # STEP 5: CURRENT PRICE
            # ============================================================
            
            current_price = self._get_current_price(market_data, technical_result, forecast_result)
            
            # ============================================================
            # STEP 6: WEIGHTED CONSENSUS DENGAN DEBUG
            # ============================================================
            
            consensus_action, consensus_score, consensus_debug = await self._perform_consensus_with_debug(
                symbol=symbol,
                sentiment=sentiment_result,
                technical=technical_result,
                decision=decision_result,
                forecast=forecast_result
            )
            
            # ============================================================
            # STEP 7: AGENT VOTES
            # ============================================================
            
            agent_votes = self._get_agent_votes(
                sentiment=sentiment_result,
                technical=technical_result,
                decision=decision_result,
                forecast=forecast_result
            )
            
            # ============================================================
            # STEP 8: FINAL DECISION
            # ============================================================
            
            final_action, final_confidence, decision_score, confidence_components = \
                self._determine_final_decision_with_reasoning(
                    decision=decision_result,
                    consensus_action=consensus_action,
                    consensus_score=consensus_score,
                    sentiment=sentiment_result,
                    technical=technical_result,
                    forecast=forecast_result,
                    agent_votes=agent_votes,
                    consensus_debug=consensus_debug
                )
            
            # ============================================================
            # STEP 9: POSITION SIZE
            # ============================================================
            
            position_size = self._calculate_position_size(
                confidence=final_confidence,
                decision=decision_result,
                action=final_action
            )
            
            # ============================================================
            # STEP 10: SL / TP
            # ============================================================
            
            stop_loss, take_profit = self._calculate_sl_tp(
                technical=technical_result,
                action=final_action,
                current_price=current_price
            )
            
            # ============================================================
            # STEP 11: MARKET SCORES
            # ============================================================
            
            market_scores = self._build_market_scores(
                sentiment=sentiment_result,
                technical=technical_result,
                decision=decision_result,
                forecast=forecast_result,
                consensus_score=consensus_score
            )
            
            # ============================================================
            # STEP 12: EXECUTION REASON
            # ============================================================
            
            execution_reason = self._build_execution_reason(
                final_action=final_action,
                final_confidence=final_confidence,
                consensus_score=consensus_score,
                consensus_debug=consensus_debug
            )
            
            # ============================================================
            # STEP 13: SUMMARY
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
                execution_reason=execution_reason,
                consensus_debug=consensus_debug
            )
            
            # ============================================================
            # STEP 14: BUILD RESULT
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
                execution_reason=execution_reason,
                consensus_debug=consensus_debug if self.debug_enabled else None
            )
            
            # ============================================================
            # STEP 15: SAVE HISTORY
            # ============================================================
            
            self.history.append(result)
            if len(self.history) > self.max_history:
                self.history.pop(0)
            
            # ============================================================
            # STEP 16: LOG CONSENSUS DEBUG
            # ============================================================
            
            if self.debug_enabled and consensus_debug:
                self._log_consensus_debug(consensus_debug)
            
            logger.info("Analysis completed: %s -> %s (confidence=%.2f%%)",
                       symbol, final_action, final_confidence * 100)
            
            return result
            
        except Exception as e:
            logger.exception("Orchestrator analysis failed for %s: %s", symbol, e)
            return self._get_default_result(symbol)

    # ============================================================
    # CONSENSUS WITH DEBUG - CORE IMPROVEMENT
    # ============================================================
    
    async def _perform_consensus_with_debug(
        self,
        symbol: str,
        sentiment: Optional[SentimentResult],
        technical: Optional[TechnicalResult],
        decision: Optional[DecisionResult],
        forecast: Optional[ForecastResult]
    ) -> Tuple[str, float, ConsensusDebug]:
        """
        Perform weighted consensus dengan detailed debug.
        """
        # ============================================================
        # COLLECT AGENT SCORES WITH QUALITY ADJUSTMENT
        # ============================================================
        
        agent_scores = {}
        agent_votes = {}
        agent_weights = {}
        weighted_total = 0.0
        available_weight = 0.0
        
        # Sentiment
        if sentiment is not None:
            raw_score = self._safe_score(getattr(sentiment, "overall_score", 0.0))
            # Quality adjustment based on confidence
            confidence = self._safe_probability(getattr(sentiment, "confidence", 0.5))
            quality_factor = 0.5 + (confidence * 0.5)  # 0.5 - 1.0
            score = raw_score * quality_factor
            
            agent_scores["sentiment"] = score
            agent_votes["sentiment"] = self._score_to_action(raw_score)
            
            weight = self._get_agent_weight_with_quality("sentiment", confidence)
            agent_weights["sentiment"] = weight
            
            weighted_total += score * weight
            available_weight += weight
            
            logger.debug("Sentiment: raw=%.4f, conf=%.2f, quality=%.2f, adjusted=%.4f, weight=%.4f",
                        raw_score, confidence, quality_factor, score, weight)
        
        # Technical
        if technical is not None:
            raw_score = self._safe_score(getattr(technical, "overall_score", 0.0))
            # Quality adjustment based on signal strength and confidence
            confidence = self._safe_probability(getattr(technical, "confidence", 0.5))
            quality_factor = 0.5 + (confidence * 0.5)
            score = raw_score * quality_factor
            
            agent_scores["technical"] = score
            agent_votes["technical"] = self._score_to_action(raw_score)
            
            weight = self._get_agent_weight_with_quality("technical", confidence)
            agent_weights["technical"] = weight
            
            weighted_total += score * weight
            available_weight += weight
            
            logger.debug("Technical: raw=%.4f, conf=%.2f, quality=%.2f, adjusted=%.4f, weight=%.4f",
                        raw_score, confidence, quality_factor, score, weight)
        
        # Decision
        if decision is not None:
            raw_score = self._safe_score(getattr(decision, "action_score", 0.0))
            confidence = self._safe_probability(getattr(decision, "confidence", 0.5))
            quality_factor = 0.5 + (confidence * 0.5)
            score = raw_score * quality_factor
            
            agent_scores["decision"] = score
            agent_votes["decision"] = self._score_to_action(raw_score)
            
            weight = self._get_agent_weight_with_quality("decision", confidence)
            agent_weights["decision"] = weight
            
            weighted_total += score * weight
            available_weight += weight
            
            logger.debug("Decision: raw=%.4f, conf=%.2f, quality=%.2f, adjusted=%.4f, weight=%.4f",
                        raw_score, confidence, quality_factor, score, weight)
        
        # Forecast
        if forecast is not None:
            raw_score = self._forecast_to_score(forecast)
            confidence = self._safe_probability(getattr(forecast, "confidence", 0.5))
            quality_factor = 0.5 + (confidence * 0.5)
            score = raw_score * quality_factor
            
            agent_scores["forecast"] = score
            agent_votes["forecast"] = self._score_to_action(raw_score)
            
            weight = self._get_agent_weight_with_quality("forecast", confidence)
            agent_weights["forecast"] = weight
            
            weighted_total += score * weight
            available_weight += weight
            
            logger.debug("Forecast: raw=%.4f, conf=%.2f, quality=%.2f, adjusted=%.4f, weight=%.4f",
                        raw_score, confidence, quality_factor, score, weight)
        
        # ============================================================
        # CALCULATE CONSENSUS
        # ============================================================
        
        if available_weight <= 0:
            consensus_score = 0.0
            consensus_action = "HOLD"
        else:
            consensus_score = self._safe_score(weighted_total / available_weight)
            consensus_action = self._score_to_action(consensus_score)
        
        # ============================================================
        # CALCULATE AGREEMENT
        # ============================================================
        
        agreement = self._calculate_agent_agreement(agent_votes)
        agreement_direction = self._agreement_direction(agent_votes)
        
        # ============================================================
        # DETECT CONFLICT
        # ============================================================
        
        actions = list(agent_votes.values())
        unique_actions = set(actions)
        conflict_detected = len(unique_actions) > 1 and "HOLD" in unique_actions
        
        # Detect directional bias
        directional_bias = "NEUTRAL"
        if consensus_score > 0.2:
            directional_bias = "BULLISH"
        elif consensus_score < -0.2:
            directional_bias = "BEARISH"
        
        # ============================================================
        # BUILD DEBUG
        # ============================================================
        
        debug = ConsensusDebug(
            timestamp=datetime.now(timezone.utc),
            symbol=symbol,
            agent_votes=agent_votes,
            agent_scores=agent_scores,
            agent_weights=agent_weights,
            weighted_total=weighted_total,
            available_weight=available_weight,
            consensus_score=consensus_score,
            consensus_action=consensus_action,
            agent_agreement=agreement,
            agreement_direction=agreement_direction,
            directional_bias=directional_bias,
            conflict_detected=conflict_detected,
            confidence_components={},
            final_confidence=0.0,
            final_action=consensus_action,
            decision_reasoning=[]
        )
        
        return consensus_action, consensus_score, debug

    def _get_agent_weight_with_quality(self, agent_name: str, confidence: float) -> float:
        """
        Get agent weight adjusted by confidence quality.
        """
        base_weight = self.agent_weights.get(agent_name, 0.25)
        
        if not self.enable_dynamic_weights:
            # Quality adjustment based on confidence
            quality_boost = 0.5 + (confidence * 0.5)  # 0.5 - 1.0
            return base_weight * quality_boost
        
        # Dynamic weight based on performance
        performance = self.performance_history.get(agent_name, {"correct": 0, "total": 0})
        
        if performance["total"] < 10:
            # Not enough data, use base weight with confidence adjustment
            quality_boost = 0.5 + (confidence * 0.5)
            return base_weight * quality_boost
        
        accuracy = performance["correct"] / performance["total"]
        avg_score = performance.get("avg_score", 0.0)
        
        # Combine performance metrics
        performance_boost = 0.5 + (accuracy * 0.5)  # 0.5 - 1.0
        quality_boost = 0.5 + (confidence * 0.5)
        
        # Final weight = base * performance * quality
        weight = base_weight * performance_boost * quality_boost
        
        # Clamp to reasonable range
        return max(0.05, min(0.50, weight))

    # ============================================================
    # FINAL DECISION WITH REASONING
    # ============================================================
    
    def _determine_final_decision_with_reasoning(
        self,
        decision: Optional[DecisionResult],
        consensus_action: str,
        consensus_score: float,
        sentiment: Optional[SentimentResult],
        technical: Optional[TechnicalResult],
        forecast: Optional[ForecastResult],
        agent_votes: Dict[str, str],
        consensus_debug: ConsensusDebug
    ) -> Tuple[str, float, float, Dict[str, float]]:
        """
        Enhanced final decision with detailed reasoning.
        """
        reasoning = []
        
        # ============================================================
        # 1. EXTRACT BASE SCORES
        # ============================================================
        
        # Decision agent score
        if decision is not None:
            decision_score = self._safe_score(getattr(decision, "action_score", 0.0))
            decision_confidence = self._safe_probability(getattr(decision, "confidence", 0.0))
            reasoning.append(f"Decision Agent: score={decision_score:.3f}, confidence={decision_confidence:.2%}")
        else:
            decision_score = 0.0
            decision_confidence = 0.0
            reasoning.append("Decision Agent: UNAVAILABLE")
        
        # Consensus
        consensus_score = self._safe_score(consensus_score)
        consensus_strength = abs(consensus_score)
        reasoning.append(f"Consensus: action={consensus_action}, score={consensus_score:.3f}, strength={consensus_strength:.3f}")
        
        # Agreement
        agreement = consensus_debug.agent_agreement
        agreement_direction = consensus_debug.agreement_direction
        reasoning.append(f"Agreement: level={agreement:.2%}, direction={agreement_direction:.3f}")
        
        # Technical and sentiment scores
        technical_score = 0.0
        if technical is not None:
            technical_score = self._safe_score(getattr(technical, "overall_score", 0.0))
            reasoning.append(f"Technical: score={technical_score:.3f}")
            
        sentiment_score = 0.0
        if sentiment is not None:
            sentiment_score = self._safe_score(getattr(sentiment, "overall_score", 0.0))
            reasoning.append(f"Sentiment: score={sentiment_score:.3f}")
            
        # ============================================================
        # 2. DETECT ALIGNMENT / CONFLICT
        # ============================================================
        
        tech_sent_aligned = (technical_score > 0.1 and sentiment_score > 0.1) or \
                           (technical_score < -0.1 and sentiment_score < -0.1)
        
        if tech_sent_aligned:
            reasoning.append(f"Tech-Sentiment ALIGNED: both {'bullish' if technical_score > 0 else 'bearish'}")
        else:
            reasoning.append(f"Tech-Sentiment CONFLICT: tech={technical_score:.3f}, sent={sentiment_score:.3f}")
        
        # Detect majority direction
        votes_list = list(agent_votes.values())
        buy_count = votes_list.count("BUY") + votes_list.count("STRONG_BUY")
        sell_count = votes_list.count("SELL") + votes_list.count("STRONG_SELL")
        hold_count = votes_list.count("HOLD")
        
        reasoning.append(f"Votes: BUY={buy_count}, SELL={sell_count}, HOLD={hold_count}")
        
        # ============================================================
        # 3. CALCULATE COMBINED SCORE
        # ============================================================
        
        # Weighted components
        if decision is not None:
            combined_score = (
                decision_score * 0.35 +
                consensus_score * 0.25 +
                agreement_direction * 0.20 +
                technical_score * 0.15 +
                sentiment_score * 0.05
            )
        else:
            combined_score = consensus_score
        
        # Boost for alignment
        if tech_sent_aligned and abs(technical_score) > 0.2:
            combined_score *= 1.1
            reasoning.append("Tech-Sentiment alignment: +10% boost")
        
        # Boost for strong consensus
        if consensus_strength > 0.3 and agreement > 0.6:
            combined_score *= 1.05
            reasoning.append("Strong consensus: +5% boost")
        
        combined_score = self._safe_score(combined_score)
        final_action = self._score_to_action(combined_score)
        reasoning.append(f"Combined score: {combined_score:.3f} -> {final_action}")
        
        # ============================================================
        # 4. CALCULATE CONFIDENCE
        # ============================================================
        
        # Component weights for confidence
        confidence_components = {
            "decision_confidence": decision_confidence,
            "consensus_strength": consensus_strength,
            "agent_agreement": agreement,
            "agreement_direction": abs(agreement_direction),
            "tech_sent_alignment": 1.0 if tech_sent_aligned else 0.0,
            "signal_strength": min(1.0, abs(combined_score) * 2.0),
        }
        
        # Weighted confidence
        if decision is not None:
            raw_confidence = (
                decision_confidence * 0.30 +
                consensus_strength * 0.25 +
                agreement * 0.20 +
                abs(agreement_direction) * 0.15 +
                (1.0 if tech_sent_aligned else 0.0) * 0.10
            )
        else:
            raw_confidence = (
                consensus_strength * 0.35 +
                agreement * 0.30 +
                abs(agreement_direction) * 0.20 +
                (1.0 if tech_sent_aligned else 0.0) * 0.15
            )
        
        # ============================================================
        # 5. HANDLE CONFLICT - PERBAIKAN UTAMA
        # ============================================================
        
        # Jika ada konflik (Technical vs lainnya)
        if consensus_debug.conflict_detected:
            # Cek apakah technical sangat kuat
            if abs(technical_score) > 0.4 and abs(consensus_score) < 0.2:
                # Technical signal kuat tapi consensus lemah
                # Beri penalti pada confidence
                raw_confidence *= 0.8
                reasoning.append("CONFLICT DETECTED: Technical strong vs consensus weak -> confidence penalty")
                
                # Tapi jika technical sangat kuat, kita ikuti technical
                if abs(technical_score) > 0.6:
                    temp_action = self._score_to_action(technical_score)
                    if temp_action != final_action:
                        reasoning.append(f"OVERRIDE: Following strong technical signal ({temp_action})")
                        final_action = temp_action
                        combined_score = technical_score * 0.7 + consensus_score * 0.3
                        combined_score = self._safe_score(combined_score)
        
        # ============================================================
        # 6. ADJUST CONFIDENCE BASED ON FINAL ACTION
        # ============================================================
        
        if final_action != "HOLD":
            # Untuk BUY/SELL, confidence harus cukup tinggi
            if raw_confidence < self.min_confidence_threshold:
                raw_confidence = max(raw_confidence, self.min_confidence_threshold * 0.8)
        else:
            # HOLD - kurangi confidence jika ada conflict
            if consensus_debug.conflict_detected:
                raw_confidence = min(raw_confidence, 0.40)
            else:
                raw_confidence = min(raw_confidence, 0.50)
        
        final_confidence = max(0.0, min(1.0, raw_confidence))
        
        reasoning.append(f"Final confidence: {final_confidence:.2%}")
        
        # ============================================================
        # 7. UPDATE DEBUG
        # ============================================================
        
        consensus_debug.confidence_components = confidence_components
        consensus_debug.final_confidence = final_confidence
        consensus_debug.final_action = final_action
        consensus_debug.decision_reasoning = reasoning
        
        return (final_action, final_confidence, combined_score, confidence_components)

    # ============================================================
    # BASE AGENTS - FULL IMPLEMENTATION
    # ============================================================
    
    async def _run_base_agents(
        self,
        symbol: str,
        market_data: Dict[str, Any]
    ) -> Tuple[Optional[SentimentResult], Optional[TechnicalResult]]:
        """Run Sentiment + Technical agents in parallel."""
        tasks = [
            asyncio.to_thread(self.sentiment_agent.analyze, symbol, market_data),
            asyncio.to_thread(self.technical_agent.analyze, symbol, market_data),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        sentiment_result = None
        technical_result = None
        
        if len(results) > 0 and not isinstance(results[0], Exception):
            sentiment_result = results[0]
        else:
            logger.error("Sentiment agent failed: %s", results[0] if results else "Unknown")
            
        if len(results) > 1 and not isinstance(results[1], Exception):
            technical_result = results[1]
        else:
            logger.error("Technical agent failed: %s", results[1] if len(results) > 1 else "Unknown")
            
        return sentiment_result, technical_result
    
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
                symbol, sentiment, technical, market_data
            )
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
        try:
            return await asyncio.to_thread(
                self.forecast_agent.analyze,
                symbol, sentiment, technical, market_data
            )
        except Exception as e:
            logger.error("Forecast agent failed: %s", e)
            return None
    
    async def _run_reflection(
        self,
        symbol: str,
        market_data: Dict[str, Any]
    ) -> Optional[ReflectionResult]:
        try:
            trades = market_data.get("recent_trades", [])
            if trades is None or not isinstance(trades, list):
                trades = []
            return await asyncio.to_thread(
                self.reflector_agent.analyze,
                symbol, trades, None
            )
        except Exception as e:
            logger.error("Reflector agent failed: %s", e)
            return None

    # ============================================================
    # HELPER METHODS
    # ============================================================
    
    def _get_agent_votes(
        self,
        sentiment: Optional[SentimentResult],
        technical: Optional[TechnicalResult],
        decision: Optional[DecisionResult],
        forecast: Optional[ForecastResult]
    ) -> Dict[str, str]:
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
            
        counts = {
            "BUY": actions.count("BUY") + actions.count("STRONG_BUY"),
            "SELL": actions.count("SELL") + actions.count("STRONG_SELL"),
            "HOLD": actions.count("HOLD"),
        }
        
        majority_count = max(counts.values())
        return round(majority_count / len(actions), 4)
    
    def _agreement_direction(self, votes: Dict[str, str]) -> float:
        if not votes:
            return 0.0
        scores = [self._action_to_score(action) for action in votes.values()]
        if not scores:
            return 0.0
        return self._safe_score(sum(scores) / len(scores))
    
    def _forecast_to_score(self, forecast: ForecastResult) -> float:
        if forecast is None:
            return 0.0
            
        trend_score = 0.0
        trend = str(getattr(forecast, "primary_trend", "")).upper()
        if trend == "BULLISH":
            trend_score = 1.0
        elif trend == "BEARISH":
            trend_score = -1.0
            
        probability_score = 0.0
        next_move = getattr(forecast, "next_move_probability", {})
        if isinstance(next_move, dict):
            up = self._safe_probability(next_move.get("UP", 0.0))
            down = self._safe_probability(next_move.get("DOWN", 0.0))
            probability_score = up - down
            
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
    
    def _action_to_score(self, action: str) -> float:
        mapping = {
            "STRONG_BUY": 1.0,
            "BUY": 0.5,
            "HOLD": 0.0,
            "SELL": -0.5,
            "STRONG_SELL": -1.0,
        }
        return mapping.get(str(action).upper(), 0.0)
    
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
    
    def _get_current_price(
        self,
        market_data: Dict[str, Any],
        technical: Optional[TechnicalResult],
        forecast: Optional[ForecastResult]
    ) -> float:
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
        if technical is not None:
            try:
                price = float(getattr(technical, "current_price", 0.0))
                if price > 0:
                    return price
            except (TypeError, ValueError):
                pass
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
        scores = {}
        if sentiment is not None:
            scores["sentiment"] = round(self._safe_score(getattr(sentiment, "overall_score", 0.0)), 4)
        if technical is not None:
            scores["technical"] = round(self._safe_score(getattr(technical, "overall_score", 0.0)), 4)
        if decision is not None:
            scores["decision"] = round(self._safe_score(getattr(decision, "action_score", 0.0)), 4)
        if forecast is not None:
            scores["forecast"] = round(self._forecast_to_score(forecast), 4)
        scores["consensus"] = round(self._safe_score(consensus_score), 4)
        return scores
    
    def _calculate_position_size(
        self,
        confidence: float,
        decision: Optional[DecisionResult],
        action: str
    ) -> float:
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
    
    def _calculate_sl_tp(
        self,
        technical: Optional[TechnicalResult],
        action: str,
        current_price: float
    ) -> Tuple[Optional[float], Optional[float]]:
        if technical is None or current_price <= 0 or action == "HOLD":
            return None, None
            
        support_levels = self._extract_price_levels(getattr(technical, "support_levels", None))
        resistance_levels = self._extract_price_levels(getattr(technical, "resistance_levels", None))
        
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
    
    def _build_execution_reason(
        self,
        final_action: str,
        final_confidence: float,
        consensus_score: float,
        consensus_debug: ConsensusDebug
    ) -> str:
        if final_action == "HOLD":
            reasons = []
            if final_confidence < 0.50:
                reasons.append(f"Confidence too low: {final_confidence:.1%} < 50%")
            if consensus_debug.conflict_detected:
                reasons.append("Conflict detected between agents")
            if abs(consensus_score) < 0.20:
                reasons.append(f"Weak consensus: {abs(consensus_score):.1%}")
            if consensus_debug.agent_agreement < 0.50:
                reasons.append(f"Poor agent agreement: {consensus_debug.agent_agreement:.1%}")
            if not reasons:
                reasons.append("No clear signal from agents")
            return "; ".join(reasons)
        else:
            return f"Executing {final_action} with {final_confidence:.1%} confidence"
    
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
        execution_reason: Optional[str],
        consensus_debug: Optional[ConsensusDebug]
    ) -> str:
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
            
        # ============================================================
        # CONSENSUS DEBUG SECTION
        # ============================================================
        
        if consensus_debug:
            lines.append("")
            lines.append("--- CONSENSUS DEBUG ---")
            lines.append(f"Agent Agreement: {consensus_debug.agent_agreement:.2%}")
            lines.append(f"Agreement Direction: {consensus_debug.agreement_direction:.4f}")
            lines.append(f"Directional Bias: {consensus_debug.directional_bias}")
            lines.append(f"Conflict Detected: {consensus_debug.conflict_detected}")
            
            if consensus_debug.agent_scores:
                lines.append("Agent Scores:")
                for agent, score in consensus_debug.agent_scores.items():
                    lines.append(f"  {agent}: {score:.4f}")
                    
            if consensus_debug.agent_weights:
                lines.append("Agent Weights:")
                for agent, weight in consensus_debug.agent_weights.items():
                    lines.append(f"  {agent}: {weight:.4f}")
                    
            lines.append(f"Weighted Total: {consensus_debug.weighted_total:.4f}")
            lines.append(f"Available Weight: {consensus_debug.available_weight:.4f}")
            
            if consensus_debug.confidence_components:
                lines.append("Confidence Components:")
                for key, value in consensus_debug.confidence_components.items():
                    lines.append(f"  {key}: {value:.4f}")
            
            if consensus_debug.decision_reasoning:
                lines.append("Decision Reasoning:")
                for reason in consensus_debug.decision_reasoning:
                    lines.append(f"  - {reason}")
        
        lines.append("")
        lines.append("NOTE: Position size and SL/TP are preliminary only.")
        lines.append("Risk Engine must validate them before execution.")
        
        return "\n".join(lines)
    
    def _log_consensus_debug(self, debug: ConsensusDebug):
        """Log consensus debug information."""
        logger.info("=" * 60)
        logger.info("CONSENSUS DEBUG: %s", debug.symbol)
        logger.info("-" * 60)
        logger.info("Agent Votes: %s", debug.agent_votes)
        logger.info("Agent Scores: %s", debug.agent_scores)
        logger.info("Agent Weights: %s", debug.agent_weights)
        logger.info("Weighted Total: %.4f | Available Weight: %.4f", 
                   debug.weighted_total, debug.available_weight)
        logger.info("Consensus: %s (%.4f)", debug.consensus_action, debug.consensus_score)
        logger.info("Agreement: %.2f%% | Direction: %.4f", 
                   debug.agent_agreement * 100, debug.agreement_direction)
        logger.info("Conflict: %s | Bias: %s", debug.conflict_detected, debug.directional_bias)
        logger.info("Final Action: %s | Confidence: %.2f%%", 
                   debug.final_action, debug.final_confidence * 100)
        logger.info("Confidence Components: %s", debug.confidence_components)
        if debug.decision_reasoning:
            logger.info("Decision Reasoning:")
            for reason in debug.decision_reasoning:
                logger.info("  - %s", reason)
        logger.info("=" * 60)
    
    def _get_default_result(self, symbol: str) -> OrchestratorResult:
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
                "signal_strength": 0.0,
            },
            market_scores={},
            summary=summary,
            execution_reason="Error during analysis"
        )
    
    def update_agent_performance(self, agent_name: str, was_correct: bool, score: float = 0.0):
        if agent_name not in self.performance_history:
            self.performance_history[agent_name] = {"correct": 0, "total": 0, "avg_score": 0.0, "total_score": 0.0}
            
        perf = self.performance_history[agent_name]
        perf["total"] += 1
        if was_correct:
            perf["correct"] += 1
        if score != 0.0:
            perf["total_score"] += abs(score)
            perf["avg_score"] = perf["total_score"] / perf["total"]
    
    def get_history(self, n: int = 10) -> List[OrchestratorResult]:
        if n <= 0:
            return []
        return self.history[-n:]
