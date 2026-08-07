"""
Agent 3: Pengambil Keputusan (Decision Maker)
Bertugas menggabungkan hasil analisis dari Sentiment Agent dan Technical Agent,
serta memutuskan action trading berdasarkan berbagai faktor.

Agent ini adalah "otak" utama yang mengkonsolidasi semua analisis
menjadi keputusan trading yang solid.
"""

import os
import logging
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
import json
from enum import Enum

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TradingAction(Enum):
    """Trading actions yang tersedia"""
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"

@dataclass
class DecisionResult:
    """Data class untuk hasil keputusan trading"""
    symbol: str
    timestamp: datetime
    action: str  # STRONG_BUY, BUY, HOLD, SELL, STRONG_SELL
    action_score: float  # -1 to 1 (strong sell to strong buy)
    confidence: float  # 0 to 1
    
    # Breakdown dari masing-masing agent
    sentiment_score: float
    technical_score: float
    risk_score: float
    market_context_score: float
    
    # Detail decision
    reasoning: List[str]
    factors_considered: Dict[str, Any]
    alternative_actions: List[str]
    
    # Trading parameters
    suggested_position_size: float  # 0 to 1 (percentage of portfolio)
    stop_loss: Optional[float]
    take_profit: Optional[float]
    time_horizon: str  # SHORT, MEDIUM, LONG
    
    # Final decision
    final_decision: str
    summary: str

