"""
core/orchestrator.py

Orchestrator - AI Decision Coordination Layer
Central coordinator untuk seluruh AI agents dengan Unified Market Data.
Dilengkapi dengan MimicTrader untuk meniru gaya trading trader profesional.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple

from agents.agent_sentiment import SentimentAgent, SentimentResult
from agents.agent_technical import TechnicalAgent, TechnicalResult
from agents.agent_decision import DecisionAgent, DecisionResult
from agents.agent_reflector import ReflectorAgent, ReflectionResult
from agents.agent_forecast import ForecastAgent, ForecastResult

from core.unified_market_data import (
    UnifiedMarketDataProvider,
    UnifiedMarketSnapshot,
    get_market_data_provider,
    get_market_data_for_agent,
    create_snapshot_from_market_data
)

from core.mimic_trader import MimicTrader, BullBearAnalysis

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorResult:
    """Hasil lengkap dari proses analisis Orchestrator."""
    timestamp: datetime
    symbol: str
    current_price: float
    unified_snapshot: Optional[UnifiedMarketSnapshot]
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
    hold_reason: Optional[str] = None
    mimic_analysis: Optional[BullBearAnalysis] = None  # NEW: MimicTrader analysis


class Orchestrator:
    """Central coordinator untuk seluruh AI agents dengan Unified Market Data dan MimicTrader."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

        # ============================================================
        # AGENTS
        # ============================================================

        self.sentiment_agent = SentimentAgent()
        self.technical_agent = TechnicalAgent()
        self.decision_agent = DecisionAgent()
        self.reflector_agent = ReflectorAgent()
        self.forecast_agent = ForecastAgent()

        # ============================================================
        # UNIFIED MARKET DATA
        # ============================================================

        self.market_data_provider = get_market_data_provider(config)
        self.use_unified_data = config.get("use_unified_data", True)

        # ============================================================
        # MIMIC TRADER - Referensi trader profesional
        # ============================================================

        self.mimic_trader = MimicTrader(config.get("mimic_trader", {}))
        self.use_mimic_trader = config.get("use_mimic_trader", True)
        self.mimic_weight = config.get("mimic_weight", 0.25)  # Bobot MimicTrader dalam voting

        # ============================================================
        # VOTING THRESHOLDS
        # ============================================================

        self.voting_thresholds = {
            "strong_buy": 0.65,
            "buy": 0.25,
            "sell": -0.25,
            "strong_sell": -0.65,
        }

        # ============================================================
        # AGENT WEIGHTS
        # ============================================================

        self.agent_weights = {
            "sentiment": 0.18,
            "technical": 0.30,
            "decision": 0.25,
            "forecast": 0.12,
            "mimic_trader": 0.15,  # NEW: MimicTrader weight
        }

        # ============================================================
        # CONFIDENCE THRESHOLDS
        # ============================================================

        self.min_confidence_threshold = float(config.get("min_confidence", 0.40))
        self.high_confidence_threshold = float(config.get("high_confidence", 0.65))

        # ============================================================
        # CONFLICT HANDLING
        # ============================================================

        self.conflict_penalty = float(config.get("conflict_penalty", 0.08))
        self.minor_conflict_penalty = float(config.get("minor_conflict_penalty", 0.03))
        self.severe_conflict_penalty = float(config.get("severe_conflict_penalty", 0.15))

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

        logger.info("Orchestrator initialized with Unified Market Data and MimicTrader")

    # ============================================================
    # PUBLIC ANALYZE
    # ============================================================

    async def analyze(
        self,
        symbol: str,
        market_data: Optional[Dict[str, Any]] = None
    ) -> OrchestratorResult:
        """
        Menjalankan seluruh pipeline dengan Unified Market Snapshot dan MimicTrader.
        """
        logger.info("Starting analysis for %s", symbol)
        symbol = symbol.upper()

        # ============================================================
        # STEP 0: FORCE SIGNAL - Untuk testing pipeline eksekusi
        # ============================================================
        market_data = market_data or {}
        
        force_action = market_data.get("_force_action")
        if force_action and force_action in ["BUY", "SELL", "STRONG_BUY", "STRONG_SELL"]:
            logger.info(f"⚠️ FORCE SIGNAL DETECTED: {force_action} for {symbol}")
            
            current_price = market_data.get("current_price", 0)
            if current_price <= 0:
                current_price = market_data.get("unified_price", 0)
            if current_price <= 0:
                current_price = 60000.0  # fallback
            
            return self._create_forced_result(
                symbol=symbol,
                action=force_action,
                current_price=current_price,
                market_data=market_data
            )

        # ============================================================
        # STEP 1: GET UNIFIED MARKET SNAPSHOT
        # ============================================================

        unified_snapshot = None

        if self.use_unified_data:
            # Try to get from provider or refresh
            unified_snapshot = self.market_data_provider.get_snapshot(symbol)
            if unified_snapshot is None or unified_snapshot.is_stale(60):
                unified_snapshot = self.market_data_provider.refresh_snapshot(
                    symbol=symbol,
                    timeframe=market_data.get("timeframe", "1h"),
                    limit=100
                )

            # If still None, create from market_data
            if unified_snapshot is None:
                unified_snapshot = create_snapshot_from_market_data(
                    self.market_data_provider,
                    symbol,
                    market_data
                )

            # Inject unified data into market_data
            market_data["current_price"] = unified_snapshot.current_price
            market_data["unified_price"] = unified_snapshot.current_price
            market_data["_unified_snapshot"] = unified_snapshot
            market_data["timestamp"] = unified_snapshot.timestamp

        try:
            # ============================================================
            # STEP 2: RUN AGENTS
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
            # STEP 3: CURRENT PRICE
            # ============================================================

            current_price = self._get_current_price(market_data, technical_result, forecast_result)

            # ============================================================
            # STEP 4: MIMIC TRADER ANALYSIS
            # ============================================================
            
            mimic_analysis = None
            mimic_score = 0.0
            mimic_action = "HOLD"
            mimic_confidence = 0.0
            
            if self.use_mimic_trader:
                # Build market data for MimicTrader
                mimic_market_data = {
                    "current_price": current_price,
                    "technical_score": self._extract_technical_score(technical_result),
                    "sentiment_score": self._extract_sentiment_score(sentiment_result),
                    "momentum_score": self._calculate_momentum_score(technical_result, current_price),
                    "support_levels": self._extract_support_levels(technical_result),
                    "resistance_levels": self._extract_resistance_levels(technical_result),
                    "detected_patterns": self._extract_patterns(technical_result),
                    "volatility": market_data.get("volatility", 0.02),
                    "data_quality": unified_snapshot.data_quality_score if unified_snapshot else 0.7,
                }
                
                mimic_analysis = self.mimic_trader.analyze(symbol, mimic_market_data)
                
                # Convert to score
                if mimic_analysis.recommendation == "STRONG_BUY":
                    mimic_score = 0.85
                    mimic_action = "STRONG_BUY"
                elif mimic_analysis.recommendation == "BUY":
                    mimic_score = 0.50
                    mimic_action = "BUY"
                elif mimic_analysis.recommendation == "STRONG_SELL":
                    mimic_score = -0.85
                    mimic_action = "STRONG_SELL"
                elif mimic_analysis.recommendation == "SELL":
                    mimic_score = -0.50
                    mimic_action = "SELL"
                else:
                    mimic_score = 0.0
                    mimic_action = "HOLD"
                
                mimic_confidence = mimic_analysis.confidence
                
                logger.info("MimicTrader: %s (bull=%.2f, bear=%.2f, net=%.2f, conf=%.2f)",
                           mimic_action, 
                           mimic_analysis.bull_score if mimic_analysis else 0,
                           mimic_analysis.bear_score if mimic_analysis else 0,
                           mimic_analysis.net_score if mimic_analysis else 0,
                           mimic_confidence)

            # ============================================================
            # STEP 5: PERFORM VOTING (dengan MimicTrader)
            # ============================================================

            consensus_action, consensus_score = self._perform_voting(
                sentiment=sentiment_result,
                technical=technical_result,
                decision=decision_result,
                forecast=forecast_result,
                mimic_score=mimic_score,
                mimic_confidence=mimic_confidence
            )

            # ============================================================
            # STEP 6: AGENT VOTES (dengan MimicTrader)
            # ============================================================

            agent_votes = self._get_agent_votes(
                sentiment=sentiment_result,
                technical=technical_result,
                decision=decision_result,
                forecast=forecast_result,
                mimic_action=mimic_action
            )

            # ============================================================
            # STEP 7: FINAL DECISION
            # ============================================================

            final_action, final_confidence, decision_score, confidence_components, hold_reason = \
                self._determine_final_decision_enhanced(
                    decision=decision_result,
                    consensus_action=consensus_action,
                    consensus_score=consensus_score,
                    sentiment=sentiment_result,
                    technical=technical_result,
                    forecast=forecast_result,
                    agent_votes=agent_votes,
                    mimic_analysis=mimic_analysis
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
                    current_price=current_price,
                    mimic_analysis=mimic_analysis
                )

            # ============================================================
            # STEP 10: MARKET SCORES
            # ============================================================

            market_scores = self._build_market_scores(
                sentiment=sentiment_result,
                technical=technical_result,
                decision=decision_result,
                forecast=forecast_result,
                consensus_score=consensus_score,
                mimic_score=mimic_score
            )

            # ============================================================
            # STEP 11: EXECUTION REASON
            # ============================================================

            execution_reason = self._build_execution_reason(
                final_action=final_action,
                final_confidence=final_confidence,
                consensus_score=consensus_score,
                hold_reason=hold_reason,
                mimic_analysis=mimic_analysis
            )

            # ============================================================
            # STEP 12: SUMMARY
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
                hold_reason=hold_reason,
                mimic_analysis=mimic_analysis
            )

            # ============================================================
            # STEP 13: BUILD RESULT
            # ============================================================

            result = OrchestratorResult(
                timestamp=datetime.now(timezone.utc),
                symbol=symbol,
                current_price=current_price,
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
                decision_score=decision_score,
                confidence_components=confidence_components,
                market_scores=market_scores,
                summary=summary,
                execution_reason=execution_reason,
                hold_reason=hold_reason,
                mimic_analysis=mimic_analysis
            )

            # ============================================================
            # STEP 14: SAVE HISTORY
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
    # FORCE RESULT
    # ============================================================

    def _create_forced_result(
        self,
        symbol: str,
        action: str,
        current_price: float,
        market_data: Dict[str, Any]
    ) -> OrchestratorResult:
        """
        Create forced result untuk testing pipeline eksekusi.
        """
        timestamp = datetime.now(timezone.utc)
        
        action = action.upper()
        is_buy = action in ["BUY", "STRONG_BUY"]
        is_sell = action in ["SELL", "STRONG_SELL"]
        
        confidence = 0.85
        position_size = 0.08
        score = 0.85 if is_buy else -0.85
        
        agent_votes = {
            "sentiment": action,
            "technical": action,
            "decision": action,
            "forecast": action,
        }
        
        stop_loss = None
        take_profit = None
        if current_price > 0:
            if is_buy:
                stop_loss = current_price * 0.95
                take_profit = current_price * 1.05
            elif is_sell:
                stop_loss = current_price * 1.05
                take_profit = current_price * 0.95
        
        summary = (
            f"=== FORCED SIGNAL ===\n"
            f"Symbol: {symbol}\n"
            f"Action: {action}\n"
            f"Confidence: {confidence:.2%}\n"
            f"Position Size: {position_size:.2%}\n"
            f"This is a forced test signal for pipeline validation."
        )
        
        return OrchestratorResult(
            timestamp=timestamp,
            symbol=symbol,
            current_price=current_price,
            unified_snapshot=None,
            sentiment=None,
            technical=None,
            decision=None,
            reflection=None,
            forecast=None,
            consensus_action=action,
            consensus_score=score,
            agent_votes=agent_votes,
            final_action=action,
            final_confidence=confidence,
            position_size=position_size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            decision_score=score,
            confidence_components={
                "decision_confidence": confidence,
                "consensus_strength": 0.85,
                "agent_agreement": 1.0,
                "agreement_direction": score,
                "combined_score": score,
            },
            market_scores={
                "sentiment": score,
                "technical": score,
                "decision": score,
                "forecast": score,
                "consensus": score,
            },
            summary=summary,
            execution_reason=f"FORCED SIGNAL: {action}",
            hold_reason=None,
            mimic_analysis=None
        )

    # ============================================================
    # AGENT RUNNERS
    # ============================================================

    async def _run_base_agents(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        unified_snapshot: Optional[UnifiedMarketSnapshot]
    ) -> Tuple[Optional[SentimentResult], Optional[TechnicalResult]]:
        """Run Sentiment + Technical agents with unified data."""
        # Inject unified data
        if unified_snapshot:
            market_data["current_price"] = unified_snapshot.current_price
            market_data["_unified_snapshot"] = unified_snapshot

        tasks = [
            asyncio.to_thread(self.sentiment_agent.analyze, symbol, market_data),
            asyncio.to_thread(self.technical_agent.analyze, symbol, market_data),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        sentiment_result = None
        technical_result = None

        if len(results) > 0 and not isinstance(results[0], Exception):
            sentiment_result = results[0]
            if unified_snapshot and hasattr(sentiment_result, "current_price"):
                sentiment_result.current_price = unified_snapshot.current_price
        else:
            logger.error("Sentiment agent failed: %s", results[0] if results else "Unknown")

        if len(results) > 1 and not isinstance(results[1], Exception):
            technical_result = results[1]
            if unified_snapshot and hasattr(technical_result, "current_price"):
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
        unified_snapshot: Optional[UnifiedMarketSnapshot]
    ) -> Optional[DecisionResult]:
        """Run Decision agent."""
        try:
            if unified_snapshot:
                market_data["current_price"] = unified_snapshot.current_price

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
        unified_snapshot: Optional[UnifiedMarketSnapshot]
    ) -> Optional[ForecastResult]:
        """Run Forecast agent."""
        try:
            if unified_snapshot:
                market_data["current_price"] = unified_snapshot.current_price

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
        unified_snapshot: Optional[UnifiedMarketSnapshot]
    ) -> Optional[ReflectionResult]:
        """Run Reflector agent."""
        try:
            trades = market_data.get("recent_trades", [])
            if trades is None or not isinstance(trades, list):
                trades = []

            result = await asyncio.to_thread(
                self.reflector_agent.analyze,
                symbol, trades, None
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
        forecast: Optional[ForecastResult],
        mimic_score: float = 0.0,
        mimic_confidence: float = 0.0
    ) -> Tuple[str, float]:
        """Weighted consensus with MimicTrader."""
        weighted_total = 0.0
        available_weight = 0.0

        if sentiment is not None:
            score = self._safe_score(getattr(sentiment, "overall_score", 0.0))
            weight = self.agent_weights["sentiment"]
            weighted_total += score * weight
            available_weight += weight

        if technical is not None:
            score = self._safe_score(getattr(technical, "overall_score", 0.0))
            weight = self.agent_weights["technical"]
            weighted_total += score * weight
            available_weight += weight

        if decision is not None:
            score = self._safe_score(getattr(decision, "action_score", 0.0))
            weight = self.agent_weights["decision"]
            weighted_total += score * weight
            available_weight += weight

        if forecast is not None:
            score = self._forecast_to_score(forecast)
            weight = self.agent_weights["forecast"]
            weighted_total += score * weight
            available_weight += weight

        # MimicTrader
        if self.use_mimic_trader and abs(mimic_score) > 0.01:
            # Weight adjusted by confidence
            weight = self.agent_weights["mimic_trader"] * (0.3 + 0.7 * mimic_confidence)
            weighted_total += mimic_score * weight
            available_weight += weight
            logger.debug("MimicTrader vote: score=%.3f, weight=%.3f", mimic_score, weight)

        if available_weight <= 0:
            return ("HOLD", 0.0)

        consensus_score = self._safe_score(weighted_total / available_weight)
        consensus_action = self._score_to_action(consensus_score)

        return (consensus_action, consensus_score)

    # ============================================================
    # FINAL DECISION
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
        mimic_analysis: Optional[BullBearAnalysis] = None
    ) -> Tuple[str, float, float, Dict[str, float], Optional[str]]:
        """Enhanced final decision with MimicTrader integration."""
        reasoning = []
        hold_reason = None

        # Extract scores
        if decision is not None:
            decision_score = self._safe_score(getattr(decision, "action_score", 0.0))
            decision_confidence = self._safe_probability(getattr(decision, "confidence", 0.5))
        else:
            decision_score = 0.0
            decision_confidence = 0.0

        consensus_score = self._safe_score(consensus_score)
        consensus_strength = abs(consensus_score)

        agreement = self._calculate_agent_agreement(agent_votes)
        agreement_direction = self._agreement_direction(agent_votes)

        technical_score = 0.0
        if technical is not None:
            technical_score = self._safe_score(getattr(technical, "overall_score", 0.0))

        sentiment_score = 0.0
        if sentiment is not None:
            sentiment_score = self._safe_score(getattr(sentiment, "overall_score", 0.0))

        # ============================================================
        # MIMIC TRADER INTEGRATION
        # ============================================================
        
        mimic_boost = 0.0
        if mimic_analysis and self.use_mimic_trader:
            # If MimicTrader agrees with consensus, boost confidence
            if mimic_analysis.recommendation == consensus_action:
                mimic_boost = 0.10 * mimic_analysis.confidence
                reasoning.append(f"MimicTrader agrees with {consensus_action} (conf={mimic_analysis.confidence:.2%})")
            # If MimicTrader strongly disagrees, apply small penalty
            elif mimic_analysis.recommendation in ["STRONG_BUY", "STRONG_SELL"]:
                mimic_boost = -0.05 * mimic_analysis.confidence
                reasoning.append(f"MimicTrader strong disagreement: {mimic_analysis.recommendation}")

        # Combined score
        if decision is not None and consensus_action != "HOLD":
            combined_score = (
                decision_score * 0.35 +
                consensus_score * 0.25 +
                agreement_direction * 0.20 +
                technical_score * 0.10 +
                sentiment_score * 0.05 +
                mimic_boost * 0.05
            )
        else:
            combined_score = consensus_score + mimic_boost * 0.1

        combined_score = self._safe_score(combined_score)
        final_action = self._score_to_action(combined_score)

        # Confidence
        if decision is not None:
            raw_confidence = (
                decision_confidence * 0.25 +
                consensus_strength * 0.20 +
                agreement * 0.20 +
                abs(agreement_direction) * 0.15 +
                min(1.0, abs(combined_score) * 2.0) * 0.10 +
                mimic_boost * 0.10
            )
        else:
            raw_confidence = (
                consensus_strength * 0.30 +
                agreement * 0.25 +
                abs(agreement_direction) * 0.20 +
                min(1.0, abs(combined_score) * 2.0) * 0.15 +
                mimic_boost * 0.10
            )

        # Conflict penalty
        if final_action != "HOLD" and agreement < 0.75:
            raw_confidence *= (1.0 - self.conflict_penalty)

        final_confidence = max(0.0, min(1.0, raw_confidence))

        # HOLD validation
        if final_action == "HOLD":
            if final_confidence < self.min_confidence_threshold:
                hold_reason = f"Confidence {final_confidence:.1%} below threshold"
            elif abs(consensus_score) < 0.15:
                hold_reason = f"Weak consensus: {abs(consensus_score):.1%}"
            elif agreement < 0.50:
                hold_reason = f"Poor agreement: {agreement:.1%}"
            else:
                hold_reason = "No clear directional signal"

        if final_confidence < self.min_confidence_threshold and final_action != "HOLD":
            final_action = "HOLD"
            combined_score = 0.0
            hold_reason = f"Confidence {final_confidence:.1%} below threshold"

        confidence_components = {
            "decision_confidence": round(decision_confidence, 4),
            "consensus_strength": round(consensus_strength, 4),
            "agent_agreement": round(agreement, 4),
            "agreement_direction": round(agreement_direction, 4),
            "combined_score": round(combined_score, 4),
            "mimic_boost": round(mimic_boost, 4),
        }

        return (final_action, final_confidence, combined_score, confidence_components, hold_reason)

    # ============================================================
    # HELPER METHODS
    # ============================================================

    def _extract_technical_score(self, technical: Optional[TechnicalResult]) -> float:
        """Extract technical score for MimicTrader."""
        if technical is None:
            return 0.0
        return self._safe_score(getattr(technical, "overall_score", 0.0))

    def _extract_sentiment_score(self, sentiment: Optional[SentimentResult]) -> float:
        """Extract sentiment score for MimicTrader."""
        if sentiment is None:
            return 0.0
        return self._safe_score(getattr(sentiment, "overall_score", 0.0))

    def _calculate_momentum_score(self, technical: Optional[TechnicalResult], current_price: float) -> float:
        """Calculate momentum score for MimicTrader."""
        if technical is None or current_price <= 0:
            return 0.0
        
        # Try to get from technical indicators
        moving_averages = getattr(technical, "moving_averages", {})
        if moving_averages and "MA20" in moving_averages:
            ma20 = moving_averages["MA20"]
            if ma20 > 0:
                momentum = (current_price - ma20) / ma20
                return self._safe_score(momentum * 5)  # Scale to -1 to 1
        
        # Try RSI
        rsi = getattr(technical, "rsi", 50.0)
        if rsi:
            return (rsi - 50) / 50  # -1 to 1
        
        return 0.0

    def _extract_support_levels(self, technical: Optional[TechnicalResult]) -> List[float]:
        """Extract support levels for MimicTrader."""
        if technical is None:
            return []
        levels = getattr(technical, "support_levels", [])
        if isinstance(levels, list):
            return levels
        return []

    def _extract_resistance_levels(self, technical: Optional[TechnicalResult]) -> List[float]:
        """Extract resistance levels for MimicTrader."""
        if technical is None:
            return []
        levels = getattr(technical, "resistance_levels", [])
        if isinstance(levels, list):
            return levels
        return []

    def _extract_patterns(self, technical: Optional[TechnicalResult]) -> List[Dict]:
        """Extract detected patterns for MimicTrader."""
        if technical is None:
            return []
        patterns = getattr(technical, "detected_patterns", [])
        if isinstance(patterns, list):
            return patterns
        return []

    def _get_agent_votes(
        self,
        sentiment: Optional[SentimentResult],
        technical: Optional[TechnicalResult],
        decision: Optional[DecisionResult],
        forecast: Optional[ForecastResult],
        mimic_action: str = "HOLD"
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
        
        # MimicTrader vote
        if self.use_mimic_trader and mimic_action != "HOLD":
            votes["mimic_trader"] = mimic_action

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
        if value != value:  # NaN
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
        if value != value:  # NaN
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
        # From market data
        if market_data:
            for key in ["current_price", "price", "last_price", "close", "unified_price"]:
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
        consensus_score: float,
        mimic_score: float = 0.0
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
        if self.use_mimic_trader:
            scores["mimic_trader"] = round(mimic_score, 4)
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
        current_price: float,
        mimic_analysis: Optional[BullBearAnalysis] = None
    ) -> Tuple[Optional[float], Optional[float]]:
        """Calculate SL/TP dengan MimicTrader multi-target jika tersedia."""
        # Gunakan MimicTrader TP levels jika tersedia
        if mimic_analysis and mimic_analysis.take_profit_levels and len(mimic_analysis.take_profit_levels) > 0:
            # Gunakan TP level pertama dari MimicTrader
            tp_levels = mimic_analysis.take_profit_levels
            if action in {"BUY", "STRONG_BUY"}:
                stop_loss = mimic_analysis.stop_loss if mimic_analysis.stop_loss else current_price * 0.95
                # Ambil TP level pertama sebagai TP utama (bisa di-expand nanti)
                take_profit = tp_levels[0] if tp_levels else current_price * 1.05
                return stop_loss, take_profit
            elif action in {"SELL", "STRONG_SELL"}:
                stop_loss = mimic_analysis.stop_loss if mimic_analysis.stop_loss else current_price * 1.05
                take_profit = tp_levels[0] if tp_levels else current_price * 0.95
                return stop_loss, take_profit

        # Fallback ke existing logic
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
        hold_reason: Optional[str],
        mimic_analysis: Optional[BullBearAnalysis] = None
    ) -> str:
        reasons = []
        
        if final_action == "HOLD":
            if hold_reason:
                return hold_reason
            if final_confidence < self.min_confidence_threshold:
                reasons.append(f"Confidence {final_confidence:.1%} below threshold")
            if abs(consensus_score) < 0.15:
                reasons.append(f"Weak consensus: {abs(consensus_score):.1%}")
            if not reasons:
                reasons.append("No clear directional signal")
            return "; ".join(reasons)
        
        # BUY/SELL reason
        reasons.append(f"Executing {final_action} with {final_confidence:.1%} confidence")
        
        if mimic_analysis and self.use_mimic_trader:
            reasons.append(f"MimicTrader: {mimic_analysis.recommendation} (bull={mimic_analysis.bull_score:.2f}, bear={mimic_analysis.bear_score:.2f})")
        
        return " | ".join(reasons)

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
        hold_reason: Optional[str],
        mimic_analysis: Optional[BullBearAnalysis] = None
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

        # MimicTrader analysis
        if mimic_analysis and self.use_mimic_trader:
            lines.append("")
            lines.append("--- MIMIC TRADER ANALYSIS ---")
            lines.append(f"Bull Case: {mimic_analysis.bull_score:.2%}")
            lines.append(f"Bear Case: {mimic_analysis.bear_score:.2%}")
            lines.append(f"Net Score: {mimic_analysis.net_score:.2f}")
            lines.append(f"Recommendation: {mimic_analysis.recommendation}")
            lines.append(f"Confidence: {mimic_analysis.confidence:.2%}")
            if mimic_analysis.suggested_position:
                lines.append(f"Suggested Position: {mimic_analysis.suggested_position:.2%}")
            if mimic_analysis.bull_factors:
                lines.append("Bull Factors:")
                for factor in mimic_analysis.bull_factors[:3]:
                    lines.append(f"  + {factor}")
            if mimic_analysis.bear_factors:
                lines.append("Bear Factors:")
                for factor in mimic_analysis.bear_factors[:3]:
                    lines.append(f"  - {factor}")
            if mimic_analysis.take_profit_levels:
                lines.append(f"TP Levels: {', '.join([f'{tp:.2f}' for tp in mimic_analysis.take_profit_levels[:3]])}")

        lines.append("")
        lines.append("NOTE: Position size and SL/TP are preliminary only.")
        lines.append("Risk Engine must validate them before execution.")

        return "\n".join(lines)

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
            hold_reason="Analysis error",
            mimic_analysis=None
        )

    def get_history(self, n: int = 10) -> List[OrchestratorResult]:
        if n <= 0:
            return []
        return self.history[-n:]
