"""
integration/trading_engine.py

Trading Integration Engine - Menghubungkan semua komponen trading.
"""

import asyncio
import json
import logging
import random
import math
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

from core.orchestrator import Orchestrator, OrchestratorResult
from core.risk_engine import RiskEngine
from core.decision_engine import DecisionEngine, DecisionInput, PositionState
from core.execution_gate import ExecutionGate

from core.unified_market_data import (
    UnifiedMarketDataProvider,
    get_market_data_provider,
    create_snapshot_from_market_data
)

from paper_trading.paper_engine import PaperTradingEngine

logger = logging.getLogger(__name__)


class TradingIntegrationEngine:
    """
    Trading Integration Engine dengan Unified Market Data.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

        # ============================================================
        # SAFETY
        # ============================================================

        self.mode = str(self.config.get("mode", "paper")).lower()
        if self.mode != "paper":
            raise ValueError("TradingIntegrationEngine hanya mendukung PAPER mode.")

        # ============================================================
        # UNIFIED MARKET DATA
        # ============================================================

        self.market_data_provider = get_market_data_provider(config)
        self.use_unified_data = config.get("use_unified_data", True)

        # ============================================================
        # CONFIGURATION
        # ============================================================

        self.orchestrator_config = self.config.get("orchestrator", {})
        self.risk_config = self.config.get("risk_engine", {})
        self.decision_config = self.config.get("decision_engine", {})
        self.execution_config = self.config.get("execution_gate", {})
        self.paper_config = self.config.get("paper_trading", {})

        # ============================================================
        # COMPONENTS
        # ============================================================

        self.orchestrator = Orchestrator(self.orchestrator_config)
        self.risk_engine = RiskEngine(self.risk_config)
        self.decision_engine = DecisionEngine(self.decision_config)
        self.execution_gate = self._build_execution_gate(self.execution_config)
        self.paper_engine = PaperTradingEngine(self.paper_config)

        # ============================================================
        # STATE
        # ============================================================

        self.running = False
        self.last_cycle: Optional[Dict[str, Any]] = None
        self.total_cycles = 0
        self.executed_trades = 0
        self.blocked_trades = 0
        self.closed_trades = 0

        logger.info("Trading Integration Engine initialized | MODE=%s", self.mode)

    def _build_execution_gate(self, config: Dict[str, Any]) -> ExecutionGate:
        """Build ExecutionGate dengan parameter yang benar."""
        config = config or {}

        min_confidence = float(config.get("min_confidence", 0.60))
        min_risk_reward = float(config.get("min_risk_reward", 1.50))
        max_position_size = float(config.get("max_position_size", 0.20))

        logger.info("Execution Gate config | min_confidence=%.2f | min_rr=%.2f | max_position=%.2f",
                   min_confidence, min_risk_reward, max_position_size)

        return ExecutionGate(
            min_confidence=min_confidence,
            min_risk_reward=min_risk_reward,
            max_position_size=max_position_size
        )

    # ============================================================
    # MAIN PIPELINE
    # ============================================================

    async def analyze_and_execute(
        self,
        symbol: str,
        market_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        FULL PIPELINE dengan Unified Market Data.
        """
        symbol = symbol.upper()
        self.total_cycles += 1
        timestamp = datetime.now(timezone.utc).isoformat()

        logger.info("=" * 70)
        logger.info("TRADING CYCLE #%s | %s", self.total_cycles, symbol)
        logger.info("=" * 70)

        # ============================================================
        # STEP 1: GET UNIFIED MARKET DATA
        # ============================================================

        market_data = market_data or {}

        if self.use_unified_data:
            # Try to get unified snapshot
            unified_snapshot = self.market_data_provider.get_snapshot(symbol)

            if unified_snapshot is None or unified_snapshot.is_stale(60):
                unified_snapshot = self.market_data_provider.refresh_snapshot(
                    symbol=symbol,
                    timeframe=market_data.get("timeframe", "1h"),
                    limit=100
                )

            if unified_snapshot is not None:
                # Inject unified data
                market_data["current_price"] = unified_snapshot.current_price
                market_data["unified_price"] = unified_snapshot.current_price
                market_data["_unified_snapshot"] = unified_snapshot
                market_data["timestamp"] = unified_snapshot.timestamp
                market_data["data_quality"] = unified_snapshot.data_quality_score
            else:
                logger.warning("No unified snapshot for %s, using provided market_data", symbol)

        # ============================================================
        # STEP 2: GET CURRENT PRICE
        # ============================================================

        current_price = self._extract_market_price(market_data)

        if current_price <= 0:
            return self._build_error_result(
                symbol, timestamp, "MARKET_DATA",
                "Invalid or missing current_price."
            )

        # ============================================================
        # STEP 3: POSITION MONITOR
        # ============================================================

        position = self.paper_engine.get_position(symbol)
        position_update = None

        if position is not None:
            logger.info("POSITION MONITOR | %s | %s | entry=%.2f | current=%.2f",
                       symbol, position.get("position_type"),
                       position.get("entry_price", 0.0), current_price)

            position_update = self.paper_engine.update_price(symbol, current_price)
            if position_update is not None:
                self.closed_trades += 1
                logger.info("POSITION CLOSED | %s | reason=%s", symbol,
                           position_update.get("reason", "UNKNOWN"))

        # ============================================================
        # STEP 4: ORCHESTRATOR
        # ============================================================

        try:
            orchestrator_result = await self.orchestrator.analyze(symbol, market_data)
        except Exception as e:
            logger.exception("Orchestrator failed")
            return self._build_error_result(symbol, timestamp, "ORCHESTRATOR", str(e))

        # Extract values
        action = str(getattr(orchestrator_result, "final_action", "HOLD")).upper()
        confidence = float(getattr(orchestrator_result, "final_confidence", 0.0))
        position_size = float(getattr(orchestrator_result, "position_size", 0.0))
        consensus_score = float(getattr(orchestrator_result, "consensus_score", 0.0))
        stop_loss = getattr(orchestrator_result, "stop_loss", None)
        take_profit = getattr(orchestrator_result, "take_profit", None)
        hold_reason = getattr(orchestrator_result, "hold_reason", None)

        logger.info("ORCHESTRATOR | action=%s | confidence=%.2f | consensus=%.4f",
                   action, confidence, consensus_score)

        # ============================================================
        # STEP 5: HOLD
        # ============================================================

        if action == "HOLD":
            result = {
                "timestamp": timestamp,
                "symbol": symbol,
                "status": "POSITION_UPDATED" if position_update else "NO_TRADE",
                "stage": "ORCHESTRATOR",
                "action": "HOLD",
                "confidence": confidence,
                "position_size": 0.0,
                "current_price": current_price,
                "position_update": position_update,
                "orchestrator": orchestrator_result,
                "paper_summary": self.paper_engine.get_summary({symbol: current_price}),
                "reason": getattr(orchestrator_result, "execution_reason", "Orchestrator returned HOLD."),
                "hold_reason": hold_reason
            }
            self.last_cycle = result
            return result

        # ============================================================
        # STEP 6: RISK ENGINE
        # ============================================================

        try:
            risk_result = self.risk_engine.evaluate(
                symbol=symbol,
                action=action,
                confidence=confidence,
                position_size=position_size,
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit
            )
        except Exception as e:
            logger.exception("Risk Engine failed")
            return self._build_error_result(symbol, timestamp, "RISK_ENGINE", str(e))

        risk_approved = bool(getattr(risk_result, "approved", False))
        risk_score = float(getattr(risk_result, "risk_score", 1.0))
        risk_reward_ratio = float(getattr(risk_result, "risk_reward_ratio", 0.0))

        logger.info("RISK ENGINE | approved=%s | risk=%.4f | RR=%.2f",
                   risk_approved, risk_score, risk_reward_ratio)

        if not risk_approved:
            self.blocked_trades += 1
            result = {
                "timestamp": timestamp,
                "symbol": symbol,
                "status": "RISK_REJECTED",
                "stage": "RISK_ENGINE",
                "action": "HOLD",
                "confidence": confidence,
                "position_size": 0.0,
                "risk": risk_result,
                "reason": getattr(risk_result, "reason", "Risk engine rejected trade.")
            }
            self.last_cycle = result
            return result

        # ============================================================
        # STEP 7: DECISION ENGINE
        # ============================================================

        try:
            decision_input = DecisionInput(
                symbol=symbol,
                consensus_score=consensus_score,
                confidence=confidence,
                sentiment_score=self._get_sentiment_score(orchestrator_result),
                technical_score=self._get_technical_score(orchestrator_result),
                forecast_score=self._get_forecast_score(orchestrator_result),
                decision_score=self._get_decision_score(orchestrator_result),
                risk_score=risk_score,
                risk_reward_ratio=risk_reward_ratio,
                suggested_position_size=position_size,
                position_state=self._get_position_state(symbol),
                current_price=current_price
            )

            decision_result = self.decision_engine.evaluate(decision_input)

        except Exception as e:
            logger.exception("Decision Engine failed")
            return self._build_error_result(symbol, timestamp, "DECISION_ENGINE", str(e))

        decision_approved = bool(getattr(decision_result, "approved", False))
        decision_action = str(getattr(decision_result, "action", "HOLD")).upper()
        decision_confidence = float(getattr(decision_result, "confidence", confidence))
        decision_position_size = float(getattr(decision_result, "position_size", position_size))

        logger.info("DECISION ENGINE | action=%s | approved=%s | confidence=%.2f",
                   decision_action, decision_approved, decision_confidence)

        if not decision_approved:
            self.blocked_trades += 1
            result = {
                "timestamp": timestamp,
                "symbol": symbol,
                "status": "DECISION_REJECTED",
                "stage": "DECISION_ENGINE",
                "action": "HOLD",
                "confidence": decision_confidence,
                "position_size": 0.0,
                "risk": risk_result,
                "decision": decision_result,
                "reason": "Decision engine rejected trade."
            }
            self.last_cycle = result
            return result

        # ============================================================
        # STEP 8: EXECUTION GATE
        # ============================================================

        execution_allowed = bool(self.config.get("execution_allowed", True))

        try:
            gate_result = self.execution_gate.evaluate(
                symbol=symbol,
                action=decision_action,
                confidence=decision_confidence,
                position_size=decision_position_size,
                risk_reward_ratio=risk_reward_ratio,
                approved=decision_approved,
                execution_allowed=execution_allowed
            )
        except Exception as e:
            logger.exception("Execution Gate failed")
            return self._build_error_result(symbol, timestamp, "EXECUTION_GATE", str(e))

        gate_allowed = bool(getattr(gate_result, "allowed", False))

        logger.info("EXECUTION GATE | allowed=%s", gate_allowed)

        if not gate_allowed:
            self.blocked_trades += 1
            result = {
                "timestamp": timestamp,
                "symbol": symbol,
                "status": "EXECUTION_BLOCKED",
                "stage": "EXECUTION_GATE",
                "action": "HOLD",
                "confidence": decision_confidence,
                "position_size": 0.0,
                "risk": risk_result,
                "decision": decision_result,
                "execution_gate": gate_result,
                "reason": getattr(gate_result, "reason", "Execution gate blocked trade.")
            }
            self.last_cycle = result
            return result

        # ============================================================
        # STEP 9: PAPER EXECUTION
        # ============================================================

        if self.mode != "paper":
            raise RuntimeError("SAFETY VIOLATION: Non-paper execution requested.")

        # Prevent duplicate position
        existing_position = self.paper_engine.get_position(symbol)
        if existing_position is not None:
            logger.warning("ENTRY BLOCKED | %s already has an active position.", symbol)
            self.blocked_trades += 1
            result = {
                "timestamp": timestamp,
                "symbol": symbol,
                "status": "POSITION_EXISTS",
                "stage": "PAPER_TRADING",
                "action": "HOLD",
                "current_price": current_price,
                "existing_position": existing_position,
                "reason": "Active position already exists."
            }
            self.last_cycle = result
            return result

        try:
            paper_result = self.paper_engine.open_position(
                symbol=symbol,
                side=decision_action,
                price=current_price,
                position_size=decision_position_size,
                confidence=decision_confidence,
                stop_loss=stop_loss,
                take_profit=take_profit,
                metadata={
                    "source": "trading_integration_engine",
                    "strategy": "AI_SCALPING",
                    "mode": "paper"
                }
            )
        except Exception as e:
            logger.exception("Paper Trading execution failed")
            return self._build_error_result(symbol, timestamp, "PAPER_TRADING", str(e))

        if paper_result is None:
            self.blocked_trades += 1
            result = {
                "timestamp": timestamp,
                "symbol": symbol,
                "status": "PAPER_REJECTED",
                "stage": "PAPER_TRADING",
                "action": "HOLD",
                "reason": "Paper engine rejected the position."
            }
            self.last_cycle = result
            return result

        # ============================================================
        # SUCCESS
        # ============================================================

        self.executed_trades += 1

        result = {
            "timestamp": timestamp,
            "symbol": symbol,
            "status": "PAPER_EXECUTED",
            "stage": "PAPER_TRADING",
            "mode": "paper",
            "action": decision_action,
            "confidence": decision_confidence,
            "position_size": decision_position_size,
            "current_price": current_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "pipeline": {
                "orchestrator": orchestrator_result,
                "risk_engine": risk_result,
                "decision_engine": decision_result,
                "execution_gate": gate_result,
                "paper_trading": paper_result
            },
            "paper_summary": self.paper_engine.get_summary({symbol: current_price})
        }

        self.last_cycle = result

        logger.info("PAPER TRADE COMPLETED | %s | %s | %.2f%%",
                   symbol, decision_action, decision_position_size * 100)

        return result

    # ============================================================
    # HELPER METHODS
    # ============================================================

    @staticmethod
    def _extract_market_price(market_data) -> float:
        """Extract current price from market data."""
        if not market_data:
            return 0.0

        # Try unified price first
        price = market_data.get("unified_price")
        if price is not None:
            try:
                return float(price)
            except (TypeError, ValueError):
                pass

        # Try current_price
        price = market_data.get("current_price")
        if price is None:
            price = market_data.get("price", 0.0)

        try:
            return float(price)
        except (TypeError, ValueError):
            return 0.0

    def _get_sentiment_score(self, orchestrator_result: OrchestratorResult) -> float:
        """Extract sentiment score from orchestrator result."""
        if hasattr(orchestrator_result, "sentiment") and orchestrator_result.sentiment:
            return float(getattr(orchestrator_result.sentiment, "overall_score", 0.0))
        if hasattr(orchestrator_result, "market_scores"):
            return float(orchestrator_result.market_scores.get("sentiment", 0.0))
        return 0.0

    def _get_technical_score(self, orchestrator_result: OrchestratorResult) -> float:
        """Extract technical score from orchestrator result."""
        if hasattr(orchestrator_result, "technical") and orchestrator_result.technical:
            return float(getattr(orchestrator_result.technical, "overall_score", 0.0))
        if hasattr(orchestrator_result, "market_scores"):
            return float(orchestrator_result.market_scores.get("technical", 0.0))
        return 0.0

    def _get_decision_score(self, orchestrator_result: OrchestratorResult) -> float:
        """Extract decision score from orchestrator result."""
        if hasattr(orchestrator_result, "decision") and orchestrator_result.decision:
            return float(getattr(orchestrator_result.decision, "action_score", 0.0))
        return float(getattr(orchestrator_result, "decision_score", 0.0))

    def _get_forecast_score(self, orchestrator_result: OrchestratorResult) -> float:
        """Extract forecast score from orchestrator result."""
        if hasattr(orchestrator_result, "forecast") and orchestrator_result.forecast:
            if hasattr(orchestrator_result.forecast, "forecast_score"):
                return float(orchestrator_result.forecast.forecast_score)
            trend = str(getattr(orchestrator_result.forecast, "primary_trend", "")).upper()
            if trend == "BULLISH":
                return 0.5
            elif trend == "BEARISH":
                return -0.5
        if hasattr(orchestrator_result, "market_scores"):
            return float(orchestrator_result.market_scores.get("forecast", 0.0))
        return 0.0

    def _get_position_state(self, symbol: str) -> PositionState:
        """Get current position state for DecisionEngine."""
        position = self.paper_engine.get_position(symbol)
        if position is None:
            return PositionState.FLAT
        pos_type = str(position.get("position_type", "FLAT")).upper()
        if pos_type == "LONG":
            return PositionState.LONG
        elif pos_type == "SHORT":
            return PositionState.SHORT
        return PositionState.FLAT

    def _build_error_result(self, symbol: str, timestamp: str, stage: str, error: str) -> Dict[str, Any]:
        """Build error result."""
        self.blocked_trades += 1
        return {
            "timestamp": timestamp,
            "symbol": symbol,
            "status": "ERROR",
            "stage": stage,
            "action": "HOLD",
            "position_size": 0.0,
            "error": str(error)
        }

    def get_status(self) -> Dict[str, Any]:
        """Get engine status."""
        try:
            summary = self.paper_engine.get_summary()
        except Exception:
            summary = {}
        return {
            "mode": self.mode,
            "running": self.running,
            "total_cycles": self.total_cycles,
            "executed_trades": self.executed_trades,
            "closed_trades": self.closed_trades,
            "blocked_trades": self.blocked_trades,
            "paper_trading": summary,
            "last_cycle": self.last_cycle
        }

    def start(self):
        """Start engine."""
        if self.mode != "paper":
            raise RuntimeError("Only PAPER mode is allowed.")
        self.running = True
        logger.info("Trading Integration Engine STARTED | MODE=PAPER")

    def stop(self):
        """Stop engine."""
        self.running = False
        logger.info("Trading Integration Engine STOPPED")


