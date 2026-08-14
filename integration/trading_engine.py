"""
Trading Integration Engine

Menghubungkan seluruh pipeline trading:

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

IMPORTANT:
- Default execution = PAPER
- Tidak melakukan live trading
- Semua keputusan harus melewati seluruh layer
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from core.orchestrator import Orchestrator
from core.risk_engine import RiskEngine
from core.decision_engine import DecisionEngine
from core.execution_gate import ExecutionGate

from paper_trading.paper_engine import PaperTradingEngine


logger = logging.getLogger(__name__)


class TradingIntegrationEngine:

    def __init__(self, config: Optional[Dict[str, Any]] = None):

        self.config = config or {}

        # ==========================================================
        # SAFETY
        # ==========================================================

        self.mode = self.config.get("mode", "paper")

        # Hard safety:
        # Integration engine ini tidak mengizinkan live execution.
        if self.mode != "paper":
            raise ValueError(
                "TradingIntegrationEngine hanya mendukung PAPER mode."
            )

        # ==========================================================
        # COMPONENTS
        # ==========================================================

        self.orchestrator = Orchestrator(
            self.config.get("orchestrator", {})
        )

        self.risk_engine = RiskEngine(
            self.config.get("risk_engine", {})
        )

        self.decision_engine = DecisionEngine(
            self.config.get("decision_engine", {})
        )

        self.execution_gate = ExecutionGate(
            self.config.get("execution_gate", {})
        )

        self.paper_engine = PaperTradingEngine(
            self.config.get("paper_trading", {})
        )

        # ==========================================================
        # STATE
        # ==========================================================

        self.running = False

        self.last_cycle: Optional[Dict[str, Any]] = None

        self.total_cycles = 0
        self.executed_trades = 0
        self.blocked_trades = 0

        logger.info(
            "Trading Integration Engine initialized | MODE=%s",
            self.mode
        )

    # ==============================================================
    # MAIN PIPELINE
    # ==============================================================

    async def analyze_and_execute(
        self,
        symbol: str,
        market_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:

        self.total_cycles += 1

        timestamp = datetime.now(timezone.utc).isoformat()

        logger.info(
            "=================================================="
        )

        logger.info(
            "TRADING CYCLE #%s | %s",
            self.total_cycles,
            symbol
        )

        logger.info(
            "=================================================="
        )

        # ----------------------------------------------------------
        # 1. ORCHESTRATOR
        # ----------------------------------------------------------

        try:

            orchestrator_result = await self.orchestrator.analyze(
                symbol,
                market_data
            )

        except Exception as e:

            logger.exception(
                "Orchestrator failed"
            )

            return self._build_error_result(
                symbol,
                timestamp,
                "ORCHESTRATOR_ERROR",
                str(e)
            )

        # ----------------------------------------------------------
        # Extract orchestrator data
        # ----------------------------------------------------------

        current_price = getattr(
            orchestrator_result,
            "current_price",
            0.0
        )

        action = getattr(
            orchestrator_result,
            "final_action",
            "HOLD"
        )

        confidence = getattr(
            orchestrator_result,
            "final_confidence",
            0.0
        )

        position_size = getattr(
            orchestrator_result,
            "position_size",
            0.0
        )

        consensus_score = getattr(
            orchestrator_result,
            "consensus_score",
            0.0
        )

        stop_loss = getattr(
            orchestrator_result,
            "stop_loss",
            None
        )

        take_profit = getattr(
            orchestrator_result,
            "take_profit",
            None
        )

        logger.info(
            "ORCHESTRATOR | %s | confidence=%.2f | consensus=%.4f",
            action,
            confidence,
            consensus_score
        )

        # ----------------------------------------------------------
        # HOLD
        # ----------------------------------------------------------

        if action == "HOLD":

            result = {
                "timestamp": timestamp,
                "symbol": symbol,
                "status": "NO_TRADE",
                "stage": "ORCHESTRATOR",
                "action": "HOLD",
                "confidence": confidence,
                "position_size": 0.0,
                "reason": "Orchestrator returned HOLD",
                "orchestrator": self._serialize_object(
                    orchestrator_result
                )
            }

            self.last_cycle = result

            return result

        # ==========================================================
        # 2. RISK ENGINE
        # ==========================================================

        try:

            risk_result = self.risk_engine.evaluate(
                symbol=symbol,
                action=action,
                confidence=confidence,
                position_size=position_size,
                current_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit
            )

        except TypeError:

            # Compatibility fallback untuk RiskEngine
            risk_result = self.risk_engine.evaluate(
                symbol,
                action,
                confidence,
                position_size,
                current_price,
                stop_loss,
                take_profit
            )

        except Exception as e:

            logger.exception(
                "Risk Engine failed"
            )

            return self._build_error_result(
                symbol,
                timestamp,
                "RISK_ENGINE_ERROR",
                str(e)
            )

        risk_dict = self._serialize_object(risk_result)

        risk_score = self._get_value(
            risk_result,
            "risk_score",
            1.0
        )

        risk_reward_ratio = self._get_value(
            risk_result,
            "risk_reward_ratio",
            0.0
        )

        logger.info(
            "RISK ENGINE | score=%.4f | RR=%.2f",
            risk_score,
            risk_reward_ratio
        )

        # ----------------------------------------------------------
        # Risk rejection
        # ----------------------------------------------------------

        risk_approved = self._get_bool(
            risk_result,
            "approved",
            False
        )

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
                "reason": "Risk engine rejected trade"
            }

            self.last_cycle = result

            return result

        # ==========================================================
        # 3. DECISION ENGINE
        # ==========================================================

        try:

            decision_result = self.decision_engine.evaluate(
                symbol=symbol,
                action=action,
                confidence=confidence,
                position_size=position_size,
                risk_score=risk_score,
                consensus_score=consensus_score,
                risk_reward_ratio=risk_reward_ratio,
                current_price=current_price
            )

        except TypeError:

            decision_result = self.decision_engine.evaluate(
                symbol,
                action,
                confidence,
                position_size,
                risk_score,
                consensus_score,
                risk_reward_ratio,
                current_price
            )

        except Exception as e:

            logger.exception(
                "Decision Engine failed"
            )

            return self._build_error_result(
                symbol,
                timestamp,
                "DECISION_ENGINE_ERROR",
                str(e)
            )

        decision_dict = self._serialize_object(
            decision_result
        )

        decision_approved = self._get_bool(
            decision_result,
            "approved",
            False
        )

        decision_action = self._get_value(
            decision_result,
            "action",
            "HOLD"
        )

        decision_confidence = self._get_value(
            decision_result,
            "confidence",
            confidence
        )

        decision_position_size = self._get_value(
            decision_result,
            "position_size",
            position_size
        )

        logger.info(
            "DECISION ENGINE | %s | approved=%s",
            decision_action,
            decision_approved
        )

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
                "reason": "Decision engine rejected trade"
            }

            self.last_cycle = result

            return result

        # ==========================================================
        # 4. EXECUTION GATE
        # ==========================================================

        execution_allowed_config = self.config.get(
            "execution_allowed",
            True
        )

        try:

            gate_result = self.execution_gate.evaluate(
                symbol=symbol,
                action=decision_action,
                confidence=decision_confidence,
                position_size=decision_position_size,
                risk_reward_ratio=risk_reward_ratio,
                approved=decision_approved,
                execution_allowed=execution_allowed_config
            )

        except TypeError:

            gate_result = self.execution_gate.evaluate(
                symbol,
                decision_action,
                decision_confidence,
                decision_position_size,
                risk_reward_ratio,
                decision_approved,
                execution_allowed_config
            )

        except Exception as e:

            logger.exception(
                "Execution Gate failed"
            )

            return self._build_error_result(
                symbol,
                timestamp,
                "EXECUTION_GATE_ERROR",
                str(e)
            )

        gate_dict = self._serialize_object(
            gate_result
        )

        gate_allowed = self._get_bool(
            gate_result,
            "allowed",
            False
        )

        logger.info(
            "EXECUTION GATE | allowed=%s",
            gate_allowed
        )

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
                "reason": self._get_value(
                    gate_result,
                    "reason",
                    "Execution gate blocked trade"
                )
            }

            self.last_cycle = result

            return result

        # ==========================================================
        # 5. PAPER TRADING
        # ==========================================================

        if self.mode != "paper":

            raise RuntimeError(
                "Safety violation: non-paper execution requested."
            )

        logger.info(
            "PAPER EXECUTION | %s | %s | %.2f%%",
            symbol,
            decision_action,
            decision_position_size * 100
        )

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

            logger.exception(
                "Paper Trading execution failed"
            )

            return self._build_error_result(
                symbol,
                timestamp,
                "PAPER_EXECUTION_ERROR",
                str(e)
            )

        paper_dict = self._serialize_object(
            paper_result
        )

        self.executed_trades += 1

        # ==========================================================
        # FINAL RESULT
        # ==========================================================

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
                "orchestrator": self._serialize_object(
                    orchestrator_result
                ),

                "risk_engine": risk_dict,

                "decision_engine": decision_dict,

                "execution_gate": gate_dict,

                "paper_trading": paper_dict
            }
        }

        self.last_cycle = result

        logger.info(
            "PAPER TRADE COMPLETED | %s | %s",
            symbol,
            decision_action
        )

        return result

    # ==============================================================
    # PAPER EXECUTION ADAPTER
    # ==============================================================

    def _execute_paper(
        self,
        symbol: str,
        action: str,
        position_size: float,
        confidence: float,
        current_price: float,
        stop_loss: Optional[float],
        take_profit: Optional[float]
    ):

        """
        Adapter antara Integration Engine dan PaperTradingEngine.

        Karena implementasi PaperTradingEngine bisa memiliki
        signature berbeda, kita coba beberapa interface umum.
        """

        # ----------------------------------------------------------
        # Preferred interface
        # ----------------------------------------------------------

        if hasattr(self.paper_engine, "open_position"):

            return self.paper_engine.open_position(
                symbol=symbol,
                side=action,
                position_size=position_size,
                confidence=confidence,
                price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                metadata={
                    "source": "integration_engine",
                    "strategy": "AI_SCALPING",
                    "mode": "paper"
                }
            )

        # ----------------------------------------------------------
        # Alternative interface
        # ----------------------------------------------------------

        if hasattr(self.paper_engine, "execute_order"):

            quantity = (
                self._get_portfolio_value()
                * position_size
                / current_price
            )

            return self.paper_engine.execute_order(
                symbol=symbol,
                side=action,
                quantity=quantity,
                price=current_price
            )

        raise AttributeError(
            "PaperTradingEngine tidak memiliki "
            "open_position() atau execute_order()."
        )

    # ==============================================================
    # PORTFOLIO
    # ==============================================================

    def _get_portfolio_value(self) -> float:

        if hasattr(
            self.paper_engine,
            "get_portfolio_value"
        ):

            return self.paper_engine.get_portfolio_value()

        if hasattr(
            self.paper_engine,
            "get_summary"
        ):

            summary = self.paper_engine.get_summary()

            return summary.get(
                "equity",
                summary.get(
                    "balance",
                    10000.0
                )
            )

        return 10000.0

    # ==============================================================
    # SERIALIZATION
    # ==============================================================

    def _serialize_object(self, obj):

        if obj is None:
            return None

        if isinstance(obj, dict):
            return obj

        if hasattr(obj, "to_dict"):

            try:
                return obj.to_dict()
            except Exception:
                pass

        if hasattr(obj, "__dict__"):

            result = {}

            for key, value in obj.__dict__.items():

                if isinstance(
                    value,
                    datetime
                ):

                    result[key] = value.isoformat()

                elif hasattr(
                    value,
                    "value"
                ):

                    result[key] = value.value

                else:

                    result[key] = value

            return result

        return obj

    # ==============================================================
    # HELPERS
    # ==============================================================

    @staticmethod
    def _get_value(
        obj,
        key,
        default=None
    ):

        if obj is None:
            return default

        if isinstance(obj, dict):
            return obj.get(
                key,
                default
            )

        return getattr(
            obj,
            key,
            default
        )

    @staticmethod
    def _get_bool(
        obj,
        key,
        default=False
    ):

        value = TradingIntegrationEngine._get_value(
            obj,
            key,
            default
        )

        return bool(value)

    def _build_error_result(
        self,
        symbol,
        timestamp,
        stage,
        error
    ):

        self.blocked_trades += 1

        result = {
            "timestamp": timestamp,
            "symbol": symbol,
            "status": "ERROR",
            "stage": stage,
            "action": "HOLD",
            "position_size": 0.0,
            "error": error
        }

        self.last_cycle = result

        return result

    # ==============================================================
    # STATUS
    # ==============================================================

    def get_status(self) -> Dict[str, Any]:

        paper_summary = {}

        if hasattr(
            self.paper_engine,
            "get_summary"
        ):

            try:
                paper_summary = (
                    self.paper_engine.get_summary()
                )
            except Exception as e:

                logger.error(
                    "Unable to get paper summary: %s",
                    e
                )

        return {
            "mode": self.mode,

            "running": self.running,

            "total_cycles": self.total_cycles,

            "executed_trades": self.executed_trades,

            "blocked_trades": self.blocked_trades,

            "paper_trading": paper_summary,

            "last_cycle": self.last_cycle
        }

    # ==============================================================
    # START / STOP
    # ==============================================================

    def start(self):

        self.running = True

        logger.info(
            "Trading Integration Engine STARTED"
        )

    def stop(self):

        self.running = False

        logger.info(
            "Trading Integration Engine STOPPED"
        )


# ==============================================================
# TEST
# ==============================================================

async def main():

    logging.basicConfig(
        level=logging.INFO
    )

    print()
    print("=" * 70)
    print("AI TRADING INTEGRATION ENGINE TEST")
    print("=" * 70)
    print()

    engine = TradingIntegrationEngine({
        "mode": "paper",

        # PAPER execution diperbolehkan
        "execution_allowed": True,

        "paper_trading": {
            "initial_balance": 10000.0
        }
    })

    engine.start()

    result = await engine.analyze_and_execute(
        symbol="BTC-USD",
        market_data={
            "current_price": 62760.21
        }
    )

    print()
    print("=" * 70)
    print("FINAL RESULT")
    print("=" * 70)

    import json

    print(
        json.dumps(
            result,
            indent=2,
            default=str
        )
    )

    print()
    print("=" * 70)
    print("ENGINE STATUS")
    print("=" * 70)

    print(
        json.dumps(
            engine.get_status(),
            indent=2,
            default=str
        )
    )

    engine.stop()


if __name__ == "__main__":

    asyncio.run(main())
