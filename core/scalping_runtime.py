"""Stateful scalping runtime adapter.

Keeps strategy evaluation and paper position lifecycle together so replay/live
loops can use the same BUY -> position -> SELL/SL/TP state machine.
This module does not bypass RiskEngine/ExecutionGate; it is an execution-neutral
strategy adapter intended to be called after those gates in the production path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence

from core.scalping_controller import ScalpingController
from paper_trading.paper_engine import PaperTradingEngine


@dataclass
class ScalpingRuntimeState:
    cycles: int = 0
    entries: int = 0
    exits: int = 0
    holds: int = 0
    stop_losses: int = 0
    take_profits: int = 0
    realized_pnl: float = 0.0
    events: list[Dict[str, Any]] = field(default_factory=list)


class ScalpingRuntime:
    """Stateful BUY/SELL lifecycle for deterministic paper/replay testing."""

    def __init__(
        self,
        controller: Optional[ScalpingController] = None,
        paper_engine: Optional[PaperTradingEngine] = None,
        symbol: str = "BTC/IDR",
        position_size: float = 0.05,
    ) -> None:
        self.controller = controller or ScalpingController()
        self.paper = paper_engine or PaperTradingEngine()
        self.symbol = symbol.upper()
        self.position_size = float(position_size)
        self.state = ScalpingRuntimeState()

    def step(
        self,
        *,
        price: float,
        technical: float,
        sentiment: float,
        forecast: float,
        mimic: float,
        decision: float = 0.0,
        volatility: float = 0.02,
        data_quality: float = 1.0,
        prices: Optional[Sequence[float]] = None,
        volumes: Optional[Sequence[float]] = None,
    ) -> Dict[str, Any]:
        self.state.cycles += 1

        setup = self.controller.evaluate(
            technical=technical,
            sentiment=sentiment,
            forecast=forecast,
            mimic=mimic,
            decision=decision,
            volatility=volatility,
            data_quality=data_quality,
            prices=prices,
            volumes=volumes,
        )

        existing_before = self.paper.get_position(self.symbol)
        closed = self.paper.update_price(self.symbol, float(price)) if existing_before else None
        if closed:
            self._record_close(closed)

        existing = self.paper.get_position(self.symbol)
        event: Dict[str, Any] = {
            "cycle": self.state.cycles,
            "price": float(price),
            "setup_action": setup.action,
            "setup": setup.setup,
            "score": setup.score,
            "confidence": setup.confidence,
            "regime": setup.regime,
            "confirmations": setup.confirmations,
            "position_before": bool(existing_before),
            "action": "HOLD",
        }

        if closed:
            event["action"] = "SELL" if closed.get("side") == "BUY" else "BUY"
            reason = str(closed.get("reason", "RISK_EXIT"))
            event["exit_reason"] = reason
            event["trade"] = closed
            self.state.events.append(event)
            return event

        if existing and existing.get("side") == "BUY":
            if setup.action == "SELL":
                trade = self.paper.close_position(self.symbol, float(price), "SCALP_EXIT")
                if trade:
                    self._record_manual_close(trade)
                    event["action"] = "SELL"
                    event["exit_reason"] = "STRATEGY_REVERSAL"
                    event["trade"] = trade
                    self.state.events.append(event)
                    return event

            should_exit, exit_signal = self.controller.should_exit_long(
                technical=technical,
                sentiment=sentiment,
                forecast=forecast,
                mimic=mimic,
                decision=decision,
                volatility=volatility,
                data_quality=data_quality,
                prices=prices,
                volumes=volumes,
            )
            if should_exit:
                trade = self.paper.close_position(self.symbol, float(price), "SCALP_EXIT")
                if trade:
                    self._record_manual_close(trade)
                    event["action"] = "SELL"
                    event["exit_reason"] = "DEDICATED_LONG_EXIT"
                    event["exit_signal"] = exit_signal
                    event["trade"] = trade
                    self.state.events.append(event)
                    return event

            self.state.holds += 1
        elif not existing and setup.action == "BUY":
            stop = float(price) * (1.0 - setup.stop_distance_pct)
            target = float(price) * (1.0 + setup.take_profit_pct)
            position = self.paper.open_position(
                symbol=self.symbol,
                side="BUY",
                price=float(price),
                position_size=min(self.position_size, self.paper.max_position_size),
                confidence=setup.confidence,
                stop_loss=stop,
                take_profit=target,
                metadata={"strategy": "AI_SCALPING", "setup": setup.setup},
            )
            if position:
                self.state.entries += 1
                event["action"] = "BUY"
                event["position"] = position
            else:
                self.state.holds += 1
        else:
            self.state.holds += 1

        self.state.events.append(event)
        return event

    def _record_close(self, trade: Dict[str, Any]) -> None:
        self.state.exits += 1
        self.state.realized_pnl += float(trade.get("pnl", 0.0))
        reason = str(trade.get("reason", "MANUAL"))
        if reason == "STOP_LOSS":
            self.state.stop_losses += 1
        elif reason == "TAKE_PROFIT":
            self.state.take_profits += 1

    def _record_manual_close(self, trade: Dict[str, Any]) -> None:
        self._record_close(trade)

    def summary(self) -> Dict[str, Any]:
        return {
            "cycles": self.state.cycles,
            "entries": self.state.entries,
            "exits": self.state.exits,
            "holds": self.state.holds,
            "stop_losses": self.state.stop_losses,
            "take_profits": self.state.take_profits,
            "realized_pnl": self.state.realized_pnl,
            "balance": self.paper.get_balance(),
            "active_position": self.paper.get_position(self.symbol),
            "trades": list(self.paper.trade_history),
        }
