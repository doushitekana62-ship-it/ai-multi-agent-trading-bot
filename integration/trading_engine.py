"""
Trading Integration Engine v3 - FULLY INTEGRATED

FULL PAPER TRADING PIPELINE

MARKET DATA
    ↓
ORCHESTRATOR
    ↓
RISK ENGINE
    ↓
DECISION ENGINE
    ↓
EXECUTION GATE
    ↓
PAPER TRADING ENGINE
    ↓
POSITION MONITOR
    ↓
SL / TP
    ↓
TRADE RESULT

IMPORTANT SAFETY:
- PAPER MODE ONLY
- Tidak ada live trading
- Semua entry harus melewati seluruh decision pipeline
- PaperTradingEngine hanya mengeksekusi keputusan
- PaperTradingEngine tidak mengambil keputusan BUY/SELL
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from core.orchestrator import Orchestrator, OrchestratorResult
from core.risk_engine import RiskEngine, RiskDecision
from core.decision_engine import DecisionEngine, DecisionInput, DecisionResult, PositionState
from core.execution_gate import ExecutionGate, ExecutionGateResult

from paper_trading.paper_engine import PaperTradingEngine

logger = logging.getLogger(__name__)


class TradingIntegrationEngine:
    """
    Trading Integration Engine - FULLY INTEGRATED VERSION
    
    Menghubungkan semua komponen:
    - Orchestrator
    - Risk Engine
    - Decision Engine
    - Execution Gate
    - Paper Trading Engine
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

        # ==========================================================
        # SAFETY
        # ==========================================================

        self.mode = str(self.config.get("mode", "paper")).lower()
        if self.mode != "paper":
            raise ValueError("TradingIntegrationEngine hanya mendukung PAPER mode.")

        # ==========================================================
        # CONFIGURATION
        # ==========================================================

        self.orchestrator_config = self.config.get("orchestrator", {})
        self.risk_config = self.config.get("risk_engine", {})
        self.decision_config = self.config.get("decision_engine", {})
        self.execution_config = self.config.get("execution_gate", {})
        self.paper_config = self.config.get("paper_trading", {})

        # ==========================================================
        # COMPONENTS - FIXED INTEGRATION
        # ==========================================================

        # 1. Orchestrator
        self.orchestrator = Orchestrator(self.orchestrator_config)

        # 2. Risk Engine
        self.risk_engine = RiskEngine(self.risk_config)

        # 3. Decision Engine
        self.decision_engine = DecisionEngine(self.decision_config)

        # 4. Execution Gate
        self.execution_gate = self._build_execution_gate(self.execution_config)

        # 5. Paper Trading Engine
        self.paper_engine = PaperTradingEngine(self.paper_config)

        # ==========================================================
        # STATE
        # ==========================================================

        self.running = False
        self.last_cycle: Optional[Dict[str, Any]] = None
        self.total_cycles = 0
        self.executed_trades = 0
        self.blocked_trades = 0
        self.closed_trades = 0

        logger.info("Trading Integration Engine initialized | MODE=%s", self.mode)

    # ==============================================================
    # EXECUTION GATE BUILDER
    # ==============================================================

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

    # ==============================================================
    # MAIN PIPELINE
    # ==============================================================

    async def analyze_and_execute(
        self,
        symbol: str,
        market_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        FULL PIPELINE - Fully Integrated
        
        Menjalankan seluruh pipeline:
        1. Orchestrator - AI Decision
        2. Risk Engine - Risk Validation
        3. Decision Engine - Final Decision
        4. Execution Gate - Security Check
        5. Paper Trading - Execution
        """
        symbol = symbol.upper()
        self.total_cycles += 1
        timestamp = datetime.now(timezone.utc).isoformat()

        logger.info("=" * 70)
        logger.info("TRADING CYCLE #%s | %s", self.total_cycles, symbol)
        logger.info("=" * 70)

        # ==========================================================
        # MARKET PRICE
        # ==========================================================

        current_price = self._extract_market_price(market_data)
        if current_price <= 0:
            return self._build_error_result(symbol, timestamp, "MARKET_DATA",
                                          "Invalid or missing current_price.")

        # ==========================================================
        # POSITION MONITOR
        # ==========================================================

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

        # ==========================================================
        # 1. ORCHESTRATOR
        # ==========================================================

        try:
            orchestrator_result = await self.orchestrator.analyze(symbol, market_data)
        except Exception as e:
            logger.exception("Orchestrator failed")
            return self._build_error_result(symbol, timestamp, "ORCHESTRATOR", str(e))

        orchestrator_dict = self._serialize_object(orchestrator_result)

        # Extract values from OrchestratorResult
        action = str(getattr(orchestrator_result, "final_action", "HOLD")).upper()
        confidence = float(getattr(orchestrator_result, "final_confidence", 0.0))
        position_size = float(getattr(orchestrator_result, "position_size", 0.0))
        consensus_score = float(getattr(orchestrator_result, "consensus_score", 0.0))
        stop_loss = getattr(orchestrator_result, "stop_loss", None)
        take_profit = getattr(orchestrator_result, "take_profit", None)

        logger.info("ORCHESTRATOR | action=%s | confidence=%.2f | consensus=%.4f",
                   action, confidence, consensus_score)

        # ==========================================================
        # HOLD
        # ==========================================================

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
                "position_update": self._serialize_object(position_update),
                "orchestrator": orchestrator_dict,
                "paper_summary": self.paper_engine.get_summary({symbol: current_price}),
                "reason": "Orchestrator returned HOLD."
            }
            self.last_cycle = result
            return result

        # ==========================================================
        # 2. RISK ENGINE - FIXED INTEGRATION
        # ==========================================================

        try:
            # RiskEngine.evaluate expects: symbol, action, confidence, position_size, 
            # entry_price, stop_loss, take_profit
            risk_result = self.risk_engine.evaluate(
                symbol=symbol,
                action=action,
                confidence=confidence,
                position_size=position_size,
                entry_price=current_price,  # ← Gunakan entry_price, bukan current_price
                stop_loss=stop_loss,
                take_profit=take_profit
            )
        except Exception as e:
            logger.exception("Risk Engine failed")
            return self._build_error_result(symbol, timestamp, "RISK_ENGINE", str(e))

        risk_dict = self._serialize_object(risk_result)
        risk_score = float(getattr(risk_result, "risk_score", 1.0))
        risk_reward_ratio = float(getattr(risk_result, "risk_reward_ratio", 0.0))
        risk_approved = bool(getattr(risk_result, "approved", False))

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
                "risk": risk_dict,
                "reason": f"Risk engine rejected: {getattr(risk_result, 'reason', 'Unknown')}"
            }
            self.last_cycle = result
            return result

        # ==========================================================
        # 3. DECISION ENGINE - FIXED INTEGRATION
        # ==========================================================

        try:
            # DecisionEngine.evaluate expects DecisionInput object
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

        decision_dict = self._serialize_object(decision_result)
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
                "risk": risk_dict,
                "decision": decision_dict,
                "reason": "Decision engine rejected trade."
            }
            self.last_cycle = result
            return result

        # ==========================================================
        # 4. EXECUTION GATE - FIXED INTEGRATION
        # ==========================================================

        execution_allowed = bool(self.config.get("execution_allowed", True))

        try:
            # ExecutionGate.evaluate bisa menerima dictionary atau keyword arguments
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

        gate_dict = self._serialize_object(gate_result)
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
                "risk": risk_dict,
                "decision": decision_dict,
                "execution_gate": gate_dict,
                "reason": getattr(gate_result, "reason", "Execution gate blocked trade.")
            }
            self.last_cycle = result
            return result

        # ==========================================================
        # 5. PAPER EXECUTION
        # ==========================================================

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
                "existing_position": self._serialize_object(existing_position),
                "reason": "Active position already exists."
            }
            self.last_cycle = result
            return result

        # Execute
        try:
            paper_result = self._execute_paper(
                symbol=symbol,
                action=decision_action,
                position_size=decision_position_size,
                confidence=decision_confidence,
                current_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit
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

        # ==========================================================
        # SUCCESS
        # ==========================================================

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
                "orchestrator": orchestrator_dict,
                "risk_engine": risk_dict,
                "decision_engine": decision_dict,
                "execution_gate": gate_dict,
                "paper_trading": self._serialize_object(paper_result)
            },
            "paper_summary": self.paper_engine.get_summary({symbol: current_price})
        }

        self.last_cycle = result

        logger.info("PAPER TRADE COMPLETED | %s | %s | %.2f%%",
                   symbol, decision_action, decision_position_size * 100)

        return result

    # ==============================================================
    # HELPER METHODS - EXTRACT SCORES FROM ORCHESTRATOR
    # ==============================================================

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
            # Try to get forecast score
            if hasattr(orchestrator_result.forecast, "forecast_score"):
                return float(orchestrator_result.forecast.forecast_score)
            # Or calculate from trend
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

    # ==============================================================
    # PAPER EXECUTION
    # ==============================================================

    def _execute_paper(self, symbol: str, action: str, position_size: float,
                       confidence: float, current_price: float,
                       stop_loss: Optional[float], take_profit: Optional[float]):
        """Execute paper trade."""
        if not hasattr(self.paper_engine, "open_position"):
            raise AttributeError("PaperTradingEngine must have open_position().")

        return self.paper_engine.open_position(
            symbol=symbol,
            side=action,
            price=current_price,
            position_size=position_size,
            confidence=confidence,
            stop_loss=stop_loss,
            take_profit=take_profit,
            metadata={
                "source": "trading_integration_engine",
                "strategy": "AI_SCALPING",
                "mode": "paper"
            }
        )

    # ==============================================================
    # MARKET DATA
    # ==============================================================

    @staticmethod
    def _extract_market_price(market_data) -> float:
        """Extract current price from market data."""
        if not market_data:
            return 0.0
        price = market_data.get("current_price")
        if price is None:
            price = market_data.get("price", 0.0)
        try:
            return float(price)
        except (TypeError, ValueError):
            return 0.0

    # ==============================================================
    # SERIALIZATION
    # ==============================================================

    @staticmethod
    def _serialize_object(obj):
        """Serialize object to dict."""
        if obj is None:
            return None
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, list):
            return [TradingIntegrationEngine._serialize_object(item) for item in obj]
        if hasattr(obj, "to_dict"):
            try:
                return obj.to_dict()
            except Exception:
                pass
        if hasattr(obj, "__dict__"):
            result = {}
            for key, value in obj.__dict__.items():
                if isinstance(value, datetime):
                    result[key] = value.isoformat()
                elif hasattr(value, "value"):
                    result[key] = value.value
                else:
                    result[key] = value
            return result
        return obj

    # ==============================================================
    # VALUE HELPERS
    # ==============================================================

    @staticmethod
    def _get_value(obj, key, default=None):
        """Get value from object or dict."""
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    @staticmethod
    def _get_bool(obj, key, default=False):
        """Get boolean value."""
        return bool(TradingIntegrationEngine._get_value(obj, key, default))

    # ==============================================================
    # ERROR
    # ==============================================================

    def _build_error_result(self, symbol: str, timestamp: str, stage: str, error: str) -> Dict[str, Any]:
        """Build error result."""
        self.blocked_trades += 1
        result = {
            "timestamp": timestamp,
            "symbol": symbol,
            "status": "ERROR",
            "stage": stage,
            "action": "HOLD",
            "position_size": 0.0,
            "error": str(error)
        }
        self.last_cycle = result
        return result

    # ==============================================================
    # STATUS
    # ==============================================================

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

    # ==============================================================
    # START / STOP
    # ==============================================================

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


# ==================================================================
# TEST
# ==================================================================

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    print()
    print("=" * 70)
    print("AI TRADING INTEGRATION ENGINE v3 TEST - FULLY INTEGRATED")
    print("=" * 70)

    config = {
        "mode": "paper",
        "execution_allowed": True,
        "orchestrator": {
            "enable_dynamic_weights": True,
            "max_position_size": 0.20,
        },
        "risk_engine": {
            "minimum_confidence": 0.55,
            "max_position_size": 0.20,
            "minimum_risk_reward": 1.5,
        },
        "decision_engine": {
            "min_confidence": 0.60,
            "min_consensus": 0.20,
            "min_directional_edge": 0.15,
            "min_risk_reward": 1.50,
            "live_trading_enabled": False,
        },
        "execution_gate": {
            "min_confidence": 0.60,
            "min_risk_reward": 1.50,
            "max_position_size": 0.20,
        },
        "paper_trading": {
            "initial_balance": 10000.0,
            "max_position_size": 0.20,
        }
    }

    engine = TradingIntegrationEngine(config)
    engine.start()

    print()
    print("=" * 70)
    print("TEST — FULL PIPELINE")
    print("=" * 70)

    result = await engine.analyze_and_execute(
        symbol="BTC-USD",
        market_data={"current_price": 62760.21}
    )

    print()
    print("=" * 70)
    print("FINAL RESULT")
    print("=" * 70)
    print(json.dumps(result, indent=2, default=str))

    print()
    print("=" * 70)
    print("ENGINE STATUS")
    print("=" * 70)
    print(json.dumps(engine.get_status(), indent=2, default=str))

    engine.stop()


if __name__ == "__main__":
    asyncio.run(main())
