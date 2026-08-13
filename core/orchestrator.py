"""
Orchestrator: Mengelola dan menjalankan semua AI Agents secara paralel

Bertugas:
1. Menginisialisasi semua 5 agents
2. Menjalankan agents secara paralel (concurrent)
3. Mengumpulkan hasil dari semua agents
4. Melakukan "debate" atau voting jika ada perbedaan pendapat
5. Mengirimkan hasil ke Executor untuk eksekusi
"""

import os
import sys
import logging
import asyncio
import json
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
import concurrent.futures
from enum import Enum

# Import semua agents
from agents.agent_sentiment import SentimentAgent, SentimentResult
from agents.agent_technical import TechnicalAgent, TechnicalResult
from agents.agent_decision import DecisionAgent, DecisionResult
from agents.agent_reflector import ReflectorAgent, ReflectionResult, TradeRecord
from agents.agent_forecast import ForecastAgent, ForecastResult

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class OrchestratorResult:
    """Hasil akhir dari orchestrator"""
    timestamp: datetime
    symbol: str
    current_price: float
    
    # Hasil dari masing-masing agent
    sentiment: Optional[SentimentResult]
    technical: Optional[TechnicalResult]
    decision: Optional[DecisionResult]
    reflection: Optional[ReflectionResult]
    forecast: Optional[ForecastResult]
    
    # Consensus / Voting
    consensus_action: str  # BUY, SELL, HOLD
    consensus_score: float
    agent_votes: Dict[str, str]  # agent_name: action
    
    # Final decision
    final_action: str
    final_confidence: float
    position_size: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    
    # Summary
    summary: str

