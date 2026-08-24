"""Real-market paper cycle coordinator.

Uses public Indodax data, the existing Orchestrator, Trading Librarian and
AdaptiveScalpingEngine, then sends the resulting action through the same
Executor used by the future live exchange adapter. No private API is used.
"""
from __future__ import annotations

from typing import Any, Dict

from agents.agent_trading_librarian import TradingLibrarianAgent
from core.adaptive_scalping import AdaptiveScalpingEngine
from core.executor import Executor
from core.orchestrator import Orchestrator


class LivePaperCycle:
    def __init__(self, config: Dict[str, Any] | None = None):
        cfg = config or {}
        self.orchestrator = Orchestrator(cfg.get("orchestrator", {}))
        self.librarian = TradingLibrarianAgent(cfg.get("trading_librarian", {}))
        self.scalper = AdaptiveScalpingEngine(cfg.get("adaptive_scalping", {}))
        self.executor = Executor({
            "exchange_mode": "paper",
            "paper": cfg.get("paper", {"initial_balance": 10_000_000.0}),
            "daily_loss_limit": cfg.get("daily_loss_limit", 0.05),
            "max_open_positions": cfg.get("max_open_positions", 1),
        })

    async def cycle(self, symbol: str = "BTC/IDR") -> Dict[str, Any]:
        symbol = symbol.upper()
        snapshot = self.orchestrator.market_data_provider.refresh_snapshot(
            symbol, timeframe="1m", limit=100, force=True
        )
        if snapshot is None or not snapshot.is_valid():
            return {
                "action": "HOLD",
                "executed": False,
                "reason": "market_data_unavailable",
                "market_data_valid": False,
            }

        # Position monitoring is part of every runtime cycle. This keeps paper
        # behavior aligned with the future live executor: an open position can
        # be closed by SL/TP even when the AI produces HOLD on the next tick.
        before_orders = len(self.executor.order_history)
        self.executor.monitor_positions()
        position_event = None
        if len(self.executor.order_history) > before_orders:
            position_event = self.executor.order_history[-1].metadata.get("close_reason")

        market_data = snapshot.to_dict()
        market_data["current_price"] = snapshot.current_price
        result = await self.orchestrator.analyze(symbol, market_data)

        librarian = self.librarian.advise("scalping momentum risk execution", limit=3)
        technical = getattr(result.technical, "overall_score", 0.0) if result.technical else 0.0
        sentiment = getattr(result.sentiment, "overall_score", 0.0) if result.sentiment else 0.0
        forecast = self.orchestrator._forecast_to_score(result.forecast) if result.forecast else 0.0
        mimic = (
            self.orchestrator._action_to_score(getattr(result.mimic_analysis, "recommendation", "HOLD"))
            if result.mimic_analysis else 0.0
        )
        momentum = self.orchestrator._calculate_momentum_score(
            result.technical, snapshot.current_price
        )
        scalping = self.scalper.evaluate(
            technical=float(technical),
            sentiment=float(sentiment),
            forecast=float(forecast),
            mimic=float(mimic),
            momentum=float(momentum),
            volatility=float(snapshot.volatility or 0.02),
            data_quality=float(snapshot.data_quality_score),
        )

        action = result.final_action
        # Scalping is an execution gate, not a blind trade-forcer. It may turn a
        # HOLD into a trade only when independent confirmation is strong and the
        # orchestrator is not directionally opposed.
        if (
            action == "HOLD"
            and scalping.action in {"BUY", "SELL"}
            and scalping.confidence >= self.scalper.min_confidence
        ):
            if (
                scalping.action == "BUY" and result.consensus_score >= -0.05
            ) or (
                scalping.action == "SELL" and result.consensus_score <= 0.05
            ):
                action = scalping.action

        position_size = result.position_size if action != "HOLD" else 0.0
        if action != "HOLD" and position_size <= 0:
            position_size = max(0.01, min(0.10, scalping.position_multiplier * 0.05))

        if action == "HOLD":
            return {
                "action": action,
                "executed": False,
                "price": snapshot.current_price,
                "confidence": result.final_confidence,
                "scalping": scalping.action,
                "scalping_confidence": scalping.confidence,
                "scalping_reason": scalping.reason,
                "position_event": position_event,
                "active_positions": len(self.executor.active_positions),
                "library_topics": [x.get("topic") for x in librarian.get("knowledge", [])],
                "market_data_valid": True,
            }

        order = self.executor.execute(
            symbol,
            action,
            max(result.final_confidence, scalping.confidence),
            position_size,
            stop_loss=result.stop_loss,
            take_profit=result.take_profit,
        )
        return {
            "action": action,
            "executed": order is not None,
            "price": snapshot.current_price,
            "confidence": max(result.final_confidence, scalping.confidence),
            "scalping": scalping.action,
            "scalping_confidence": scalping.confidence,
            "scalping_reason": scalping.reason,
            "position_event": position_event,
            "active_positions": len(self.executor.active_positions),
            "library_topics": [x.get("topic") for x in librarian.get("knowledge", [])],
            "market_data_valid": True,
            "order_id": order.order_id if order else None,
        }

    def runtime_summary(self) -> Dict[str, Any]:
        performance = self.executor.paper_trading.get_performance()
        summary = self.executor.get_summary()
        return {
            "executor": summary,
            "paper_performance": performance,
            "trade_history": self.executor.paper_trading.trade_history,
            "positions": self.executor.paper_trading.get_positions(),
        }
