"""
core/mimic_trader.py - Mimic Trader Style

Mengimplementasikan pola pikir trader profesional:
- Bull/Bear Case Analysis
- Risk-First Decision Making
- Anti-Martingale Position Sizing
- Multi-Target Exit Strategy
"""

import logging
import random
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class BullBearAnalysis:
    """Hasil analisis Bull vs Bear."""
    symbol: str
    timestamp: datetime
    
    # Bull case
    bull_score: float  # 0-1
    bull_factors: List[str]
    bull_targets: List[float]  # Multiple TP levels
    
    # Bear case
    bear_score: float  # 0-1
    bear_factors: List[str]
    bear_risks: List[str]
    
    # Final verdict
    net_score: float  # -1 to 1
    recommendation: str  # STRONG_BUY, BUY, HOLD, SELL, STRONG_SELL
    confidence: float  # 0-1
    
    # Position sizing
    suggested_position: float  # 0-1
    stop_loss: Optional[float]
    take_profit_levels: List[float]  # Multiple TP levels
    
    # Reasoning
    reasoning: str


class MimicTrader:
    """
    Mimic Trader - Meniru gaya trading trader profesional.
    
    Referensi:
    - Multi-agent LLM trading system [citation:10]
    - Hybrid LLM + RL trading [citation:7]
    - AI Alpha Trading Arena [citation:12]
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        
        # Risk parameters
        self.max_drawdown = self.config.get("max_drawdown", 0.15)
        self.max_position = self.config.get("max_position", 0.20)
        self.min_position = self.config.get("min_position", 0.02)
        self.risk_per_trade = self.config.get("risk_per_trade", 0.01)
        
        # Anti-Martingale
        self.use_anti_martingale = self.config.get("use_anti_martingale", True)
        self.win_streak_multiplier = self.config.get("win_streak_multiplier", 1.2)
        self.loss_streak_multiplier = self.config.get("loss_streak_multiplier", 0.7)
        self.win_streak = 0
        self.loss_streak = 0
        
        # Multi-target exit levels
        self.tp_levels = self.config.get("tp_levels", [0.5, 1.0, 2.0])  # ATR multiples
        self.tp_allocation = self.config.get("tp_allocation", [0.5, 0.3, 0.2])  # 50%, 30%, 20%
        
        # Bull/Bear bias
        self.bull_bias = self.config.get("bull_bias", 0.5)
        self.bear_bias = self.config.get("bear_bias", 0.5)
        
        # Performance tracking
        self.trade_history: List[Dict] = []
        self.performance = {
            "wins": 0,
            "losses": 0,
            "total_pnl": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "max_drawdown": 0.0,
        }
        
        logger.info("MimicTrader initialized with Anti-Martingale: %s", self.use_anti_martingale)
    
    def analyze(self, symbol: str, market_data: Dict) -> BullBearAnalysis:
        """
        Analisis Bull vs Bear seperti trader profesional.
        
        Args:
            symbol: Trading symbol
            market_data: Data pasar lengkap
        
        Returns:
            BullBearAnalysis dengan rekomendasi
        """
        logger.info("Analyzing %s with MimicTrader", symbol)
        
        # ============================================================
        # 1. BULL CASE - Build bullish argument
        # ============================================================
        
        bull_score, bull_factors, bull_targets = self._build_bull_case(market_data)
        
        # ============================================================
        # 2. BEAR CASE - Build bearish argument
        # ============================================================
        
        bear_score, bear_factors, bear_risks = self._build_bear_case(market_data)
        
        # ============================================================
        # 3. NET SCORE - Final verdict
        # ============================================================
        
        net_score = bull_score - bear_score
        net_score = max(-1.0, min(1.0, net_score))
        
        recommendation = self._score_to_action(net_score)
        confidence = self._calculate_confidence(bull_score, bear_score, market_data)
        
        # ============================================================
        # 4. POSITION SIZING - Anti-Martingale
        # ============================================================
        
        suggested_position = self._calculate_position_size(
            net_score, confidence, market_data
        )
        
        # ============================================================
        # 5. EXIT STRATEGY - Multiple TP levels
        # ============================================================
        
        current_price = self._get_current_price(market_data)
        stop_loss, take_profit_levels = self._calculate_exit_levels(
            current_price, net_score, market_data
        )
        
        # ============================================================
        # 6. REASONING - Transparent decision
        # ============================================================
        
        reasoning = self._generate_reasoning(
            symbol, bull_score, bear_score, net_score,
            bull_factors, bear_factors, recommendation
        )
        
        return BullBearAnalysis(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            bull_score=bull_score,
            bull_factors=bull_factors,
            bull_targets=bull_targets,
            bear_score=bear_score,
            bear_factors=bear_factors,
            bear_risks=bear_risks,
            net_score=net_score,
            recommendation=recommendation,
            confidence=confidence,
            suggested_position=suggested_position,
            stop_loss=stop_loss,
            take_profit_levels=take_profit_levels,
            reasoning=reasoning
        )
    
    def _build_bull_case(self, market_data: Dict) -> Tuple[float, List[str], List[float]]:
        """Build bullish argument like Bull Researcher."""
        factors = []
        score = 0.0
        targets = []
        
        current_price = self._get_current_price(market_data)
        
        # 1. Technical bullish signals
        technical_score = self._get_technical_score(market_data)
        if technical_score > 0.3:
            factors.append(f"Technical bullish: {technical_score:.2f}")
            score += technical_score * 0.3
        elif technical_score > 0:
            factors.append("Technical neutral with bullish bias")
            score += technical_score * 0.15
        
        # 2. Sentiment bullish
        sentiment_score = self._get_sentiment_score(market_data)
        if sentiment_score > 0.2:
            factors.append(f"Sentiment bullish: {sentiment_score:.2f}")
            score += sentiment_score * 0.2
        elif sentiment_score > 0:
            factors.append("Sentiment neutral")
            score += sentiment_score * 0.1
        
        # 3. Momentum bullish
        momentum = self._get_momentum_score(market_data)
        if momentum > 0:
            factors.append(f"Positive momentum: {momentum:.2f}")
            score += momentum * 0.15
        
        # 4. Support levels
        support_levels = market_data.get("support_levels", [])
        if support_levels and current_price > 0:
            nearest_support = support_levels[0] if support_levels else current_price * 0.95
            if current_price > nearest_support:
                factors.append(f"Above key support: {nearest_support:.2f}")
                score += 0.1
        
        # 5. Pattern detection
        patterns = market_data.get("detected_patterns", [])
        bullish_patterns = [p for p in patterns if p.get("signal") == "BULLISH"]
        if bullish_patterns:
            factors.append(f"Bullish pattern: {bullish_patterns[0].get('name')}")
            score += 0.15
        
        # Calculate targets
        if current_price > 0:
            resistance_levels = market_data.get("resistance_levels", [])
            if resistance_levels:
                for level in resistance_levels[:3]:
                    if level > current_price:
                        targets.append(level)
        
        # Clamp score
        score = max(0.0, min(1.0, score))
        
        return score, factors[:5], targets
    
    def _build_bear_case(self, market_data: Dict) -> Tuple[float, List[str], List[str]]:
        """Build bearish argument like Bear Researcher."""
        factors = []
        risks = []
        score = 0.0
        
        current_price = self._get_current_price(market_data)
        
        # 1. Technical bearish signals
        technical_score = self._get_technical_score(market_data)
        if technical_score < -0.3:
            factors.append(f"Technical bearish: {technical_score:.2f}")
            score += abs(technical_score) * 0.3
        elif technical_score < 0:
            factors.append("Technical neutral with bearish bias")
            score += abs(technical_score) * 0.15
        
        # 2. Sentiment bearish
        sentiment_score = self._get_sentiment_score(market_data)
        if sentiment_score < -0.2:
            factors.append(f"Sentiment bearish: {sentiment_score:.2f}")
            score += abs(sentiment_score) * 0.2
        elif sentiment_score < 0:
            factors.append("Sentiment neutral")
            score += abs(sentiment_score) * 0.1
        
        # 3. Momentum bearish
        momentum = self._get_momentum_score(market_data)
        if momentum < 0:
            factors.append(f"Negative momentum: {momentum:.2f}")
            score += abs(momentum) * 0.15
        
        # 4. Resistance levels
        resistance_levels = market_data.get("resistance_levels", [])
        if resistance_levels and current_price > 0:
            nearest_resistance = resistance_levels[0] if resistance_levels else current_price * 1.05
            if current_price < nearest_resistance:
                factors.append(f"Below key resistance: {nearest_resistance:.2f}")
                score += 0.1
        
        # 5. Pattern detection
        patterns = market_data.get("detected_patterns", [])
        bearish_patterns = [p for p in patterns if p.get("signal") == "BEARISH"]
        if bearish_patterns:
            factors.append(f"Bearish pattern: {bearish_patterns[0].get('name')}")
            score += 0.15
        
        # 6. Risks
        volatility = market_data.get("volatility", 0.02)
        if volatility > 0.05:
            risks.append(f"High volatility: {volatility:.2%}")
            score += 0.1
        
        # Clamp score
        score = max(0.0, min(1.0, score))
        
        return score, factors[:5], risks[:3]
    
    def _calculate_position_size(self, net_score: float, confidence: float, market_data: Dict) -> float:
        """Calculate position size with Anti-Martingale."""
        base_size = self.max_position * abs(net_score) * confidence
        
        # Apply Anti-Martingale
        if self.use_anti_martingale:
            if self.win_streak > 0:
                multiplier = min(1.0 + (self.win_streak * 0.1), 1.5)
            elif self.loss_streak > 0:
                multiplier = max(0.3, 1.0 - (self.loss_streak * 0.1))
            else:
                multiplier = 1.0
            base_size *= multiplier
        
        # Adjust for volatility
        volatility = market_data.get("volatility", 0.02)
        if volatility > 0.05:
            base_size *= 0.7
        elif volatility < 0.01:
            base_size *= 1.2
        
        # Clamp
        size = max(self.min_position, min(self.max_position, base_size))
        
        # Log position sizing
        logger.debug("Position size: %.2f%% (base=%.2f, win_streak=%d, loss_streak=%d)",
                    size * 100, base_size, self.win_streak, self.loss_streak)
        
        return size
    
    def _calculate_exit_levels(self, current_price: float, net_score: float, market_data: Dict) -> Tuple[Optional[float], List[float]]:
        """Calculate multi-target exit levels."""
        if current_price <= 0 or abs(net_score) < 0.1:
            return None, []
        
        # Calculate ATR-like volatility
        atr = self._calculate_atr(market_data, current_price)
        
        # Stop loss: 1-2 ATR from entry
        if net_score > 0:
            stop_loss = current_price - (atr * 1.5)
        else:
            stop_loss = current_price + (atr * 1.5)
        
        # Take profit levels: multiple targets
        tp_levels = []
        for i, multiplier in enumerate(self.tp_levels[:3]):
            if net_score > 0:
                tp = current_price + (atr * multiplier)
            else:
                tp = current_price - (atr * multiplier)
            tp_levels.append(tp)
        
        return stop_loss, tp_levels
    
    def _calculate_atr(self, market_data: Dict, current_price: float) -> float:
        """Calculate ATR-like volatility."""
        # Try to get from market data
        if "atr" in market_data:
            return market_data["atr"]
        
        # Calculate from volatility
        volatility = market_data.get("volatility", 0.02)
        return current_price * volatility
    
    def _get_technical_score(self, market_data: Dict) -> float:
        """Get technical score from market data."""
        return market_data.get("technical_score", 0.0)
    
    def _get_sentiment_score(self, market_data: Dict) -> float:
        """Get sentiment score from market data."""
        return market_data.get("sentiment_score", 0.0)
    
    def _get_momentum_score(self, market_data: Dict) -> float:
        """Get momentum score from market data."""
        return market_data.get("momentum_score", 0.0)
    
    def _get_current_price(self, market_data: Dict) -> float:
        """Get current price from market data."""
        return market_data.get("current_price", 0.0)
    
    def _score_to_action(self, score: float) -> str:
        """Convert score to action."""
        if score >= 0.7:
            return "STRONG_BUY"
        elif score >= 0.3:
            return "BUY"
        elif score <= -0.7:
            return "STRONG_SELL"
        elif score <= -0.3:
            return "SELL"
        else:
            return "HOLD"
    
    def _calculate_confidence(self, bull_score: float, bear_score: float, market_data: Dict) -> float:
        """Calculate confidence in the decision."""
        # Difference between bull and bear
        difference = abs(bull_score - bear_score)
        
        # Higher difference = higher confidence
        base_confidence = min(1.0, difference * 2.5)
        
        # Adjust for data quality
        quality = market_data.get("data_quality", 0.7)
        confidence = base_confidence * quality
        
        return max(0.1, min(0.95, confidence))
    
    def _generate_reasoning(self, symbol: str, bull_score: float, bear_score: float,
                           net_score: float, bull_factors: List[str],
                           bear_factors: List[str], recommendation: str) -> str:
        """Generate human-readable reasoning."""
        lines = [
            f"MimicTrader Analysis for {symbol}:",
            f"Bull Case: {bull_score:.2%} ({len(bull_factors)} factors)",
            f"Bear Case: {bear_score:.2%} ({len(bear_factors)} factors)",
            f"Net Score: {net_score:.2f}",
            f"Decision: {recommendation}",
            "",
            "Bull Factors:",
        ]
        
        for factor in bull_factors[:3]:
            lines.append(f"  + {factor}")
        
        lines.append("")
        lines.append("Bear Factors:")
        for factor in bear_factors[:3]:
            lines.append(f"  - {factor}")
        
        if recommendation in ["BUY", "STRONG_BUY"]:
            lines.append("")
            lines.append(f"Bullish conviction: Bull ({bull_score:.2%}) > Bear ({bear_score:.2%})")
        elif recommendation in ["SELL", "STRONG_SELL"]:
            lines.append("")
            lines.append(f"Bearish conviction: Bear ({bear_score:.2%}) > Bull ({bull_score:.2%})")
        else:
            lines.append("")
            lines.append("HOLD: Insufficient edge")
        
        return "\n".join(lines)
    
    def update_performance(self, trade_result: Dict):
        """Update performance metrics for Anti-Martingale."""
        pnl = trade_result.get("pnl", 0)
        self.trade_history.append(trade_result)
        
        if pnl > 0:
            self.win_streak += 1
            self.loss_streak = 0
            self.performance["wins"] += 1
            self.performance["total_pnl"] += pnl
            self.performance["avg_win"] = self.performance["total_pnl"] / max(self.performance["wins"], 1)
        else:
            self.win_streak = 0
            self.loss_streak += 1
            self.performance["losses"] += 1
            self.performance["total_pnl"] += pnl
            self.performance["avg_loss"] = self.performance["total_pnl"] / max(self.performance["losses"], 1)
        
        logger.debug("Performance updated: win_streak=%d, loss_streak=%d",
                    self.win_streak, self.loss_streak)
    
    def get_performance_summary(self) -> Dict:
        """Get performance summary."""
        total_trades = self.performance["wins"] + self.performance["losses"]
        win_rate = self.performance["wins"] / max(total_trades, 1)
        
        return {
            "wins": self.performance["wins"],
            "losses": self.performance["losses"],
            "win_rate": win_rate,
            "total_pnl": self.performance["total_pnl"],
            "avg_win": self.performance["avg_win"],
            "avg_loss": self.performance["avg_loss"],
            "win_streak": self.win_streak,
            "loss_streak": self.loss_streak,
            "max_drawdown": self.performance["max_drawdown"],
        }