# ============================================================
# TEST RUNNER
# ============================================================

def _generate_test_ohlcv(base_price: float, count: int) -> List[Dict[str, Any]]:
    """Generate test OHLCV data."""
    ohlcv = []
    now = datetime.now(timezone.utc)
    price = base_price
    
    for i in range(count):
        # Random walk
        change = random.gauss(0, 0.002)
        open_price = price * (1 + change * 0.5)
        close_price = price * (1 + change)
        high_price = max(open_price, close_price) * (1 + abs(random.gauss(0, 0.001)))
        low_price = min(open_price, close_price) * (1 - abs(random.gauss(0, 0.001)))
        volume = 1000 + 500 * (1 + math.sin(i / 10))
        
        candle_time = now - timedelta(minutes=(count - i) * 60)
        
        ohlcv.append({
            "timestamp": candle_time,
            "open": round(open_price, 2),
            "high": round(high_price, 2),
            "low": round(low_price, 2),
            "close": round(close_price, 2),
            "volume": round(volume, 2)
        })
        
        price = close_price
    
    return ohlcv


async def test_engine():
    """Test function untuk menjalankan trading engine."""
    print("\n" + "=" * 70)
    print("TESTING TRADING ENGINE")
    print("=" * 70 + "\n")
    
    # Configuration
    config = {
        "mode": "paper",
        "use_unified_data": True,
        "execution_allowed": True,
        
      "orchestrator": {
        "enable_dynamic_weights": True,
        "max_position_size": 0.20,
        "min_confidence": 0.25,  # ← TURUNKAN DARI 0.40 KE 0.35
        "debug_enabled": True
    },
         "risk_engine": {
        "minimum_confidence": 0.25,  # ← TURUNKAN
        "max_position_size": 0.20,
        "minimum_risk_reward": 0.80,
        "max_daily_loss": 0.03,
        "max_risk_score": 1.0,
    },
        
        "decision_engine": {
        "min_confidence": 0.35,  # ← TURUNKAN
        "min_consensus": 0.05,
        "min_directional_edge": 0.05,
        "max_risk_score": 1.0,
        "min_risk_reward": 0.80,
        "live_trading_enabled": True
    },
        
       "execution_gate": {
        "min_confidence": 0.25,  # ← TURUNKAN
        "min_risk_reward": 0.80,
        "max_position_size": 0.20
    },
        
        "paper_trading": {
            "initial_balance": 10000.0,
            "max_position_size": 0.20
        }
    }
    
    # Initialize engine
    engine = TradingIntegrationEngine(config)
    engine.start()
    
    # Test market data
    market_data = {
        "symbol": "BTC-USD",
        "current_price": 62760.21,
        "timeframe": "1h",
        "volume_24h": 15000000.0,
        "high_24h": 63500.00,
        "low_24h": 62000.00,
        "fear_greed_index": 45,
        "ohlcv": _generate_test_ohlcv(62760.21, 100)
    }
    
    print("📊 Market Data:")
    print(f"   Symbol: {market_data['symbol']}")
    print(f"   Price: ${market_data['current_price']:.2f}")
    print(f"   OHLCV Points: {len(market_data['ohlcv'])}")
    print()
    
    # Run one cycle
    try:
        result = await engine.analyze_and_execute("BTC-USD", market_data)
        
        print("=" * 70)
        print("📈 RESULT")
        print("=" * 70)
        print(f"Status: {result.get('status')}")
        print(f"Action: {result.get('action')}")
        print(f"Confidence: {result.get('confidence', 0):.2%}")
        print(f"Position Size: {result.get('position_size', 0):.2%}")
        
        if result.get('hold_reason'):
            print(f"HOLD Reason: {result.get('hold_reason')}")
        if result.get('reason'):
            print(f"Reason: {result.get('reason')}")
        
        print("\n" + "=" * 70)
        print("ENGINE STATUS")
        print("=" * 70)
        status = engine.get_status()
        print(f"Mode: {status.get('mode')}")
        print(f"Total Cycles: {status.get('total_cycles')}")
        print(f"Executed Trades: {status.get('executed_trades')}")
        print(f"Blocked Trades: {status.get('blocked_trades')}")
        print(f"Closed Trades: {status.get('closed_trades')}")
        
        if status.get('paper_trading'):
            pt = status['paper_trading']
            print(f"Balance: ${pt.get('balance', 0):.2f}")
            print(f"Equity: ${pt.get('equity', 0):.2f}")
            print(f"Total PnL: ${pt.get('total_pnl', 0):.2f}")
            print(f"Win Rate: {pt.get('win_rate', 0):.1%}")
        
    except Exception as e:
        logger.exception("Test failed: %s", e)
        print(f"\n❌ ERROR: {e}")
    
    finally:
        engine.stop()
        print("\n" + "=" * 70)
        print("TEST COMPLETED")
        print("=" * 70)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    
    asyncio.run(test_engine())
