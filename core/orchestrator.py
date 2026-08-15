"""
Orchestrator - AI Decision Coordination Layer
Dengan Unified Market Data dan Confidence Calibration
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

from core.unified_market_data import UnifiedMarketDataProvider, UnifiedMarketSnapshot

logger = logging.getLogger(__name__)


@dataclass
class ConsensusDebug:
    """Structured debug data untuk consensus process"""
    timestamp: datetime
    symbol: str
    agent_votes: Dict[str, str]
    agent_scores: Dict[str, float]
    agent_weights: Dict[str, float]
    agent_confidences: Dict[str, float]
    weighted_total: float
    available_weight: float
    consensus_score: float
    consensus_action: str
    agent_agreement: float
    agreement_direction: float
    directional_bias: str
    conflict_detected: bool
    conflict_type: str
    conflict_severity: float  # 0-1, seberapa parah konflik
    confidence_components: Dict[str, float]
    final_confidence: float
    final_action: str
    decision_reasoning: List[str]
    price_data: Dict[str, float]
    missing_data: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "agent_votes": self.agent_votes,
            "agent_scores": self.agent_scores,
            "agent_weights": self.agent_weights,
            "agent_confidences": self.agent_confidences,
            "weighted_total": self.weighted_total,
            "available_weight": self.available_weight,
            "consensus_score": self.consensus_score,
            "consensus_action": self.consensus_action,
            "agent_agreement": self.agent_agreement,
            "agreement_direction": self.agreement_direction,
            "directional_bias": self.directional_bias,
            "conflict_detected": self.conflict_detected,
            "conflict_type": self.conflict_type,
            "conflict_severity": self.conflict_severity,
            "confidence_components": self.confidence_components,
            "final_confidence": self.final_confidence,
            "final_action": self.final_action,
            "decision_reasoning": self.decision_reasoning,
            "price_data": self.price_data,
            "missing_data": self.missing_data
        }


@dataclass
class OrchestratorResult:
    """Hasil lengkap dari proses analisis Orchestrator."""
    timestamp: datetime
    symbol: str
    current_price: float
    unified_snapshot: Optional[UnifiedMarketSnapshot]  # NEW
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
    consensus_debug: Optional[ConsensusDebug] = None
    hold_reason: Optional[str] = None


class Orchestrator:
    """Central coordinator dengan Unified Market Data."""

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
        # UNIFIED MARKET DATA PROVIDER
        # ============================================================
        
        self.market_data_provider = UnifiedMarketDataProvider()
        
        # ============================================================
        # VOTING THRESHOLDS - DIKALIBRASI
        # ============================================================
        
        self.voting_thresholds = {
            "strong_buy": 0.60,
            "buy": 0.20,
            "sell": -0.20,
            "strong_sell": -0.60,
        }
        
        # ============================================================
        # AGENT WEIGHTS - STABLE
        # ============================================================
        
        self.agent_weights = {
            "sentiment": 0.20,
            "technical": 0.35,
            "decision": 0.30,
            "forecast": 0.15,
        }
        
        # ============================================================
        # CONFIDENCE THRESHOLDS - DIKALIBRASI ULANG
        # ============================================================
        
        self.min_confidence_threshold = float(config.get("min_confidence", 0.40))
        self.high_confidence_threshold = float(config.get("high_confidence", 0.65))
        
        # ============================================================
        # CONFLICT HANDLING - LESS PENALTY
        # ============================================================
        
        self.conflict_penalty = float(config.get("conflict_penalty", 0.08))  # 8% instead of 15%
        self.minor_conflict_penalty = float(config.get("minor_conflict_penalty", 0.03))  # 3%
        self.severe_conflict_penalty = float(config.get("severe_conflict_penalty", 0.15))  # 15%
        
        # ============================================================
        # POSITION SIZING
        # ============================================================
        
        self.max_position_size = float(config.get("max_position_size", 0.20))
        self.default_position_size = float(config.get("default_position_size", 0.05))
        self.min_position_size = float(config.get("min_position_size", 0.01))
        
        # ============================================================
        # HISTORY
        # ============================================================
        
        self.history: List[OrchestratorResult] = []
        self.max_history = int(config.get("max_history", 100))
        self.debug_enabled = config.get("debug_enabled", True)
        
        logger.info("Orchestrator initialized with Unified Market Data")

    # ============================================================
    # PUBLIC ANALYZE
    # ============================================================
    
    async def analyze(
        self,
        symbol: str,
        market_data: Optional[Dict[str, Any]] = None
    ) -> OrchestratorResult:
        """
        Menjalankan seluruh pipeline dengan Unified Market Snapshot.
        """
        logger.info("Starting analysis for %s", symbol)
        market_data = market_data.copy() if isinstance(market_data, dict) else {}
        
        try:
            # ============================================================
            # FIX 1: CREATE UNIFIED MARKET SNAPSHOT
            # ============================================================
            
            unified_snapshot = self._create_unified_snapshot(symbol, market_data)
            
            # ============================================================
            # FIX 2: INJECT UNIFIED DATA INTO MARKET_DATA
            # ============================================================
            
            unified_dict = unified_snapshot.to_dict()
            market_data.update(unified_dict)
            market_data["unified_snapshot"] = unified_snapshot
            
            # ============================================================
            # STEP 1-4: RUN AGENTS WITH UNIFIED DATA
            # ============================================================
            
            sentiment_result, technical_result = await self._run_base_agents(
                symbol, market_data, unified_snapshot
            )
            
            decision_result = await self._run_decision(
                symbol, sentiment_result, technical_result, market_data, unified_snapshot
            )
            
            forecast_result = await self._run_forecast(
                symbol, sentiment_result, technical_result, market_data, unified_snapshot
            )
            
            reflection_result = await self._run_reflection(
                symbol, market_data, unified_snapshot
            )
            
            # ============================================================
            # STEP 5: CONSENSUS WITH DEBUG
            # ============================================================
            
            consensus_action, consensus_score, consensus_debug = \
                await self._perform_consensus_with_debug(
                    symbol=symbol,
                    sentiment=sentiment_result,
                    technical=technical_result,
                    decision=decision_result,
                    forecast=forecast_result,
                    unified_snapshot=unified_snapshot
                )
            
            # ============================================================
            # STEP 6: AGENT VOTES
            # ============================================================
            
            agent_votes = self._get_agent_votes(
                sentiment=sentiment_result,
                technical=technical_result,
                decision=decision_result,
                forecast=forecast_result
            )
            
            # ============================================================
            # STEP 7: FINAL DECISION
            # ============================================================
            
            final_action, final_confidence, final_score, confidence_components, hold_reason = \
                self._determine_final_decision_enhanced(
                    decision=decision_result,
                    consensus_action=consensus_action,
                    consensus_score=consensus_score,
                    sentiment=sentiment_result,
                    technical=technical_result,
                    forecast=forecast_result,
                    agent_votes=agent_votes,
                    consensus_debug=consensus_debug,
                    unified_snapshot=unified_snapshot
                )
            
            # ============================================================
            # STEP 8: POSITION SIZE
            # ============================================================
            
            position_size = self._calculate_position_size(
                confidence=final_confidence,
                decision=decision_result,
                action=final_action
            )
            
            # ============================================================
            # STEP 9: SL / TP
            # ============================================================
            
            stop_loss, take_profit = None, None
            if final_action != "HOLD" and final_confidence >= self.min_confidence_threshold:
                stop_loss, take_profit = self._calculate_sl_tp(
                    technical=technical_result,
                    action=final_action,
                    current_price=unified_snapshot.current_price
                )
            
            # ============================================================
            # STEP 10: MARKET SCORES
            # ============================================================
            
            market_scores = self._build_market_scores(
                sentiment=sentiment_result,
                technical=technical_result,
                decision=decision_result,
                forecast=forecast_result,
                consensus_score=consensus_score
            )
            
            # ============================================================
            # STEP 11: EXECUTION REASON
            # ============================================================
            
            execution_reason = self._build_execution_reason(
                final_action=final_action,
                final_confidence=final_confidence,
                consensus_score=consensus_score,
                consensus_debug=consensus_debug,
                hold_reason=hold_reason
            )
            
            # ============================================================
            # STEP 12: SUMMARY
            # ============================================================
            
            summary = self._generate_summary(
                symbol=symbol,
                unified_snapshot=unified_snapshot,
                final_action=final_action,
                final_confidence=final_confidence,
                position_size=position_size,
                consensus_action=consensus_action,
                consensus_score=consensus_score,
                agent_votes=agent_votes,
                stop_loss=stop_loss,
                take_profit=take_profit,
                execution_reason=execution_reason,
                consensus_debug=consensus_debug,
                hold_reason=hold_reason
            )
            
            # ============================================================
            # STEP 13: BUILD RESULT
            # ============================================================
            
            result = OrchestratorResult(
                timestamp=datetime.now(timezone.utc),
                symbol=symbol,
                current_price=unified_snapshot.current_price,
                unified_snapshot=unified_snapshot,
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
                decision_score=final_score,
                confidence_components=confidence_components,
                market_scores=market_scores,
                summary=summary,
                execution_reason=execution_reason,
                consensus_debug=consensus_debug if self.debug_enabled else None,
                hold_reason=hold_reason if final_action == "HOLD" else None
            )
            
            # ============================================================
            # STEP 14: SAVE HISTORY
            # ============================================================
            
            self.history.append(result)
            if len(self.history) > self.max_history:
                self.history.pop(0)
            
            # ============================================================
            # STEP 15: LOG DEBUG
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
    # FIX 1: CREATE UNIFIED SNAPSHOT
    # ============================================================
    
    def _create_unified_snapshot(
        self,
        symbol: str,
        market_data: Dict[str, Any]
    ) -> UnifiedMarketSnapshot:
        """
        Create unified market snapshot from market data.
        """
        # Extract price
        current_price = 0.0
        for key in ["current_price", "price", "last_price", "close", "orchestrator_price"]:
            value = market_data.get(key)
            if value is not None:
                try:
                    current_price = float(value)
                    if current_price > 0:
                        break
                except (TypeError, ValueError):
                    continue
        
        if current_price <= 0:
            current_price = 60000.0  # Fallback
            logger.warning("No valid price found for %s, using fallback", symbol)
        
        # Extract OHLCV data
        ohlcv_data = market_data.get("ohlcv", [])
        if not ohlcv_data and "ohlcv_data" in market_data:
            ohlcv_data = market_data.get("ohlcv_data", [])
        
        # Extract Fear & Greed
        fear_greed_index = market_data.get("fear_greed_index")
        if fear_greed_index is None:
            fear_greed_index = market_data.get("fear_greed", None)
        
        # Extract volume
        volume_24h = market_data.get("volume_24h")
        if volume_24h is None:
            volume_24h = market_data.get("volume", None)
        
        # Extract 24h high/low
        high_24h = market_data.get("high_24h")
        low_24h = market_data.get("low_24h")
        
        # Create snapshot
        snapshot = self.market_data_provider.create_snapshot(
            symbol=symbol,
            current_price=current_price,
            ohlcv_data=ohlcv_data,
            timeframe=market_data.get("timeframe", "1h"),
            fear_greed_index=fear_greed_index,
            volume_24h=volume_24h,
            high_24h=high_24h,
            low_24h=low_24h
        )
        
        return snapshot

    # ============================================================
    # FIX 2: AGENTS WITH UNIFIED DATA
    # ============================================================
    
    async def _run_base_agents(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        unified_snapshot: UnifiedMarketSnapshot
    ) -> Tuple[Optional[SentimentResult], Optional[TechnicalResult]]:
        """
        Run Sentiment + Technical agents dengan unified data.
        """
        # Pastikan semua agent mendapat unified price
        market_data["unified_price"] = unified_snapshot.current_price
        market_data["unified_snapshot"] = unified_snapshot
        
        tasks = [
            asyncio.to_thread(self.sentiment_agent.analyze, symbol, market_data),
            asyncio.to_thread(self.technical_agent.analyze, symbol, market_data),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        sentiment_result = None
        technical_result = None
        
        if len(results) > 0 and not isinstance(results[0], Exception):
            sentiment_result = results[0]
            # Override price jika agent pakai harga berbeda
            if hasattr(sentiment_result, "current_price"):
                sentiment_result.current_price = unified_snapshot.current_price
        else:
            logger.error("Sentiment agent failed: %s", results[0] if results else "Unknown")
            
        if len(results) > 1 and not isinstance(results[1], Exception):
            technical_result = results[1]
            # Override price jika agent pakai harga berbeda
            if hasattr(technical_result, "current_price"):
                technical_result.current_price = unified_snapshot.current_price
        else:
            logger.error("Technical agent failed: %s", results[1] if len(results) > 1 else "Unknown")
            
        return sentiment_result, technical_result
    
    async def _run_decision(
        self,
        symbol: str,
        sentiment: Optional[SentimentResult],
        technical: Optional[TechnicalResult],
        market_data: Dict[str, Any],
        unified_snapshot: UnifiedMarketSnapshot
    ) -> Optional[DecisionResult]:
        try:
            # Inject unified price
            market_data["unified_price"] = unified_snapshot.current_price
            market_data["unified_snapshot"] = unified_snapshot
            
            result = await asyncio.to_thread(
                self.decision_agent.analyze,
                symbol, sentiment, technical, market_data
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
        market_data: Dict[str, Any],
        unified_snapshot: UnifiedMarketSnapshot
    ) -> Optional[ForecastResult]:
        try:
            # Inject unified price
            market_data["unified_price"] = unified_snapshot.current_price
            market_data["unified_snapshot"] = unified_snapshot
            
            result = await asyncio.to_thread(
                self.forecast_agent.analyze,
                symbol, sentiment, technical, market_data
            )
            return result
        except Exception as e:
            logger.error("Forecast agent failed: %s", e)
            return None
    
    async def _run_reflection(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        unified_snapshot: UnifiedMarketSnapshot
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
    # FIX 3: CONSENSUS WITH PROPER CONFLICT DETECTION
    # ============================================================
    
    async def _perform_consensus_with_debug(
        self,
        symbol: str,
        sentiment: Optional[SentimentResult],
        technical: Optional[TechnicalResult],
        decision: Optional[DecisionResult],
        forecast: Optional[ForecastResult],
        unified_snapshot: UnifiedMarketSnapshot
    ) -> Tuple[str, float, ConsensusDebug]:
        """
        Perform weighted consensus with proper conflict detection.
        """
        agent_scores = {}
        agent_votes = {}
        agent_weights = {}
        agent_confidences = {}
        weighted_total = 0.0
        available_weight = 0.0
        missing_data = unified_snapshot.missing_fields.copy()
        price_data = {
            "unified_price": unified_snapshot.current_price,
            "data_quality": unified_snapshot.data_quality_score
        }
        
        # Sentiment
        if sentiment is not None:
            raw_score = self._safe_score(getattr(sentiment, "overall_score", 0.0))
            confidence = self._safe_probability(getattr(sentiment, "confidence", 0.5))
            
            # FIX: Jika ada missing data, kurangi bobot sentiment
            quality_penalty = 1.0 - (len(unified_snapshot.missing_fields) * 0.05)
            confidence_adjusted = confidence * quality_penalty
            
            score = self._normalize_score_with_confidence(raw_score, confidence_adjusted)
            
            agent_scores["sentiment"] = score
            agent_votes["sentiment"] = self._score_to_action(raw_score)
            agent_confidences["sentiment"] = confidence_adjusted
            
            if hasattr(sentiment, "current_price"):
                price_data["sentiment_price"] = float(getattr(sentiment, "current_price", unified_snapshot.current_price))
            
            weight = self._get_agent_weight("sentiment", confidence_adjusted)
            agent_weights["sentiment"] = weight
            weighted_total += score * weight
            available_weight += weight
            
            logger.debug("Sentiment: raw=%.4f, conf=%.2f, adj=%.2f, weight=%.4f",
                        raw_score, confidence, confidence_adjusted, weight)
        
        # Technical - FIX: Pattern confidence vs directional confidence
        if technical is not None:
            raw_score = self._safe_score(getattr(technical, "overall_score", 0.0))
            confidence = self._safe_probability(getattr(technical, "confidence", 0.5))
            
            # FIX: Kurangi confidence jika pattern strength tinggi tapi score rendah
            # Ini berarti pattern terdeteksi tapi arah tidak jelas
            pattern_confidence = self._get_pattern_confidence(technical)
            if pattern_confidence > 0.8 and abs(raw_score) < 0.2:
                # Pattern detected but direction unclear - reduce confidence
                confidence = confidence * 0.7
                logger.debug("Technical: Pattern detected but direction unclear, confidence reduced")
            
            score = self._normalize_score_with_confidence(raw_score, confidence)
            
            agent_scores["technical"] = score
            agent_votes["technical"] = self._score_to_action(raw_score)
            agent_confidences["technical"] = confidence
            
            if hasattr(technical, "current_price"):
                price_data["technical_price"] = float(getattr(technical, "current_price", unified_snapshot.current_price))
            
            weight = self._get_agent_weight("technical", confidence)
            agent_weights["technical"] = weight
            weighted_total += score * weight
            available_weight += weight
            
            logger.debug("Technical: raw=%.4f, conf=%.2f, pattern_conf=%.2f, weight=%.4f",
                        raw_score, confidence, pattern_confidence, weight)
        
        # Decision
        if decision is not None:
            raw_score = self._safe_score(getattr(decision, "action_score", 0.0))
            confidence = self._safe_probability(getattr(decision, "confidence", 0.5))
            
            # FIX: Jika decision adalah HOLD dengan score kecil, kurangi bobot
            if raw_score == 0.0 or abs(raw_score) < 0.05:
                confidence = confidence * 0.8
            
            score = self._normalize_score_with_confidence(raw_score, confidence)
            
            agent_scores["decision"] = score
            agent_votes["decision"] = self._score_to_action(raw_score)
            agent_confidences["decision"] = confidence
            
            weight = self._get_agent_weight("decision", confidence)
            agent_weights["decision"] = weight
            weighted_total += score * weight
            available_weight += weight
            
            logger.debug("Decision: raw=%.4f, conf=%.2f, weight=%.4f",
                        raw_score, confidence, weight)
        
        # Forecast - FIX: Model agreement-based confidence
        if forecast is not None:
            raw_score = self._forecast_to_score(forecast)
            confidence = self._safe_probability(getattr(forecast, "confidence", 0.5))
            
            # FIX: Jika model agreement rendah, turunkan confidence
            model_agreement = self._get_forecast_model_agreement(forecast)
            if model_agreement < 0.6:
                confidence = confidence * model_agreement
                logger.debug("Forecast: Model agreement %.2f -> confidence reduced to %.2f",
                            model_agreement, confidence)
            
            score = self._normalize_score_with_confidence(raw_score, confidence)
            
            agent_scores["forecast"] = score
            agent_votes["forecast"] = self._score_to_action(raw_score)
            agent_confidences["forecast"] = confidence
            
            if hasattr(forecast, "current_price"):
                price_data["forecast_price"] = float(getattr(forecast, "current_price", unified_snapshot.current_price))
            
            weight = self._get_agent_weight("forecast", confidence)
            agent_weights["forecast"] = weight
            weighted_total += score * weight
            available_weight += weight
            
            logger.debug("Forecast: raw=%.4f, conf=%.2f, agreement=%.2f, weight=%.4f",
                        raw_score, confidence, model_agreement, weight)
        
        # Normalize weights jika available_weight < 1.0
        if available_weight > 0 and available_weight < 1.0:
            # Normalize agar total weight = 1.0
            normalization_factor = 1.0 / available_weight
            for agent in agent_weights:
                agent_weights[agent] *= normalization_factor
            weighted_total *= normalization_factor
            available_weight = 1.0
        
        # Calculate consensus
        if available_weight <= 0:
            consensus_score = 0.0
            consensus_action = "HOLD"
        else:
            consensus_score = self._safe_score(weighted_total / available_weight)
            consensus_action = self._score_to_action(consensus_score)
        
        # Calculate agreement
        agreement = self._calculate_agent_agreement(agent_votes)
        agreement_direction = self._agreement_direction(agent_votes)
        
        # ============================================================
        # FIX 4: ENHANCED CONFLICT DETECTION WITH SEVERITY
        # ============================================================
        
        conflict_detected = False
        conflict_type = "NONE"
        conflict_severity = 0.0
        
        # Get all actions
        actions = list(agent_votes.values())
        
        # Check for BUY vs SELL conflict
        has_buy = any(a in ["BUY", "STRONG_BUY"] for a in actions)
        has_sell = any(a in ["SELL", "STRONG_SELL"] for a in actions)
        
        if has_buy and has_sell:
            conflict_detected = True
            conflict_type = "BUY_SELL"
            conflict_severity = 0.8  # Severe
        # Check for Tech vs Sentiment conflict
        elif "technical" in agent_votes and "sentiment" in agent_votes:
            tech_vote = agent_votes["technical"]
            sent_vote = agent_votes["sentiment"]
            
            if (tech_vote in ["SELL", "STRONG_SELL"] and sent_vote in ["BUY", "STRONG_BUY"]) or \
               (tech_vote in ["BUY", "STRONG_BUY"] and sent_vote in ["SELL", "STRONG_SELL"]):
                conflict_detected = True
                conflict_type = "TECH_SENTIMENT"
                conflict_severity = 0.6
        # Check for Tech vs Consensus
        elif "technical" in agent_votes:
            tech_score = agent_scores.get("technical", 0.0)
            consensus_without_tech = self._calculate_consensus_without_agent(agent_scores, "technical", agent_weights)
            
            if abs(tech_score) > 0.3 and abs(consensus_without_tech) < 0.15:
                conflict_detected = True
                conflict_type = "TECH_CONSENSUS"
                conflict_severity = 0.5
        # Minor conflict (3 HOLD, 1 directional)
        elif actions.count("HOLD") >= 3 and any(a not in ["HOLD"] for a in actions):
            conflict_detected = True
            conflict_type = "MINOR"
            conflict_severity = 0.3  # Low severity
        
        # ============================================================
        # DETERMINE DIRECTIONAL BIAS
        # ============================================================
        
        directional_bias = "NEUTRAL"
        if consensus_score > 0.2:
            directional_bias = "BULLISH"
        elif consensus_score < -0.2:
            directional_bias = "BEARISH"
        
        # If conflict detected, bias based on strongest signal
        if conflict_detected and "technical" in agent_scores:
            tech_score = agent_scores["technical"]
            if abs(tech_score) > abs(consensus_score):
                if tech_score > 0:
                    directional_bias = "BULLISH_CONFLICT"
                else:
                    directional_bias = "BEARISH_CONFLICT"
        
        # ============================================================
        # BUILD DEBUG
        # ============================================================
        
        debug = ConsensusDebug(
            timestamp=datetime.now(timezone.utc),
            symbol=symbol,
            agent_votes=agent_votes,
            agent_scores=agent_scores,
            agent_weights=agent_weights,
            agent_confidences=agent_confidences,
            weighted_total=weighted_total,
            available_weight=available_weight,
            consensus_score=consensus_score,
            consensus_action=consensus_action,
            agent_agreement=agreement,
            agreement_direction=agreement_direction,
            directional_bias=directional_bias,
            conflict_detected=conflict_detected,
            conflict_type=conflict_type,
            conflict_severity=conflict_severity,
            confidence_components={},
            final_confidence=0.0,
            final_action=consensus_action,
            decision_reasoning=[],
            price_data=price_data,
            missing_data=missing_data
        )
        
        return consensus_action, consensus_score, debug

    # ============================================================
    # FIX 5: ENHANCED FINAL DECISION
    # ============================================================
    
    def _determine_final_decision_enhanced(
        self,
        decision: Optional[DecisionResult],
        consensus_action: str,
        consensus_score: float,
        sentiment: Optional[SentimentResult],
        technical: Optional[TechnicalResult],
        forecast: Optional[ForecastResult],
        agent_votes: Dict[str, str],
        consensus_debug: ConsensusDebug,
        unified_snapshot: UnifiedMarketSnapshot
    ) -> Tuple[str, float, float, Dict[str, float], Optional[str]]:
        """
        Enhanced final decision dengan proper conflict resolution.
        """
        reasoning = []
        hold_reason = None
        
        # ============================================================
        # EXTRACT BASE SCORES
        # ============================================================
        
        if decision is not None:
            decision_score = self._safe_score(getattr(decision, "action_score", 0.0))
            decision_confidence = self._safe_probability(getattr(decision, "confidence", 0.5))
            reasoning.append(f"Decision Agent: score={decision_score:.4f}, confidence={decision_confidence:.2%}")
        else:
            decision_score = 0.0
            decision_confidence = 0.0
            reasoning.append("Decision Agent: UNAVAILABLE")
        
        consensus_score = self._safe_score(consensus_score)
        consensus_strength = abs(consensus_score)
        reasoning.append(f"Consensus: action={consensus_action}, score={consensus_score:.4f}, strength={consensus_strength:.4f}")
        
        agreement = consensus_debug.agent_agreement
        agreement_direction = consensus_debug.agreement_direction
        reasoning.append(f"Agreement: level={agreement:.2%}, direction={agreement_direction:.4f}")
        
        technical_score = 0.0
        if technical is not None:
            technical_score = self._safe_score(getattr(technical, "overall_score", 0.0))
            reasoning.append(f"Technical: score={technical_score:.4f}")
        
        sentiment_score = 0.0
        if sentiment is not None:
            sentiment_score = self._safe_score(getattr(sentiment, "overall_score", 0.0))
            reasoning.append(f"Sentiment: score={sentiment_score:.4f}")
        
        forecast_score = 0.0
        if forecast is not None:
            forecast_score = self._forecast_to_score(forecast)
            reasoning.append(f"Forecast: score={forecast_score:.4f}")
        
        # ============================================================
        # DETECT ALIGNMENT
        # ============================================================
        
        tech_sent_aligned = (technical_score > 0.1 and sentiment_score > 0.1) or \
                           (technical_score < -0.1 and sentiment_score < -0.1)
        
        if tech_sent_aligned:
            reasoning.append(f"Tech-Sentiment ALIGNED: both {'bullish' if technical_score > 0 else 'bearish'}")
        else:
            reasoning.append(f"Tech-Sentiment CONFLICT: tech={technical_score:.4f}, sent={sentiment_score:.4f}")
        
        # ============================================================
        # HANDLE CONFLICT WITH SEVERITY-BASED PENALTY
        # ============================================================
        
        conflict_detected = consensus_debug.conflict_detected
        conflict_severity = consensus_debug.conflict_severity
        conflict_type = consensus_debug.conflict_type
        
        # Final action based on consensus first
        final_action = consensus_action
        
        if conflict_detected:
            reasoning.append(f"CONFLICT DETECTED: {conflict_type} (severity={conflict_severity:.2f})")
            
            # ============================================================
            # FIX: RESOLVE CONFLICT BASED ON SEVERITY
            # ============================================================
            
            if conflict_severity >= 0.7:  # Severe conflict (BUY vs SELL)
                # Technical vs Sentiment conflict
                if conflict_type == "BUY_SELL":
                    # Cek mana yang lebih kuat
                    if abs(technical_score) > 0.4 and abs(technical_score) > abs(sentiment_score) * 1.3:
                        final_action = self._score_to_action(technical_score)
                        reasoning.append(f"Technical overrides ({technical_score:.4f}) vs Sentiment ({sentiment_score:.4f})")
                    elif abs(sentiment_score) > 0.4 and abs(sentiment_score) > abs(technical_score) * 1.3:
                        final_action = self._score_to_action(sentiment_score)
                        reasoning.append(f"Sentiment overrides ({sentiment_score:.4f}) vs Technical ({technical_score:.4f})")
                    else:
                        final_action = "HOLD"
                        hold_reason = f"Balanced conflict: Tech={technical_score:.4f}, Sent={sentiment_score:.4f}"
                        reasoning.append(hold_reason)
            
            elif conflict_severity >= 0.4:  # Medium conflict (Tech vs Consensus)
                if abs(technical_score) > 0.4:
                    # Technical strong enough
                    final_action = self._score_to_action(technical_score)
                    reasoning.append(f"Strong technical signal ({technical_score:.4f}) overrides weak consensus")
                else:
                    final_action = "HOLD"
                    hold_reason = f"Technical signal ({technical_score:.4f}) not strong enough vs consensus"
                    reasoning.append(hold_reason)
            
            else:  # Minor conflict (3 HOLD, 1 directional)
                # Cek jika directional agent punya sinyal kuat
                directional_agent = None
                directional_score = 0.0
                for agent, vote in agent_votes.items():
                    if vote not in ["HOLD"]:
                        directional_agent = agent
                        directional_score = consensus_debug.agent_scores.get(agent, 0.0)
                        break
                
                if directional_agent and abs(directional_score) > 0.4:
                    # Sinyal kuat, ikuti
                    final_action = self._score_to_action(directional_score)
                    reasoning.append(f"Following {directional_agent} signal ({directional_score:.4f}) despite minor conflict")
                else:
                    final_action = "HOLD"
                    hold_reason = f"Minor conflict: {directional_agent if directional_agent else 'unknown'} signal ({directional_score:.4f}) too weak"
                    reasoning.append(hold_reason)
        
        # ============================================================
        # CALCULATE COMBINED SCORE
        # ============================================================
        
        # Weighted components
        if decision is not None and final_action != "HOLD":
            combined_score = (
                decision_score * 0.35 +
                consensus_score * 0.25 +
                agreement_direction * 0.20 +
                technical_score * 0.12 +
                sentiment_score * 0.08
            )
        else:
            combined_score = consensus_score
        
        combined_score = self._safe_score(combined_score)
        if final_action != "HOLD":
            final_action = self._score_to_action(combined_score)
        
        # ============================================================
        # FIX: CALCULATE CONFIDENCE WITH SEVERITY-BASED PENALTY
        # ============================================================
        
        confidence_components = {
            "decision_confidence": decision_confidence,
            "consensus_strength": consensus_strength,
            "agent_agreement": agreement,
            "agreement_direction": abs(agreement_direction),
            "signal_strength": min(1.0, abs(combined_score) * 2.0),
        }
        
        # Base confidence
        if decision is not None:
            raw_confidence = (
                decision_confidence * 0.30 +
                consensus_strength * 0.25 +
                agreement * 0.20 +
                abs(agreement_direction) * 0.15 +
                confidence_components["signal_strength"] * 0.10
            )
        else:
            raw_confidence = (
                consensus_strength * 0.35 +
                agreement * 0.30 +
                abs(agreement_direction) * 0.20 +
                confidence_components["signal_strength"] * 0.15
            )
        
        # ============================================================
        # FIX: APPLY SEVERITY-BASED PENALTY (NOT UNIFORM)
        # ============================================================
        
        if conflict_detected and final_action != "HOLD":
            # Penalty berdasarkan severity
            if conflict_severity >= 0.7:
                penalty = self.severe_conflict_penalty  # 15%
            elif conflict_severity >= 0.4:
                penalty = self.conflict_penalty  # 8%
            else:
                penalty = self.minor_conflict_penalty  # 3%
            
            raw_confidence *= (1.0 - penalty)
            reasoning.append(f"Conflict penalty: {penalty:.0%} (severity={conflict_severity:.2f})")
            confidence_components["conflict_penalty"] = penalty
        
        # Data quality penalty (jika ada missing data)
        quality_penalty = 1.0 - (len(consensus_debug.missing_data) * 0.02)
        if quality_penalty < 0.9:
            raw_confidence *= quality_penalty
            confidence_components["data_quality_penalty"] = 1.0 - quality_penalty
            reasoning.append(f"Data quality penalty: {(1.0 - quality_penalty):.0%}")
        
        final_confidence = max(0.0, min(1.0, raw_confidence))
        
        # ============================================================
        # FINAL ACTION VALIDATION
        # ============================================================
        
        if final_confidence < self.min_confidence_threshold:
            if final_action != "HOLD":
                hold_reason = f"Confidence {final_confidence:.1%} below threshold {self.min_confidence_threshold:.0%}"
                reasoning.append(hold_reason)
            final_action = "HOLD"
            combined_score = 0.0
        
        # Update debug
        consensus_debug.confidence_components = confidence_components
        consensus_debug.final_confidence = final_confidence
        consensus_debug.final_action = final_action
        consensus_debug.decision_reasoning = reasoning
        
        return final_action, final_confidence, combined_score, confidence_components, hold_reason

    # ============================================================
    # HELPER METHODS
    # ============================================================
    
    def _normalize_score_with_confidence(self, score: float, confidence: float) -> float:
        """Normalize score with confidence adjustment."""
        if confidence < 0.3:
            return 0.0
        quality_factor = 0.3 + (confidence * 0.7)
        return self._safe_score(score * quality_factor)
    
    def _get_pattern_confidence(self, technical: TechnicalResult) -> float:
        """Extract pattern detection confidence."""
        try:
            patterns = getattr(technical, "detected_patterns", [])
            if patterns and isinstance(patterns, list):
                # Ambil confidence tertinggi dari pattern
                max_conf = 0.0
                for p in patterns:
                    if isinstance(p, dict):
                        conf = p.get("confidence", 0.0)
                        if conf > max_conf:
                            max_conf = conf
                return max_conf
        except (AttributeError, TypeError):
            pass
        return 0.0
    
    def _get_forecast_model_agreement(self, forecast: ForecastResult) -> float:
        """Extract model agreement from forecast."""
        try:
            agreement = getattr(forecast, "model_agreement", None)
            if agreement is not None:
                return float(agreement)
        except (AttributeError, TypeError, ValueError):
            pass
        return 0.5
    
    def _calculate_consensus_without_agent(
        self,
        agent_scores: Dict[str, float],
        exclude_agent: str,
        agent_weights: Dict[str, float]
    ) -> float:
        """Calculate consensus excluding a specific agent."""
        total = 0.0
        weight = 0.0
        
        for agent, score in agent_scores.items():
            if agent == exclude_agent:
                continue
            w = agent_weights.get(agent, 0.25)
            total += score * w
            weight += w
        
        if weight <= 0:
            return 0.0
        
        return self._safe_score(total / weight)
    
    def _get_agent_weight(self, agent_name: str, confidence: float) -> float:
        """Get agent weight with confidence adjustment."""
        base_weight = self.agent_weights.get(agent_name, 0.25)
        quality_boost = 0.4 + (confidence * 0.6)
        weight = base_weight * quality_boost
        return max(0.05, min(0.50, weight))
    
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
    
    def _calculate_position_size(
        self,
        confidence: float,
        decision: Optional[DecisionResult],
        action: str
    ) -> float:
        if action == "HOLD":
            return 0.0
            
        confidence = self._safe_probability(confidence)
        if confidence < self.min_confidence_threshold:
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
            
        # Scale position by confidence
        confidence_range = 1.0 - self.min_confidence_threshold
        if confidence_range > 0:
            scale = (confidence - self.min_confidence_threshold) / confidence_range
        else:
            scale = 1.0
            
        size = base_size * min(1.0, max(0.0, scale))
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
    
    def _build_execution_reason(
        self,
        final_action: str,
        final_confidence: float,
        consensus_score: float,
        consensus_debug: ConsensusDebug,
        hold_reason: Optional[str]
    ) -> str:
        if final_action == "HOLD":
            if hold_reason:
                return hold_reason
            reasons = []
            if final_confidence < self.min_confidence_threshold:
                reasons.append(f"Confidence {final_confidence:.1%} below threshold {self.min_confidence_threshold:.0%}")
            if consensus_debug.conflict_detected:
                reasons.append(f"Conflict detected: {consensus_debug.conflict_type} (severity={consensus_debug.conflict_severity:.2f})")
            if abs(consensus_score) < 0.15:
                reasons.append(f"Weak consensus: {abs(consensus_score):.1%}")
            if consensus_debug.agent_agreement < 0.50:
                reasons.append(f"Poor agent agreement: {consensus_debug.agent_agreement:.1%}")
            if not reasons:
                reasons.append("No clear directional signal")
            return "; ".join(reasons)
        else:
            return f"Executing {final_action} with {final_confidence:.1%} confidence"
    
    def _generate_summary(
        self,
        symbol: str,
        unified_snapshot: UnifiedMarketSnapshot,
        final_action: str,
        final_confidence: float,
        position_size: float,
        consensus_action: str,
        consensus_score: float,
        agent_votes: Dict[str, str],
        stop_loss: Optional[float],
        take_profit: Optional[float],
        execution_reason: Optional[str],
        consensus_debug: Optional[ConsensusDebug],
        hold_reason: Optional[str]
    ) -> str:
        lines = [
            "=== ORCHESTRATOR SUMMARY ===",
            f"Symbol: {symbol}",
            f"Current Price: {unified_snapshot.current_price:.8f}",
            f"Data Quality: {unified_snapshot.data_quality_score:.2%}",
            f"Market Phase: {unified_snapshot.market_phase}",
            f"Missing Data: {unified_snapshot.missing_fields if unified_snapshot.missing_fields else 'None'}",
            "",
            f"Final Action: {final_action}",
            f"Confidence: {final_confidence:.2%}",
            f"Preliminary Position Size: {position_size:.2%}",
            f"Consensus: {consensus_action}",
            f"Consensus Score: {consensus_score:.4f}",
        ]
        
        if execution_reason:
            lines.append(f"Execution Reason: {execution_reason}")
            
        if hold_reason:
            lines.append(f"HOLD Reason: {hold_reason}")
            
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
            lines.append(f"Conflict Type: {consensus_debug.conflict_type}")
            lines.append(f"Conflict Severity: {consensus_debug.conflict_severity:.2f}")
            
            if consensus_debug.agent_scores:
                lines.append("Agent Scores:")
                for agent, score in consensus_debug.agent_scores.items():
                    lines.append(f"  {agent}: {score:.4f}")
                    
            if consensus_debug.agent_weights:
                lines.append("Agent Weights:")
                for agent, weight in consensus_debug.agent_weights.items():
                    lines.append(f"  {agent}: {weight:.4f}")
                    
            if consensus_debug.agent_confidences:
                lines.append("Agent Confidences:")
                for agent, conf in consensus_debug.agent_confidences.items():
                    lines.append(f"  {agent}: {conf:.2%}")
                    
            lines.append(f"Weighted Total: {consensus_debug.weighted_total:.4f}")
            lines.append(f"Available Weight: {consensus_debug.available_weight:.4f}")
            
            if consensus_debug.price_data:
                lines.append("Price Consistency:")
                for key, price in consensus_debug.price_data.items():
                    diff = abs(price - unified_snapshot.current_price) if unified_snapshot.current_price > 0 else 0
                    diff_pct = (diff / unified_snapshot.current_price * 100) if unified_snapshot.current_price > 0 else 0
                    lines.append(f"  {key}: {price:.2f} (diff: {diff_pct:.2f}%)")
            
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
        logger.info("Agent Confidences: %s", debug.agent_confidences)
        logger.info("Weighted Total: %.4f | Available Weight: %.4f", 
                   debug.weighted_total, debug.available_weight)
        logger.info("Consensus: %s (%.4f)", debug.consensus_action, debug.consensus_score)
        logger.info("Agreement: %.2f%% | Direction: %.4f", 
                   debug.agent_agreement * 100, debug.agreement_direction)
        logger.info("Conflict: %s | Type: %s | Severity: %.2f", 
                   debug.conflict_detected, debug.conflict_type, debug.conflict_severity)
        logger.info("Final Action: %s | Confidence: %.2f%%", 
                   debug.final_action, debug.final_confidence * 100)
        logger.info("Price Data: %s", debug.price_data)
        logger.info("Missing Data: %s", debug.missing_data)
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
            unified_snapshot=None,
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
            confidence_components={},
            market_scores={},
            summary=summary,
            execution_reason="Error during analysis",
            hold_reason="Analysis error"
        )
    
    def get_history(self, n: int = 10) -> List[OrchestratorResult]:
        if n <= 0:
            return []
        return self.history[-n:]
