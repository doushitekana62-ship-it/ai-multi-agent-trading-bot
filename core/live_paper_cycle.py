"""Canonical real-market paper cycle.

One cycle uses one unified Indodax snapshot, the canonical orchestrator, the
mandatory deterministic risk gate, and one paper executor/ledger. There is no
secondary scalping decision path and no second market-price fetch for fills.
"""
from __future__ import annotations
from typing import Any, Dict
from agents.agent_trading_librarian import TradingLibrarianAgent
from core.execution_gate import ExecutionGate
from core.executor import Executor
from core.orchestrator import Orchestrator
from core.risk_engine import RiskEngine
from core.runtime_state import set_last_orchestrator_result

class LivePaperCycle:
    def __init__(self, config: Dict[str, Any] | None = None):
        cfg = config or {}
        self.orchestrator = Orchestrator(cfg.get("orchestrator", {}))
        self.librarian = TradingLibrarianAgent(cfg.get("trading_librarian", {}))
        self.risk = RiskEngine(cfg.get("risk", {
            "initial_capital": 10_000_000.0,
            "max_open_positions": min(3, int(cfg.get("max_open_positions", 3))),
        }))
        self.execution_gate = ExecutionGate(cfg.get("execution_gate", {
            "min_confidence": 0.75,
            "min_risk_reward": 1.50,
            "max_position_size": 0.20,
            "require_approved": True,
            "require_execution_allowed": True,
        }))
        self.executor = Executor({
            "exchange_mode": "paper",
            "paper": cfg.get("paper", {"initial_balance": 10_000_000.0}),
            "daily_loss_limit": cfg.get("daily_loss_limit", 0.05),
            "max_open_positions": min(3, int(cfg.get("max_open_positions", 3))),
        })

    async def cycle(self, symbol: str = "BTC/IDR") -> Dict[str, Any]:
        symbol = symbol.upper()
        snapshot = self.orchestrator.market_data_provider.refresh_snapshot(symbol, timeframe="1m", limit=180, force=True)
        if snapshot is None or not snapshot.is_valid():
            return {"action": "HOLD", "executed": False, "reason": "DATA_UNAVAILABLE", "cycle_status": "DATA_UNAVAILABLE", "market_data_valid": False}

        price = float(snapshot.current_price)
        before = len(self.executor.order_history)
        self.executor.monitor_positions({symbol: price})
        position_event = self.executor.order_history[-1].metadata.get("close_reason") if len(self.executor.order_history) > before else None

        market_data = snapshot.to_dict()
        market_data.update({"current_price": price, "unified_price": price, "timeframe": "1m"})
        result = await self.orchestrator.analyze(symbol, market_data)
        set_last_orchestrator_result(result)

        action = result.final_action
        confidence = float(result.final_confidence)
        if action == "HOLD":
            return {"action": "HOLD", "executed": False, "price": price, "confidence": confidence,
                    "reason": result.hold_reason or result.execution_reason, "cycle_status": result.cycle_status,
                    "position_event": position_event, "active_positions": len(self.executor.active_positions), "market_data_valid": True}

        if action in {"BUY", "STRONG_BUY"}:
            stop_loss = price * 0.995
            take_profit = price * 1.010
        elif action in {"SELL", "STRONG_SELL"}:
            stop_loss = price * 1.005
            take_profit = price * 0.990
        else:
            return {"action": "HOLD", "executed": False, "price": price, "confidence": confidence,
                    "reason": "INVALID_CANDIDATE_ACTION", "cycle_status": "NO_EDGE", "market_data_valid": True}

        position_size = float(result.position_size)
        if position_size <= 0:
            return {"action": action, "executed": False, "price": price, "confidence": confidence,
                    "reason": "ZERO_POSITION_SIZE", "cycle_status": "RISK_REJECTED", "market_data_valid": True}

        # Risk is evaluated before the execution gate. Neither layer can change direction.
        summary = self.executor.get_summary()
        risk_decision = self.risk.evaluate(
            symbol=symbol, action=action, confidence=confidence, position_size=position_size,
            entry_price=price, stop_loss=stop_loss, take_profit=take_profit,
            volatility=float(snapshot.volatility or 0.0),
            current_exposure=float(sum(float(p.get("quantity", 0.0)) * price / max(self.executor._get_portfolio_value(), 1e-9) for p in self.executor.active_positions.values())),
            open_positions=len(self.executor.active_positions), daily_pnl=float(summary.get("daily_pnl", 0.0)),
        )
        if not risk_decision.approved:
            return {"action": action, "executed": False, "price": price, "confidence": confidence,
                    "reason": risk_decision.reason, "cycle_status": "RISK_REJECTED", "risk": risk_decision.to_dict(),
                    "position_event": position_event, "active_positions": len(self.executor.active_positions), "market_data_valid": True}

        gate = self.execution_gate.evaluate(
            symbol=symbol, action=action, confidence=confidence,
            position_size=risk_decision.approved_position_size,
            risk_reward_ratio=risk_decision.risk_reward_ratio,
            approved=risk_decision.approved, execution_allowed=True,
        )
        if not gate.allowed:
            return {"action": action, "executed": False, "price": price, "confidence": confidence,
                    "reason": gate.reason, "cycle_status": "RISK_REJECTED", "risk": risk_decision.to_dict(),
                    "execution_gate": gate.to_dict(), "position_event": position_event,
                    "active_positions": len(self.executor.active_positions), "market_data_valid": True}

        order = self.executor.execute(symbol, action, confidence, risk_decision.approved_position_size,
                                      stop_loss, take_profit, market_price=price)
        return {"action": action, "executed": order is not None, "price": price, "confidence": confidence,
                "reason": "EXECUTED" if order else "EXECUTION_FAILED", "cycle_status": "EXECUTED" if order else "RISK_REJECTED",
                "risk": risk_decision.to_dict(), "execution_gate": gate.to_dict(), "position_event": position_event,
                "active_positions": len(self.executor.active_positions), "market_data_valid": True,
                "order_id": order.order_id if order else None}

    def runtime_summary(self) -> Dict[str, Any]:
        return {"executor": self.executor.get_summary(), "paper_performance": self.executor.paper_trading.get_performance(),
                "trade_history": self.executor.paper_trading.trade_history, "positions": self.executor.paper_trading.get_positions()}
