"""Persistent paper-trading state backed by a Durable Object.

This object is the authoritative safety boundary for paper mode. It never
contains exchange credentials and it can never execute a real order.
"""
from __future__ import annotations

from datetime import datetime, timezone
from workers import DurableObject


DEFAULT_STATE = {
    "enabled": False,
    "mode": "paper",
    "cycle_running": False,
    "started_at": None,
    "last_cycle_at": None,
    "cycles_today": 0,
    "balance": 10_000_000.0,
    "initial_balance": 10_000_000.0,
    "portfolio_value": 10_000_000.0,
    "daily_pnl": 0.0,
    "total_pnl": 0.0,
    "daily_trades": 0,
    "total_trades": 0,
    "active_positions": 0,
    "max_open_positions": 5,
    "decision_counts": {"BUY": 0, "SELL": 0, "HOLD": 0},
    "positions": [],
    "last_decision": None,
    "updated_at": None,
}


def _now():
    return datetime.now(timezone.utc).isoformat()


class PaperTradingState(DurableObject):
    """Single authoritative state for the dashboard paper-trading session."""

    def __init__(self, ctx, env):
        super().__init__(ctx, env)
        self.ctx = ctx
        self.env = env

    async def _get(self):
        state = await self.ctx.storage.get("state")
        if not isinstance(state, dict):
            state = dict(DEFAULT_STATE)
            state["decision_counts"] = dict(DEFAULT_STATE["decision_counts"])
            state["positions"] = []
            await self.ctx.storage.put("state", state)
        state.setdefault("decision_counts", {"BUY": 0, "SELL": 0, "HOLD": 0})
        state.setdefault("positions", [])
        return state

    async def get_state(self):
        return await self._get()

    async def start(self):
        state = await self._get()
        now = _now()
        state["enabled"] = True
        state["mode"] = "paper"
        state["cycle_running"] = False
        state["started_at"] = state["started_at"] or now
        state["updated_at"] = now
        await self.ctx.storage.put("state", state)
        return state

    async def stop(self):
        state = await self._get()
        state["enabled"] = False
        state["cycle_running"] = False
        state["updated_at"] = _now()
        await self.ctx.storage.put("state", state)
        return state

    async def reset(self):
        state = dict(DEFAULT_STATE)
        state["decision_counts"] = dict(DEFAULT_STATE["decision_counts"])
        state["positions"] = []
        state["updated_at"] = _now()
        await self.ctx.storage.put("state", state)
        return state

    async def begin_cycle(self):
        state = await self._get()
        if not state.get("enabled"):
            return False, state, "paper_trading_disabled"
        if state.get("cycle_running"):
            return False, state, "cycle_already_running"
        state["cycle_running"] = True
        state["updated_at"] = _now()
        await self.ctx.storage.put("state", state)
        return True, state, None

    async def finish_cycle(self):
        state = await self._get()
        state["cycle_running"] = False
        state["updated_at"] = _now()
        await self.ctx.storage.put("state", state)
        return state

    async def record_cycle(self, decision=None, confidence=0.0, symbol="BTC/IDR", price=0.0, reasoning=""):
        """Record a completed cycle and simulate a paper order when actionable."""
        state = await self._get()
        if not state.get("enabled"):
            return state

        now = _now()
        action = str(decision or "HOLD").upper()
        if action not in {"BUY", "SELL", "HOLD"}:
            action = "HOLD"
        price = float(price or 0)
        confidence = max(0.0, min(1.0, float(confidence or 0.0)))

        positions = list(state.get("positions") or [])
        position = next((p for p in positions if p.get("symbol") == symbol), None)
        executed = False
        realized = 0.0

        # Paper-only position model: allocate 20% of available IDR on BUY.
        if action == "BUY" and price > 0 and position is None and len(positions) < int(state.get("max_open_positions", 5)):
            allocation = min(state["balance"] * 0.20, state["balance"])
            if allocation > 0:
                quantity = allocation / price
                positions.append({
                    "symbol": symbol,
                    "side": "BUY",
                    "quantity": quantity,
                    "entry_price": price,
                    "price": price,
                    "pnl": 0.0,
                    "confidence": confidence,
                    "created_at": now,
                })
                state["balance"] -= allocation
                executed = True

        elif action == "SELL" and price > 0 and position is not None:
            proceeds = position["quantity"] * price
            realized = proceeds - (position["quantity"] * position["entry_price"])
            state["balance"] += proceeds
            positions = [p for p in positions if p is not position]
            state["daily_pnl"] += realized
            state["total_pnl"] += realized
            executed = True

        for p in positions:
            if p.get("symbol") == symbol and price > 0:
                p["price"] = price
                p["pnl"] = (price - float(p.get("entry_price", price))) * float(p.get("quantity", 0))

        state["positions"] = positions
        state["active_positions"] = len(positions)
        state["portfolio_value"] = state["balance"] + sum(
            float(p.get("quantity", 0)) * float(p.get("price", p.get("entry_price", 0)))
            for p in positions
        )
        state["cycles_today"] = int(state.get("cycles_today", 0)) + 1
        state["last_cycle_at"] = now
        state["decision_counts"][action] = int(state["decision_counts"].get(action, 0)) + 1
        if executed:
            state["daily_trades"] = int(state.get("daily_trades", 0)) + 1
            state["total_trades"] = int(state.get("total_trades", 0)) + 1
        state["last_decision"] = {
            "action": action,
            "confidence": confidence,
            "symbol": symbol,
            "price": price,
            "executed": executed,
            "realized_pnl": realized,
            "reasoning": reasoning,
            "created_at": now,
        }
        state["cycle_running"] = False
        state["updated_at"] = now
        await self.ctx.storage.put("state", state)
        return state
