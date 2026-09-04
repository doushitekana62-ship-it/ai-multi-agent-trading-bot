"""Canonical real-market paper cycle with mandatory data-quality gates.

Flow:
    Market snapshot -> freshness/quality gate -> agents -> deterministic risk
    -> execution gate -> paper executor/ledger.

Real trading remains disabled by architecture.
"""
from __future__ import annotations

import os
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
        self.market_data_max_age_seconds = float(
            cfg.get("market_data_max_age_seconds", os.getenv("MARKET_DATA_MAX_AGE_SECONDS", "90"))
        )
        self.min_market_quality = float(cfg.get("min_market_quality", 0.70))
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

    def _market_quality_gate(self, snapshot) -> tuple[bool, str]:
        if snapshot is None:
            return False, "DATA_UNAVAILABLE"
        snapshot.is_stale(self.market_data_max_age_seconds)
        if not snapshot.is_fresh:
            return False, "DATA_STALE"
        if float(snapshot.data_quality_score or 0.0) < self.min_market_quality:
            return False, "DATA_QUALITY_LOW"
        if float(snapshot.current_price or 0.0) <= 0:
            return False, "INVALID_PRICE"
        return True, "OK"

    async def cycle(self, symbol: str = "BTC/IDR") -> Dict[str, Any]:
        symbol = symbol.upper()
        snapshot = self.orchestrator.market_data_provider.refresh_snapshot(
            symbol, timeframe="1m", limit=180, force=True
        )
        market_ok, market_reason = self._market_quality_gate(snapshot)
        if not market_ok:
            return {
                "action": "HOLD", "executed": False, "reason": market_reason,
                "cycle_status": market_reason, "market_data_valid": False,
                "market_data_fresh": False if snapshot is None else bool(snapshot.is_fresh),
                "market_data_age_seconds": None if snapshot is None else snapshot.age_seconds,
                "market_data_quality_score": None if snapshot is None else snapshot.data_quality_score,
            }

        price = float(snapshot.current_price)
        before = len(self.executor.order_history)
        self.executor.monitor_positions({symbol: price})
        position_event = self.executor.order_history[-1].metadata.get("close_reason") if len(self.executor.order_history) > before else None

        market_data = snapshot.to_dict()
        market_data.update({
            "current_price": price, "unified_price": price, "timeframe": "1m",
            "market_data_fresh": True, "market_data_age_seconds": snapshot.age_seconds,
            "market_data_quality_score": snapshot.data_quality_score,
        })
        result = await self.orchestrator.analyze(symbol, market_data)
        set_last_orchestrator_result(result)

        action = result.final_action
        confidence = float(result.final_confidence)
        common = {
            "price": price, "confidence": confidence,
            "market_data_valid": True, "market_data_fresh": True,
            "market_data_age_seconds": snapshot.age_seconds,
            "market_data_quality_score": snapshot.data_quality_score,
        }
        if action == "HOLD":
            return {"action": "HOLD", "executed": False, **common,
                    "reason": result.hold_reason or result.execution_reason, "cycle_status": result.cycle_status,
                    "position_event": position_event, "active_positions": len(self.executor.active_positions)}

        if action in {"BUY", "STRONG_BUY"}:
            stop_loss = price * 0.995
            take_profit = price * 1.010
        elif action in {"SELL", "STRONG_SELL"}:
            stop_loss = price * 1.005
            take_profit = price * 0.990
        else:
            return {"action": "HOLD", "executed": False, **common,
                    "reason": "INVALID_CANDIDATE_ACTION", "cycle_status": "NO_EDGE"}

        position_size = float(result.position_size)
        if position_size <= 0:
            return {"action": action, "executed": False, **common,
                    "reason": "ZERO_POSITION_SIZE", "cycle_status": "RISK_REJECTED"}

        summary = self.executor.get_summary()
        risk_decision = self.risk.evaluate(
            symbol=symbol, action=action, confidence=confidence, position_size=position_size,
            entry_price=price, stop_loss=stop_loss, take_profit=take_profit,
            volatility=float(snapshot.volatility or 0.0),
            current_exposure=float(sum(float(p.get("quantity", 0.0)) * price / max(self.executor._get_portfolio_value(), 1e-9) for p in self.executor.active_positions.values())),
            open_positions=len(self.executor.active_positions), daily_pnl=float(summary.get("daily_pnl", 0.0)),
        )
        if not risk_decision.approved:
            return {"action": action, "executed": False, **common,
                    "reason": risk_decision.reason, "cycle_status": "RISK_REJECTED", "risk": risk_decision.to_dict(),
                    "position_event": position_event, "active_positions": len(self.executor.active_positions)}

        # Freshness and quality have already passed as a hard gate immediately
        # before analysis. Execution remains paper-only and risk-controlled.
        gate = self.execution_gate.evaluate(
            symbol=symbol, action=action, confidence=confidence,
            position_size=risk_decision.approved_position_size,
            risk_reward_ratio=risk_decision.risk_reward_ratio,
            approved=risk_decision.approved, execution_allowed=True,
        )
        if not gate.allowed:
            return {"action": action, "executed": False, **common,
                    "reason": gate.reason, "cycle_status": "RISK_REJECTED", "risk": risk_decision.to_dict(),
                    "execution_gate": gate.to_dict(), "position_event": position_event,
                    "active_positions": len(self.executor.active_positions)}

        order = self.executor.execute(
            symbol, action, confidence, risk_decision.approved_position_size,
            stop_loss, take_profit, market_price=price,
        )
        return {"action": action, "executed": order is not None, **common,
                "reason": "EXECUTED" if order else "EXECUTION_FAILED",
                "cycle_status": "EXECUTED" if order else "RISK_REJECTED",
                "risk": risk_decision.to_dict(), "execution_gate": gate.to_dict(),
                "position_event": position_event, "active_positions": len(self.executor.active_positions),
                "order_id": order.order_id if order else None}

    def runtime_summary(self) -> Dict[str, Any]:
        return {
            "executor": self.executor.get_summary(),
            "paper_performance": self.executor.paper_trading.get_performance(),
            "trade_history": self.executor.paper_trading.trade_history,
            "positions": self.executor.paper_trading.get_positions(),
            "market_data_max_age_seconds": self.market_data_max_age_seconds,
            "min_market_quality": self.min_market_quality,
        }
