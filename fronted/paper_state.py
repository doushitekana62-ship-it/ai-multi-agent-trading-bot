"""Persistent paper-trading state backed by a SQLite Durable Object."""
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
        return state

    async def get_state(self):
        return await self._get()

    async def start(self):
        state = await self._get()
        now = datetime.now(timezone.utc).isoformat()
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
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self.ctx.storage.put("state", state)
        return state

    async def reset(self):
        state = dict(DEFAULT_STATE)
        state["decision_counts"] = dict(DEFAULT_STATE["decision_counts"])
        state["positions"] = []
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self.ctx.storage.put("state", state)
        return state

    async def record_cycle(self, decision=None, confidence=0.0):
        """Record one completed paper cycle; execution is deliberately external."""
        state = await self._get()
        if not state.get("enabled"):
            return state

        now = datetime.now(timezone.utc).isoformat()
        action = str(decision or "HOLD").upper()
        if action not in {"BUY", "SELL", "HOLD"}:
            action = "HOLD"

        state["cycles_today"] = int(state.get("cycles_today", 0)) + 1
        state["last_cycle_at"] = now
        state["decision_counts"][action] = int(state["decision_counts"].get(action, 0)) + 1
        state["last_decision"] = {
            "action": action,
            "confidence": float(confidence or 0.0),
            "created_at": now,
        }
        state["updated_at"] = now
        await self.ctx.storage.put("state", state)
        return state