class Orchestrator:
    """
    Orchestrator untuk menjalankan semua agents secara terkoordinasi
    """
    
    def __init__(self, config: Dict = None):
        """
        Initialize Orchestrator
        
        Args:
            config: Konfigurasi untuk orchestrator
        """
        self.config = config or {}
        
        # Initialize all agents
        self.sentiment_agent = SentimentAgent()
        self.technical_agent = TechnicalAgent()
        self.decision_agent = DecisionAgent()
        self.reflector_agent = ReflectorAgent()
        self.forecast_agent = ForecastAgent()
        
        # Voting thresholds
        self.voting_thresholds = {
            'strong_buy': 0.7,
            'buy': 0.3,
            'hold': 0.3,
            'sell': -0.3,
            'strong_sell': -0.7
        }
        
        # Agent weights untuk voting
        self.agent_weights = {
            'sentiment': 0.25,
            'technical': 0.30,
            'decision': 0.30,
            'forecast': 0.15
        }
        
        # History untuk tracking
        self.history: List[OrchestratorResult] = []
        self.max_history = 100
        
        logger.info("Orchestrator initialized successfully")
    
    async def analyze(self, symbol: str, market_data: Dict = None) -> OrchestratorResult:
        """
        Main method untuk menjalankan semua agents
        
        Args:
            symbol: Simbol aset (e.g., 'BTC-USD')
            market_data: Data pasar opsional
        
        Returns:
            OrchestratorResult: Hasil agregasi dari semua agents
        """
        logger.info(f"Orchestrator analyzing {symbol}")
        
        try:
            # 1. Run all agents concurrently
            tasks = [
                self._run_sentiment(symbol, market_data),
                self._run_technical(symbol, market_data),
                self._run_decision(symbol, market_data),
                self._run_reflection(symbol, market_data),
                self._run_forecast(symbol, market_data)
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 2. Extract results
            sentiment_result = results[0] if not isinstance(results[0], Exception) else None
            technical_result = results[1] if not isinstance(results[1], Exception) else None
            decision_result = results[2] if not isinstance(results[2], Exception) else None
            reflection_result = results[3] if not isinstance(results[3], Exception) else None
            forecast_result = results[4] if not isinstance(results[4], Exception) else None
            
            # 3. Get current price
            current_price = self._get_current_price(market_data, technical_result)
            
            # 4. Voting / Consensus
            consensus_action, consensus_score = self._perform_voting(
                sentiment_result, technical_result, decision_result, forecast_result
            )
            
            # 5. Get agent votes
            agent_votes = self._get_agent_votes(
                sentiment_result, technical_result, decision_result, forecast_result
            )
            
            # 6. Final decision (from decision agent with consensus adjustment)
            final_action, final_confidence = self._determine_final_action(
                decision_result, consensus_action, consensus_score
            )
            
            # 7. Position sizing
            position_size = self._calculate_position_size(
                final_confidence, decision_result
            )
            
            # 8. Stop loss & Take profit
            stop_loss, take_profit = self._calculate_sl_tp(
                technical_result, final_action, current_price
            )
            
            # 9. Generate summary
            summary = self._generate_summary(
                symbol, final_action, final_confidence, position_size,
                consensus_action, agent_votes
            )
            
            # 10. Build result
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
                summary=summary
            )
            
            # Save history
            self.history.append(result)
            if len(self.history) > self.max_history:
                self.history.pop(0)
            
            # Log result
            logger.info(f"Orchestrator result for {symbol}: {final_action} (confidence: {final_confidence:.1%})")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in orchestrator: {str(e)}")
            return self._get_default_result(symbol)
    
    async def _run_sentiment(self, symbol: str, market_data: Dict) -> Optional[SentimentResult]:
        """Run sentiment agent"""
        try:
            return await asyncio.to_thread(
                self.sentiment_agent.analyze, symbol, market_data
            )
        except Exception as e:
            logger.error(f"Error in sentiment agent: {e}")
            return None
    
    async def _run_technical(self, symbol: str, market_data: Dict) -> Optional[TechnicalResult]:
        """Run technical agent"""
        try:
            return await asyncio.to_thread(
                self.technical_agent.analyze, symbol, market_data
            )
        except Exception as e:
            logger.error(f"Error in technical agent: {e}")
            return None
    
    async def _run_decision(self, symbol: str, market_data: Dict) -> Optional[DecisionResult]:
        """Run decision agent"""
        try:
            # Need sentiment and technical results first
            sentiment = await self._run_sentiment(symbol, market_data)
            technical = await self._run_technical(symbol, market_data)
            
            return await asyncio.to_thread(
                self.decision_agent.analyze, symbol, sentiment, technical, market_data
            )
        except Exception as e:
            logger.error(f"Error in decision agent: {e}")
            return None
    
    async def _run_reflection(self, symbol: str, market_data: Dict) -> Optional[ReflectionResult]:
        """Run reflector agent"""
        try:
            # Get recent trades from history
            trades = self._get_recent_trades(symbol)
            return await asyncio.to_thread(
                self.reflector_agent.analyze, symbol, trades, None
            )
        except Exception as e:
            logger.error(f"Error in reflector agent: {e}")
            return None
    
    async def _run_forecast(self, symbol: str, market_data: Dict) -> Optional[ForecastResult]:
        """Run forecast agent"""
        try:
            # Get sentiment and technical for better forecast
            sentiment = await self._run_sentiment(symbol, market_data)
            technical = await self._run_technical(symbol, market_data)
            
            return await asyncio.to_thread(
                self.forecast_agent.analyze, symbol, sentiment, technical, market_data
            )
        except Exception as e:
            logger.error(f"Error in forecast agent: {e}")
            return None
    
    def _perform_voting(self, sentiment: Optional[SentimentResult],
                       technical: Optional[TechnicalResult],
                       decision: Optional[DecisionResult],
                       forecast: Optional[ForecastResult]) -> Tuple[str, float]:
        """
        Perform voting / consensus mechanism
        
        Returns:
            Tuple of (consensus_action, consensus_score)
        """
        votes = []
        scores = []
        
        # Sentiment vote
        if sentiment:
            sentiment_score = sentiment.overall_score
            sentiment_action = self._score_to_action(sentiment_score)
            votes.append(('sentiment', sentiment_action))
            scores.append(('sentiment', sentiment_score * self.agent_weights['sentiment']))
        
        # Technical vote
        if technical:
            tech_score = technical.overall_score
            tech_action = self._score_to_action(tech_score)
            votes.append(('technical', tech_action))
            scores.append(('technical', tech_score * self.agent_weights['technical']))
        
        # Decision vote (most important)
        if decision:
            decision_score = decision.action_score
            decision_action = decision.action
            votes.append(('decision', decision_action))
            scores.append(('decision', decision_score * self.agent_weights['decision']))
        
        # Forecast vote
        if forecast:
            # Convert forecast trend to action
            forecast_score = self._forecast_to_score(forecast)
            forecast_action = self._score_to_action(forecast_score)
            votes.append(('forecast', forecast_action))
            scores.append(('forecast', forecast_score * self.agent_weights['forecast']))
        
        # Count votes
        vote_counts = {'STRONG_BUY': 0, 'BUY': 0, 'HOLD': 0, 'SELL': 0, 'STRONG_SELL': 0}
        for _, action in votes:
            vote_counts[action] += 1
        
        # Weighted score
        total_score = sum(score for _, score in scores)
        total_weight = sum(self.agent_weights.values())
        
        if total_weight > 0:
            consensus_score = total_score / total_weight
        else:
            consensus_score = 0
        
        # Determine consensus action
        consensus_action = self._score_to_action(consensus_score)
        
        return consensus_action, consensus_score
    
    def _score_to_action(self, score: float) -> str:
        """Convert score to action string"""
        if score >= self.voting_thresholds['strong_buy']:
            return 'STRONG_BUY'
        elif score >= self.voting_thresholds['buy']:
            return 'BUY'
        elif score <= self.voting_thresholds['strong_sell']:
            return 'STRONG_SELL'
        elif score <= self.voting_thresholds['sell']:
            return 'SELL'
        else:
            return 'HOLD'
    
    def _forecast_to_score(self, forecast: ForecastResult) -> float:
        """Convert forecast result to action score"""
        score = 0.0
        
        # Based on trend
        if forecast.primary_trend == 'BULLISH':
            score += 0.4
        elif forecast.primary_trend == 'BEARISH':
            score -= 0.4
        
        # Based on next move probability
        next_move = forecast.next_move_probability
        if next_move.get('UP', 0) > 0.5:
            score += 0.3
        elif next_move.get('DOWN', 0) > 0.5:
            score -= 0.3
        
        # Based on short-term prediction
        if forecast.short_term.predicted_price > forecast.current_price:
            score += 0.2
        else:
            score -= 0.2
        
        return max(-1.0, min(1.0, score))
    
    def _get_agent_votes(self, sentiment: Optional[SentimentResult],
                        technical: Optional[TechnicalResult],
                        decision: Optional[DecisionResult],
                        forecast: Optional[ForecastResult]) -> Dict[str, str]:
        """Get votes from each agent"""
        votes = {}
        
        if sentiment:
            votes['sentiment'] = self._score_to_action(sentiment.overall_score)
        
        if technical:
            votes['technical'] = self._score_to_action(technical.overall_score)
        
        if decision:
            votes['decision'] = decision.action
        
        if forecast:
            forecast_score = self._forecast_to_score(forecast)
            votes['forecast'] = self._score_to_action(forecast_score)
        
        return votes
    
    def _determine_final_action(self, decision: Optional[DecisionResult],
                                consensus_action: str,
                                consensus_score: float) -> Tuple[str, float]:
        """
        Determine final action based on decision agent and consensus
        """
        # If decision agent is available, use it with consensus adjustment
        if decision:
            # Weighted combination: 60% decision, 40% consensus
            decision_score = decision.action_score
            combined_score = (decision_score * 0.6) + (consensus_score * 0.4)
            
            action = self._score_to_action(combined_score)
            confidence = min(1.0, decision.confidence + 0.1)  # Boost from consensus
            
            return action, confidence
        
        # Otherwise, use consensus
        return consensus_action, min(1.0, abs(consensus_score) * 0.8 + 0.2)
    
    def _calculate_position_size(self, confidence: float,
                                 decision: Optional[DecisionResult]) -> float:
        """Calculate position size based on confidence"""
        if decision:
            base_size = decision.suggested_position_size
        else:
            base_size = 0.1
        
        # Adjust by confidence
        size = base_size * min(1.0, confidence * 1.5)
        
        # Cap at 20%
        return min(0.20, max(0.0, size))
    
    def _calculate_sl_tp(self, technical: Optional[TechnicalResult],
                        action: str, current_price: float) -> Tuple[Optional[float], Optional[float]]:
        """Calculate stop loss and take profit levels"""
        if not technical or not current_price:
            return None, None
        
        stop_loss = None
        take_profit = None
        
        if action in ['BUY', 'STRONG_BUY']:
            if technical.support_levels:
                stop_loss = min(technical.support_levels) * 0.99
            else:
                stop_loss = current_price * 0.95
            
            if technical.resistance_levels:
                take_profit = max(technical.resistance_levels) * 1.01
            else:
                take_profit = current_price * 1.10
        
        elif action in ['SELL', 'STRONG_SELL']:
            if technical.resistance_levels:
                stop_loss = max(technical.resistance_levels) * 1.01
            else:
                stop_loss = current_price * 1.05
            
            if technical.support_levels:
                take_profit = min(technical.support_levels) * 0.99
            else:
                take_profit = current_price * 0.90
        
        return stop_loss, take_profit
    
    def _get_current_price(self, market_data: Dict,
                          technical: Optional[TechnicalResult]) -> float:
        """Get current price from various sources"""
        if market_data and 'current_price' in market_data:
            return market_data['current_price']
        
        if technical:
            return technical.current_price
        
        return 0.0
    
    def _get_recent_trades(self, symbol: str) -> List[TradeRecord]:
        """Get recent trades from history"""
        trades = []
        for result in self.history[-50:]:
            if result.symbol == symbol:
                # Create trade record from orchestrator result
                if result.final_action in ['BUY', 'STRONG_BUY', 'SELL', 'STRONG_SELL']:
                    trade = TradeRecord(
                        trade_id=f"TRADE_{result.timestamp.timestamp()}",
                        symbol=result.symbol,
                        entry_price=result.current_price,
                        exit_price=0.0,  # Not closed yet
                        entry_time=result.timestamp,
                        exit_time=result.timestamp,
                        position_size=result.position_size,
                        action=result.final_action,
                        outcome="PENDING",
                        pnl=0.0,
                        pnl_percent=0.0,
                        holding_period_hours=0.0,
                        decision_confidence=result.final_confidence,
                        sentiment_score_at_entry=result.sentiment.overall_score if result.sentiment else 0,
                        technical_score_at_entry=result.technical.overall_score if result.technical else 0,
                        stop_loss=result.stop_loss or 0,
                        take_profit=result.take_profit or 0,
                        reason_closed="PENDING"
                    )
                    trades.append(trade)
        
        return trades
    
    def _generate_summary(self, symbol: str, action: str, confidence: float,
                         position_size: float, consensus_action: str,
                         agent_votes: Dict[str, str]) -> str:
        """Generate summary of orchestrator result"""
        summary = f"=== ORCHESTRATOR SUMMARY ===\n"
        summary += f"Symbol: {symbol}\n"
        summary += f"Final Action: {action} (Confidence: {confidence:.1%})\n"
        summary += f"Position Size: {position_size:.1%}\n"
        summary += f"Consensus: {consensus_action}\n"
        summary += f"\nAgent Votes:\n"
        for agent, vote in agent_votes.items():
            summary += f"  {agent}: {vote}\n"
        
        return summary
    
    def _get_default_result(self, symbol: str) -> OrchestratorResult:
        """Return default result if error"""
        return OrchestratorResult(
            timestamp=datetime.now(),
            symbol=symbol,
            current_price=0.0,
            sentiment=None,
            technical=None,
            decision=None,
            reflection=None,
            forecast=None,
            consensus_action='HOLD',
            consensus_score=0.0,
            agent_votes={},
            final_action='HOLD',
            final_confidence=0.0,
            position_size=0.0,
            stop_loss=None,
            take_profit=None,
            summary="Error in orchestrator - default to HOLD"
        )
    
    def get_history(self, n: int = 10) -> List[OrchestratorResult]:
        """Get recent history"""
        return self.history[-n:]

# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def main():
        orchestrator = Orchestrator()
        
        # Analyze a symbol
        result = await orchestrator.analyze("BTC-USD")
        
        print("=" * 60)
        print("ORCHESTRATOR RESULT")
        print("=" * 60)
        print(f"Symbol: {result.symbol}")
        print(f"Price: ${result.current_price:.2f}")
        print(f"Action: {result.final_action}")
        print(f"Confidence: {result.final_confidence:.1%}")
        print(f"Position Size: {result.position_size:.1%}")
        if result.stop_loss:
            print(f"Stop Loss: ${result.stop_loss:.2f}")
        if result.take_profit:
            print(f"Take Profit: ${result.take_profit:.2f}")
        print(f"\nVotes:")
        for agent, vote in result.agent_votes.items():
            print(f"  {agent}: {vote}")
        print(f"\n{result.summary}")
    
    asyncio.run(main())
