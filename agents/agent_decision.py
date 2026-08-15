"""
Agent 3: Pengambil Keputusan (Decision Maker)
Dengan dukungan Unified Market Data
"""

import os
import logging
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class TradingAction(Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


@dataclass
class DecisionResult:
    symbol: str
    timestamp: datetime
    action: str
    action_score: float
    confidence: float
    sentiment_score: float
    technical_score: float
    risk_score: float
    market_context_score: float
    reasoning: List[str]
    factors_considered: Dict[str, Any]
    alternative_actions: List[str]
    suggested_position_size: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    time_horizon: str
    final_decision: str
    summary: str


class DecisionAgent:
    """
    Agent Pengambil Keputusan dengan Unified Market Data.
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        
        self.weights = {
            'sentiment': 0.30,
            'technical': 0.35,
            'risk': 0.20,
            'market_context': 0.15
        }
        
        self.thresholds = {
            'strong_buy': 0.7,
            'buy': 0.3,
            'hold': 0.3,
            'sell': -0.3,
            'strong_sell': -0.7
        }
        
        self.risk_params = {
            'max_position_size': 0.20,
            'min_confidence': 0.60,
            'daily_loss_limit': 0.05,
            'max_open_positions': 5
        }
        
        self.decision_history = []
        self.max_history = 100
        
        logger.info("Decision Agent initialized with Unified Market Data support")

    def analyze(
        self,
        symbol: str,
        sentiment_result: Any,
        technical_result: Any,
        market_data: Optional[Dict] = None
    ) -> DecisionResult:
        """Main method untuk pengambilan keputusan dengan unified data."""
        logger.info(f"Making trading decision for {symbol}")
        
        symbol = symbol.upper()
        market_data = market_data or {}
        
        try:
            # ============================================================
            # FIX: GUNAKAN UNIFIED PRICE
            # ============================================================
            
            unified_price = market_data.get("unified_price")
            if unified_price is None:
                unified_price = market_data.get("current_price", 0)
            
            try:
                unified_price = float(unified_price)
            except (TypeError, ValueError):
                unified_price = 0
            
            # Extract scores dari agent results
            sentiment_score = self._extract_sentiment_score(sentiment_result)
            technical_score = self._extract_technical_score(technical_result)
            
            # Calculate risk score (gunakan unified data)
            risk_score = self._calculate_risk_score(symbol, market_data)
            
            # Market context (gunakan unified data)
            market_context_score = self._analyze_market_context(market_data)
            
            # Combine factors
            combined_score = self._combine_factors({
                'sentiment': sentiment_score,
                'technical': technical_score,
                'risk': risk_score,
                'market_context': market_context_score
            })
            
            # Determine action
            action, action_score = self._determine_action(combined_score)
            confidence = self._calculate_confidence({
                'sentiment': sentiment_score,
                'technical': technical_score,
                'risk': risk_score,
                'market_context': market_context_score
            })
            
            # Generate reasoning
            reasoning = self._generate_reasoning(
                symbol, action, action_score, confidence,
                sentiment_score, technical_score, risk_score,
                sentiment_result, technical_result
            )
            
            # Position size
            position_size = self._calculate_position_size(
                action_score, confidence, risk_score
            )
            
            # SL/TP menggunakan unified price
            stop_loss, take_profit = self._calculate_stop_loss_take_profit(
                technical_result, action, unified_price
            )
            
            time_horizon = self._determine_time_horizon(
                sentiment_score, technical_score, action
            )
            
            alternatives = self._generate_alternatives(
                combined_score, sentiment_score, technical_score
            )
            
            final_decision = self._build_final_decision(
                action, confidence, position_size, reasoning
            )
            
            result = DecisionResult(
                symbol=symbol,
                timestamp=datetime.now(),
                action=action,
                action_score=action_score,
                confidence=confidence,
                sentiment_score=sentiment_score,
                technical_score=technical_score,
                risk_score=risk_score,
                market_context_score=market_context_score,
                reasoning=reasoning,
                factors_considered={
                    'sentiment_score': sentiment_score,
                    'technical_score': technical_score,
                    'risk_score': risk_score,
                    'market_context_score': market_context_score,
                    'combined_score': combined_score,
                    'unified_price': unified_price
                },
                alternative_actions=alternatives,
                suggested_position_size=position_size,
                stop_loss=stop_loss,
                take_profit=take_profit,
                time_horizon=time_horizon,
                final_decision=final_decision,
                summary=f"Decision for {symbol}: {action} with {confidence:.1%} confidence"
            )
            
            self._save_decision_history(result)
            return result
            
        except Exception as e:
            logger.error(f"Error making decision for {symbol}: {str(e)}")
            return self._get_default_decision(symbol)

    # ============================================================
    # HELPER METHODS (SAMA DENGAN SEBELUMNYA)
    # ============================================================
    
    def _extract_sentiment_score(self, sentiment_result) -> float:
        try:
            if hasattr(sentiment_result, 'overall_score'):
                score = sentiment_result.overall_score
                confidence = getattr(sentiment_result, 'confidence', 0.5)
                return float(score * confidence)
            return 0.0
        except:
            return 0.0
    
    def _extract_technical_score(self, technical_result) -> float:
        try:
            if hasattr(technical_result, 'overall_score'):
                return float(technical_result.overall_score)
            return 0.0
        except:
            return 0.0
    
    def _calculate_risk_score(self, symbol: str, market_data: Dict = None) -> float:
        """Calculate risk score from unified data."""
        risk_factors = []
        
        # Volatility dari unified data
        if market_data and 'volatility' in market_data:
            volatility = market_data['volatility']
            if volatility > 0.05:
                risk_factors.append(-0.3)
            elif volatility < 0.02:
                risk_factors.append(0.2)
            else:
                risk_factors.append(0.0)
        
        # Volume dari unified data
        if market_data and 'volume_24h' in market_data:
            volume = market_data['volume_24h']
            if volume and volume > 0:
                risk_factors.append(0.1)
            else:
                risk_factors.append(-0.1)
        
        # Market phase dari unified data
        if market_data and 'market_phase' in market_data:
            phase = market_data['market_phase']
            if phase == 'BULLISH':
                risk_factors.append(0.2)
            elif phase == 'BEARISH':
                risk_factors.append(-0.2)
            elif phase == 'VOLATILE':
                risk_factors.append(-0.1)
        
        if risk_factors:
            avg_risk = np.mean(risk_factors)
            return float(np.clip(avg_risk, -1.0, 1.0))
        
        return 0.0
    
    def _analyze_market_context(self, market_data: Dict = None) -> float:
        """Analyze market context from unified data."""
        if not market_data:
            return 0.0
        
        context_factors = []
        
        # Market phase
        if 'market_phase' in market_data:
            phase = market_data['market_phase']
            if phase == 'BULLISH':
                context_factors.append(0.3)
            elif phase == 'BEARISH':
                context_factors.append(-0.3)
            elif phase == 'VOLATILE':
                context_factors.append(-0.1)
        
        # Fear & Greed
        if 'fear_greed_index' in market_data:
            fg = market_data['fear_greed_index']
            if fg is not None:
                try:
                    fg_score = (float(fg) - 50) / 50
                    context_factors.append(fg_score * 0.2)
                except (ValueError, TypeError):
                    pass
        
        # Data quality
        if 'data_quality_score' in market_data:
            quality = market_data['data_quality_score']
            if quality is not None:
                try:
                    context_factors.append((float(quality) - 0.5) * 0.2)
                except (ValueError, TypeError):
                    pass
        
        if context_factors:
            return float(np.clip(np.mean(context_factors), -1.0, 1.0))
        
        return 0.0
    
    def _combine_factors(self, factors: Dict[str, float]) -> float:
        total_score = 0.0
        total_weight = 0.0
        for factor, score in factors.items():
            weight = self.weights.get(factor, 0.1)
            total_score += score * weight
            total_weight += weight
        if total_weight > 0:
            return float(np.clip(total_score / total_weight, -1.0, 1.0))
        return 0.0
    
    def _determine_action(self, score: float) -> Tuple[str, float]:
        if score >= self.thresholds['strong_buy']:
            return TradingAction.STRONG_BUY.value, score
        elif score >= self.thresholds['buy']:
            return TradingAction.BUY.value, score
        elif score <= self.thresholds['strong_sell']:
            return TradingAction.STRONG_SELL.value, score
        elif score <= self.thresholds['sell']:
            return TradingAction.SELL.value, score
        else:
            return TradingAction.HOLD.value, score
    
    def _calculate_confidence(self, factors: Dict[str, float]) -> float:
        scores = list(factors.values())
        if not scores:
            return 0.5
        std_dev = np.std(scores)
        consistency = max(0, 1 - std_dev * 2)
        avg_abs_score = np.mean([abs(s) for s in scores])
        strength = min(1, avg_abs_score * 2)
        confidence = consistency * 0.6 + strength * 0.4
        risk_score = factors.get('risk', 0)
        if risk_score < -0.3:
            confidence *= 0.7
        return float(np.clip(confidence, 0.0, 1.0))
    
    def _generate_reasoning(self, symbol, action, action_score, confidence,
                            sentiment_score, technical_score, risk_score,
                            sentiment_result, technical_result) -> List[str]:
        reasoning = []
        if action in ['STRONG_BUY', 'BUY']:
            reasoning.append(f"Keputusan {action} untuk {symbol} dengan score {action_score:.2f}")
            reasoning.append(f"Keyakinan: {confidence:.1%} berdasarkan konsistensi analisis")
        elif action in ['STRONG_SELL', 'SELL']:
            reasoning.append(f"Keputusan {action} untuk {symbol} dengan score {action_score:.2f}")
            reasoning.append(f"Keyakinan: {confidence:.1%} berdasarkan sinyal bearish")
        else:
            reasoning.append(f"Keputusan HOLD untuk {symbol} - Menunggu sinyal yang lebih jelas")
        if abs(sentiment_score) > 0.2:
            label = "bullish" if sentiment_score > 0 else "bearish"
            reasoning.append(f"Sentimen pasar: {label} ({sentiment_score:.2f})")
        if abs(technical_score) > 0.2:
            label = "bullish" if technical_score > 0 else "bearish"
            reasoning.append(f"Analisis teknikal: {label} ({technical_score:.2f})")
        if risk_score < -0.2:
            reasoning.append(f"⚠️ Faktor risiko tinggi ({risk_score:.2f})")
        return reasoning
    
    def _calculate_position_size(self, action_score: float, confidence: float, risk_score: float) -> float:
        base_size = abs(action_score) * confidence * 0.5
        if risk_score > 0.2:
            multiplier = 1.0
        elif risk_score > -0.2:
            multiplier = 0.8
        else:
            multiplier = 0.5
        position_size = base_size * multiplier
        max_size = self.risk_params['max_position_size']
        position_size = min(position_size, max_size)
        if position_size < 0.05:
            position_size = 0.0
        return position_size
    
    def _calculate_stop_loss_take_profit(self, technical_result, action: str, unified_price: float) -> Tuple[Optional[float], Optional[float]]:
        try:
            if unified_price <= 0:
                return None, None
            
            if action in ['STRONG_BUY', 'BUY']:
                support_levels = getattr(technical_result, 'support_levels', [])
                if support_levels:
                    stop_loss = min(support_levels[:2]) * 0.99 if support_levels else unified_price * 0.95
                else:
                    stop_loss = unified_price * 0.95
                resistance_levels = getattr(technical_result, 'resistance_levels', [])
                if resistance_levels:
                    take_profit = max(resistance_levels[:2]) * 1.01 if resistance_levels else unified_price * 1.10
                else:
                    take_profit = unified_price * 1.10
                return stop_loss, take_profit
            elif action in ['STRONG_SELL', 'SELL']:
                resistance_levels = getattr(technical_result, 'resistance_levels', [])
                if resistance_levels:
                    stop_loss = max(resistance_levels[:2]) * 1.01 if resistance_levels else unified_price * 1.05
                else:
                    stop_loss = unified_price * 1.05
                support_levels = getattr(technical_result, 'support_levels', [])
                if support_levels:
                    take_profit = min(support_levels[:2]) * 0.99 if support_levels else unified_price * 0.90
                else:
                    take_profit = unified_price * 0.90
                return stop_loss, take_profit
            return None, None
        except Exception as e:
            logger.error(f"Error calculating SL/TP: {e}")
            return None, None
    
    def _determine_time_horizon(self, sentiment_score: float, technical_score: float, action: str) -> str:
        if abs(sentiment_score) > 0.3 and abs(technical_score) > 0.3:
            if abs(sentiment_score - technical_score) < 0.2:
                return "MEDIUM"
        if abs(technical_score) > abs(sentiment_score):
            return "SHORT"
        if abs(sentiment_score) > abs(technical_score):
            return "MEDIUM"
        return "SHORT"
    
    def _generate_alternatives(self, combined_score, sentiment_score, technical_score) -> List[str]:
        alternatives = []
        if combined_score > 0.3:
            alternatives.append("ALTERNATIF: Scale-in dengan posisi lebih kecil")
        elif combined_score < -0.3:
            alternatives.append("ALTERNATIF: Partial sell - reduce position")
        else:
            if sentiment_score > 0.2:
                alternatives.append("PERTIMBANGAN: Sentimen bullish tapi teknikal netral - wait for breakout")
            elif technical_score > 0.2:
                alternatives.append("PERTIMBANGAN: Teknikal bullish tapi sentimen netral - wait for volume confirmation")
            else:
                alternatives.append("ALTERNATIF: Pindah ke aset lain dengan sinyal lebih jelas")
        return alternatives[:2]
    
    def _build_final_decision(self, action: str, confidence: float, position_size: float, reasoning: List[str]) -> str:
        if confidence < self.risk_params['min_confidence']:
            return f"HOLD - Confidence terlalu rendah ({confidence:.1%})"
        if action == "STRONG_BUY":
            return f"STRONG BUY - {confidence:.1%} confidence, position size: {position_size:.1%}"
        elif action == "BUY":
            return f"BUY - {confidence:.1%} confidence, position size: {position_size:.1%}"
        elif action == "STRONG_SELL":
            return f"STRONG SELL - {confidence:.1%} confidence, position size: {position_size:.1%}"
        elif action == "SELL":
            return f"SELL - {confidence:.1%} confidence, position size: {position_size:.1%}"
        else:
            return "HOLD - Menunggu sinyal yang lebih jelas"
    
    def _save_decision_history(self, decision: DecisionResult):
        self.decision_history.append(decision)
        if len(self.decision_history) > self.max_history:
            self.decision_history.pop(0)
    
    def get_recent_decisions(self, n: int = 10) -> List[DecisionResult]:
        return self.decision_history[-n:]
    
    def _get_default_decision(self, symbol: str) -> DecisionResult:
        return DecisionResult(
            symbol=symbol,
            timestamp=datetime.now(),
            action="HOLD",
            action_score=0.0,
            confidence=0.0,
            sentiment_score=0.0,
            technical_score=0.0,
            risk_score=0.0,
            market_context_score=0.0,
            reasoning=["Unable to make decision - default to HOLD"],
            factors_considered={},
            alternative_actions=["HOLD - Wait for better signals"],
            suggested_position_size=0.0,
            stop_loss=None,
            take_profit=None,
            time_horizon="SHORT",
            final_decision="HOLD - Error in decision making",
            summary="Default HOLD due to analysis error"
        )