class DecisionAgent:
    """
    Agent Pengambil Keputusan dengan multi-factor analysis
    """
    
    def __init__(self, config: Dict = None):
        """
        Initialize Decision Agent
        
        Args:
            config: Konfigurasi untuk agent
        """
        self.config = config or {}
        
        # Weight untuk berbagai faktor
        self.weights = {
            'sentiment': 0.30,
            'technical': 0.35,
            'risk': 0.20,
            'market_context': 0.15
        }
        
        # Threshold untuk action
        self.thresholds = {
            'strong_buy': 0.7,
            'buy': 0.3,
            'hold': 0.3,
            'sell': -0.3,
            'strong_sell': -0.7
        }
        
        # Risk management parameters
        self.risk_params = {
            'max_position_size': 0.20,  # Max 20% of portfolio per trade
            'min_confidence': 0.60,      # Minimum confidence to trade
            'daily_loss_limit': 0.05,    # Max 5% daily loss
            'max_open_positions': 5
        }
        
        # Cache untuk keputusan sebelumnya
        self.decision_history = []
        self.max_history = 100
        
        logger.info("Decision Agent initialized successfully")
    
    def analyze(self, symbol: str, 
                sentiment_result: Any, 
                technical_result: Any,
                market_data: Dict = None) -> DecisionResult:
        """
        Main method untuk pengambilan keputusan
        
        Args:
            symbol: Simbol aset
            sentiment_result: Hasil dari Sentiment Agent
            technical_result: Hasil dari Technical Agent
            market_data: Data pasar tambahan
        
        Returns:
            DecisionResult: Keputusan trading final
        """
        logger.info(f"Making trading decision for {symbol}")
        
        try:
            # 1. Extract scores dari agent results
            sentiment_score = self._extract_sentiment_score(sentiment_result)
            technical_score = self._extract_technical_score(technical_result)
            
            # 2. Calculate risk score
            risk_score = self._calculate_risk_score(symbol, market_data)
            
            # 3. Analyze market context
            market_context_score = self._analyze_market_context(market_data)
            
            # 4. Combine all factors
            combined_score = self._combine_factors({
                'sentiment': sentiment_score,
                'technical': technical_score,
                'risk': risk_score,
                'market_context': market_context_score
            })
            
            # 5. Determine action
            action, action_score = self._determine_action(combined_score)
            confidence = self._calculate_confidence({
                'sentiment': sentiment_score,
                'technical': technical_score,
                'risk': risk_score,
                'market_context': market_context_score
            })
            
            # 6. Generate reasoning
            reasoning = self._generate_reasoning(
                symbol, action, action_score, confidence,
                sentiment_score, technical_score, risk_score,
                sentiment_result, technical_result
            )
            
            # 7. Calculate position size dan risk parameters
            position_size = self._calculate_position_size(
                action_score, confidence, risk_score
            )
            stop_loss, take_profit = self._calculate_stop_loss_take_profit(
                symbol, technical_result, action
            )
            time_horizon = self._determine_time_horizon(
                sentiment_score, technical_score, action
            )
            
            # 8. Consider alternatives
            alternatives = self._generate_alternatives(
                combined_score, sentiment_score, technical_score
            )
            
            # 9. Build final decision
            final_decision = self._build_final_decision(
                action, confidence, position_size, reasoning
            )
            
            # 10. Create result
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
                    'combined_score': combined_score
                },
                alternative_actions=alternatives,
                suggested_position_size=position_size,
                stop_loss=stop_loss,
                take_profit=take_profit,
                time_horizon=time_horizon,
                final_decision=final_decision,
                summary=f"Decision for {symbol}: {action} with {confidence:.1%} confidence"
            )
            
            # Save to history
            self._save_decision_history(result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error making decision for {symbol}: {str(e)}")
            return self._get_default_decision(symbol)
    
    def _extract_sentiment_score(self, sentiment_result: Any) -> float:
        """
        Extract sentiment score dari Sentiment Agent result
        """
        try:
            if hasattr(sentiment_result, 'overall_score'):
                score = sentiment_result.overall_score
                # Adjust by confidence
                confidence = getattr(sentiment_result, 'confidence', 0.5)
                return score * confidence
            return 0.0
        except:
            return 0.0
    
    def _extract_technical_score(self, technical_result: Any) -> float:
        """
        Extract technical score dari Technical Agent result
        """
        try:
            if hasattr(technical_result, 'overall_score'):
                return technical_result.overall_score
            return 0.0
        except:
            return 0.0
    
    def _calculate_risk_score(self, symbol: str, market_data: Dict = None) -> float:
        """
        Calculate risk score berdasarkan market conditions
        
        Returns:
            float: -1 (high risk) to 1 (low risk)
        """
        try:
            risk_factors = []
            
            # 1. Volatility risk
            if market_data and 'volatility' in market_data:
                volatility = market_data['volatility']
                if volatility > 0.05:  # High volatility
                    risk_factors.append(-0.3)
                elif volatility < 0.02:
                    risk_factors.append(0.2)
                else:
                    risk_factors.append(0.0)
            
            # 2. Liquidity risk
            if market_data and 'volume' in market_data:
                volume = market_data['volume']
                avg_volume = market_data.get('avg_volume', volume)
                if volume < avg_volume * 0.5:
                    risk_factors.append(-0.2)
                elif volume > avg_volume * 1.5:
                    risk_factors.append(0.1)
                else:
                    risk_factors.append(0.0)
            
            # 3. Market condition
            if market_data and 'market_condition' in market_data:
                condition = market_data['market_condition']
                if condition == 'BEAR_MARKET':
                    risk_factors.append(-0.3)
                elif condition == 'BULL_MARKET':
                    risk_factors.append(0.2)
                else:
                    risk_factors.append(0.0)
            
            # 4. Time of day risk
            current_hour = datetime.now().hour
            if current_hour < 6 or current_hour > 22:  # Low liquidity hours
                risk_factors.append(-0.1)
            
            # 5. News risk (if any significant news)
            if market_data and 'major_news' in market_data:
                if market_data['major_news']:
                    risk_factors.append(-0.2)
            
            # Average semua risk factors
            if risk_factors:
                avg_risk = np.mean(risk_factors)
                return np.clip(avg_risk, -1.0, 1.0)
            
            return 0.0
            
        except Exception as e:
            logger.error(f"Error calculating risk score: {e}")
            return 0.0
    
    def _analyze_market_context(self, market_data: Dict = None) -> float:
        """
        Analyze broader market context
        
        Returns:
            float: -1 to 1
        """
        try:
            if not market_data:
                return 0.0
            
            # Market context indicators
            context_score = 0.0
            context_factors = []
            
            # 1. Overall market trend
            if 'market_trend' in market_data:
                trend = market_data['market_trend']
                if trend == 'STRONG_UP':
                    context_factors.append(0.4)
                elif trend == 'UP':
                    context_factors.append(0.2)
                elif trend == 'SIDEWAYS':
                    context_factors.append(0.0)
                elif trend == 'DOWN':
                    context_factors.append(-0.2)
                elif trend == 'STRONG_DOWN':
                    context_factors.append(-0.4)
            
            # 2. Market sentiment (fear/greed)
            if 'fear_greed' in market_data:
                fg = market_data['fear_greed']
                # Map 0-100 to -1 to 1
                fg_score = (fg - 50) / 50
                context_factors.append(fg_score * 0.3)
            
            # 3. Sector performance
            if 'sector_performance' in market_data:
                sector = market_data['sector_performance']
                if sector > 0.02:  # Outperforming
                    context_factors.append(0.2)
                elif sector < -0.02:
                    context_factors.append(-0.2)
                else:
                    context_factors.append(0.0)
            
            if context_factors:
                context_score = np.mean(context_factors)
                return np.clip(context_score, -1.0, 1.0)
            
            return 0.0
            
        except Exception as e:
            logger.error(f"Error analyzing market context: {e}")
            return 0.0
    
    def _combine_factors(self, factors: Dict[str, float]) -> float:
        """
        Combine semua faktor dengan weight masing-masing
        """
        total_score = 0.0
        total_weight = 0.0
        
        for factor, score in factors.items():
            weight = self.weights.get(factor, 0.1)
            total_score += score * weight
            total_weight += weight
        
        if total_weight > 0:
            return np.clip(total_score / total_weight, -1.0, 1.0)
        return 0.0
    
    def _determine_action(self, score: float) -> Tuple[str, float]:
        """
        Determine trading action berdasarkan score
        
        Returns:
            Tuple of (action, action_score)
        """
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
        """
        Calculate confidence level based on consistency of factors
        """
        scores = list(factors.values())
        
        if not scores:
            return 0.5
        
        # 1. Consistency: lower standard deviation = higher confidence
        std_dev = np.std(scores)
        consistency = max(0, 1 - std_dev * 2)  # Scale
        
        # 2. Average absolute score: higher = more confident
        avg_abs_score = np.mean([abs(s) for s in scores])
        strength = min(1, avg_abs_score * 2)
        
        # 3. Weighted confidence
        confidence = (consistency * 0.6 + strength * 0.4)
        
        # 4. Cap berdasarkan risk
        risk_score = factors.get('risk', 0)
        if risk_score < -0.3:  # High risk reduces confidence
            confidence *= 0.7
        
        return np.clip(confidence, 0.0, 1.0)
    
    def _generate_reasoning(self, symbol: str, action: str, action_score: float,
                           confidence: float, sentiment_score: float,
                           technical_score: float, risk_score: float,
                           sentiment_result: Any, technical_result: Any) -> List[str]:
        """
        Generate detailed reasoning untuk keputusan
        """
        reasoning = []
        
        # 1. Overall reasoning
        if action in ['STRONG_BUY', 'BUY']:
            reasoning.append(f"Keputusan {action} untuk {symbol} dengan score {action_score:.2f}")
            reasoning.append(f"Keyakinan: {confidence:.1%} berdasarkan konsistensi analisis")
        elif action in ['STRONG_SELL', 'SELL']:
            reasoning.append(f"Keputusan {action} untuk {symbol} dengan score {action_score:.2f}")
            reasoning.append(f"Keyakinan: {confidence:.1%} berdasarkan sinyal bearish")
        else:
            reasoning.append(f"Keputusan HOLD untuk {symbol} - Menunggu sinyal yang lebih jelas")
        
        # 2. Sentiment reasoning
        if abs(sentiment_score) > 0.2:
            sentiment_label = "bullish" if sentiment_score > 0 else "bearish"
            reasoning.append(f"Sentimen pasar: {sentiment_label} ({sentiment_score:.2f})")
            
            # Extract key events dari sentiment
            if hasattr(sentiment_result, 'key_events') and sentiment_result.key_events:
                events = sentiment_result.key_events[:2]
                reasoning.append(f"Event kunci: {', '.join(events)}")
        
        # 3. Technical reasoning
        if abs(technical_score) > 0.2:
            tech_label = "bullish" if technical_score > 0 else "bearish"
            reasoning.append(f"Analisis teknikal: {tech_label} ({technical_score:.2f})")
            
            # Extract patterns
            if hasattr(technical_result, 'detected_patterns') and technical_result.detected_patterns:
                top_pattern = technical_result.detected_patterns[0]
                reasoning.append(f"Pola terdeteksi: {top_pattern['name']} ({top_pattern['signal']})")
            
            # Support/Resistance
            if hasattr(technical_result, 'current_position'):
                reasoning.append(f"Posisi harga: {technical_result.current_position}")
        
        # 4. Risk reasoning
        if risk_score < -0.2:
            reasoning.append(f"⚠️ Faktor risiko tinggi ({risk_score:.2f}) - Perhatikan manajemen risiko")
        elif risk_score > 0.2:
            reasoning.append(f"✅ Faktor risiko rendah ({risk_score:.2f}) - Kondisi mendukung")
        
        return reasoning
    
    def _calculate_position_size(self, action_score: float, 
                                 confidence: float, risk_score: float) -> float:
        """
        Calculate suggested position size
        """
        # Base size berdasarkan confidence dan action score
        base_size = abs(action_score) * confidence * 0.5
        
        # Adjust berdasarkan risk
        if risk_score > 0.2:
            size_multiplier = 1.0
        elif risk_score > -0.2:
            size_multiplier = 0.8
        else:
            size_multiplier = 0.5
        
        position_size = base_size * size_multiplier
        
        # Apply max position size
        max_size = self.risk_params['max_position_size']
        position_size = min(position_size, max_size)
        
        # Minimum threshold
        if position_size < 0.05:
            position_size = 0.0
        
        return position_size
    
    def _calculate_stop_loss_take_profit(self, symbol: str, 
                                         technical_result: Any,
                                         action: str) -> Tuple[Optional[float], Optional[float]]:
        """
        Calculate stop loss and take profit levels
        """
        try:
            if not hasattr(technical_result, 'current_price'):
                return None, None
            
            current_price = technical_result.current_price
            
            if action in ['STRONG_BUY', 'BUY']:
                # Support levels untuk stop loss
                if hasattr(technical_result, 'support_levels') and technical_result.support_levels:
                    stop_loss = min(technical_result.support_levels[:2]) * 0.99
                else:
                    stop_loss = current_price * 0.95  # 5% stop loss
                
                # Resistance untuk take profit
                if hasattr(technical_result, 'resistance_levels') and technical_result.resistance_levels:
                    take_profit = max(technical_result.resistance_levels[:2]) * 1.01
                else:
                    take_profit = current_price * 1.10  # 10% take profit
                
                return stop_loss, take_profit
                
            elif action in ['STRONG_SELL', 'SELL']:
                # Resistance untuk stop loss (short position)
                if hasattr(technical_result, 'resistance_levels') and technical_result.resistance_levels:
                    stop_loss = max(technical_result.resistance_levels[:2]) * 1.01
                else:
                    stop_loss = current_price * 1.05  # 5% stop loss
                
                # Support untuk take profit
                if hasattr(technical_result, 'support_levels') and technical_result.support_levels:
                    take_profit = min(technical_result.support_levels[:2]) * 0.99
                else:
                    take_profit = current_price * 0.90  # 10% take profit
                
                return stop_loss, take_profit
            
            return None, None
            
        except Exception as e:
            logger.error(f"Error calculating SL/TP: {e}")
            return None, None
    
    def _determine_time_horizon(self, sentiment_score: float, 
                                technical_score: float, action: str) -> str:
        """
        Determine time horizon untuk trade
        """
        # Jika sentiment dan technical sejalan = medium/long term
        if abs(sentiment_score) > 0.3 and abs(technical_score) > 0.3:
            if abs(sentiment_score - technical_score) < 0.2:
                return "MEDIUM"
        
        # Jika technical lebih kuat = short term
        if abs(technical_score) > abs(sentiment_score):
            return "SHORT"
        
        # Jika sentiment lebih kuat = medium term
        if abs(sentiment_score) > abs(technical_score):
            return "MEDIUM"
        
        return "SHORT"
    
    def _generate_alternatives(self, combined_score: float,
                               sentiment_score: float,
                               technical_score: float) -> List[str]:
        """
        Generate alternative actions
        """
        alternatives = []
        
        # Jika kombinasi score menunjukkan buy, alternatif hold atau sell
        if combined_score > 0.3:
            alternatives.append(f"BEARISH CASE: Jika {technical_score > 0.3 and sentiment_score < -0.2, 'sentimen berubah bearish', 'tidak ada konfirmasi'} lebih baik hold")
            alternatives.append("ALTERNATIF: Scale-in dengan posisi lebih kecil")
        
        # Jika kombinasi score menunjukkan sell
        elif combined_score < -0.3:
            alternatives.append(f"BULLISH CASE: Jika {sentiment_score > 0.2 and technical_score < -0.2, 'teknikal membaik', 'mungkin reversal'}")
            alternatives.append("ALTERNATIF: Partial sell - reduce position")
        
        # Hold scenarios
        else:
            if sentiment_score > 0.2:
                alternatives.append("PERTIMBANGAN: Sentimen bullish tapi teknikal netral - wait for breakout")
            elif technical_score > 0.2:
                alternatives.append("PERTIMBANGAN: Teknikal bullish tapi sentimen netral - wait for volume confirmation")
            else:
                alternatives.append("ALTERNATIF: Pindah ke aset lain dengan sinyal lebih jelas")
        
        return alternatives[:2]
    
    def _build_final_decision(self, action: str, confidence: float,
                             position_size: float, reasoning: List[str]) -> str:
        """
        Build final decision statement
        """
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
        """Save decision to history for analysis"""
        self.decision_history.append(decision)
        if len(self.decision_history) > self.max_history:
            self.decision_history.pop(0)
    
    def get_recent_decisions(self, n: int = 10) -> List[DecisionResult]:
        """Get n recent decisions"""
        return self.decision_history[-n:]
    
    def _get_default_decision(self, symbol: str) -> DecisionResult:
        """Return default decision jika terjadi error"""
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

# Example usage
if __name__ == "__main__":
    # Import agents
    import sys
    sys.path.append('..')
    from agent_sentiment import SentimentAgent
    from agent_technical import TechnicalAgent
    
    # Initialize agents
    sentiment_agent = SentimentAgent()
    technical_agent = TechnicalAgent()
    decision_agent = DecisionAgent()
    
    # Test dengan BTC
    symbol = "BTC-USD"
    print("=" * 60)
    print(f"DECISION ANALYSIS FOR {symbol}")
    print("=" * 60)
    
    # Get analyses
    sentiment_result = sentiment_agent.analyze(symbol)
    technical_result = technical_agent.analyze(symbol)
    
    # Make decision
    decision = decision_agent.analyze(
        symbol,
        sentiment_result,
        technical_result
    )
    
    print(f"\n📊 DECISION: {decision.action}")
    print(f"📈 Action Score: {decision.action_score:.3f}")
    print(f"🎯 Confidence: {decision.confidence:.1%}")
    print(f"💰 Position Size: {decision.suggested_position_size:.1%}")
    print(f"⏰ Time Horizon: {decision.time_horizon}")
    
    if decision.stop_loss and decision.take_profit:
        print(f"🛑 Stop Loss: ${decision.stop_loss:.2f}")
        print(f"🎯 Take Profit: ${decision.take_profit:.2f}")
    
    print("\n📝 REASONING:")
    for i, reason in enumerate(decision.reasoning, 1):
        print(f"  {i}. {reason}")
    
    print("\n📊 FACTORS:")
    print(f"  Sentiment: {decision.sentiment_score:.3f}")
    print(f"  Technical: {decision.technical_score:.3f}")
    print(f"  Risk: {decision.risk_score:.3f}")
    print(f"  Market Context: {decision.market_context_score:.3f}")
    
    print("\n🔄 ALTERNATIVES:")
    for alt in decision.alternative_actions:
        print(f"  • {alt}")
    
    print(f"\n✅ FINAL DECISION: {decision.final_decision}")
    print(f"\n📋 SUMMARY: {decision.summary}")
