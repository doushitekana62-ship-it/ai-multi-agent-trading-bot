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
    "trade_history": [],
    "last_decision": None,
    "last_error": None,
    "paper_pair": "btc_idr",
    "updated_at": None,
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _copy_default_state():
    state = dict(DEFAULT_STATE)
    state["decision_counts"] = dict(DEFAULT_STATE["decision_counts"])
    state["positions"] = []
    state["trade_history"] = []
    return state


class PaperTradingState(DurableObject):
    """Single authoritative state for the dashboard paper-trading session."""

    def __init__(self, ctx, env):
        super().__init__(ctx, env)
        self.ctx = ctx
        self.env = env

    async def _get(self):
        state = await self.ctx.storage.get("state")
        if not isinstance(state, dict):
            state = _copy_default_state()
            await self.ctx.storage.put("state", state)
        state.setdefault("decision_counts", {"BUY": 0, "SELL": 0, "HOLD": 0})
        state.setdefault("positions", [])
        state.setdefault("trade_history", [])
        state.setdefault("last_error", None)
        state.setdefault("paper_pair", "btc_idr")
        return state

    async def get_state(self):
        return await self._get()

    async def enable_paper(self, pair="btc_idr"):
        """Enable paper trading; does not execute a cycle."""
        state = await self._get()
        now = _now()
        state["enabled"] = True
        state["mode"] = "paper"
        state["cycle_running"] = False
        state["started_at"] = state.get("started_at") or now
        state["last_error"] = None
        state["paper_pair"] = str(pair or "btc_idr").strip().lower() or "btc_idr"
        state["updated_at"] = now
        await self.ctx.storage.put("state", state)
        return state

    async def start(self, pair="btc_idr"):
        """Backward-compatible alias for older callers."""
        return await self.enable_paper(pair)

    async def stop(self):
        state = await self._get()
        state["enabled"] = False
        state["cycle_running"] = False
        state["last_error"] = None
        state["updated_at"] = _now()
        await self.ctx.storage.put("state", state)
        return state

    async def reset(self):
        state = _copy_default_state()
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
        state["last_error"] = None
        state["updated_at"] = _now()
        await self.ctx.storage.put("state", state)
        return True, state, None

    async def finish_cycle(self, error=None):
        state = await self._get()
        state["cycle_running"] = False
        state["last_error"] = str(error) if error else None
        state["updated_at"] = _now()
        await self.ctx.storage.put("state", state)
        return state

    async def record_cycle(self, decision=None, confidence=0.0, symbol="BTC/IDR", price=0.0, reasoning=""):
        """Record one completed cycle and simulate a paper-only position."""
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
        position_index = next((i for i, p in enumerate(positions) if p.get("symbol") == symbol), None)
        executed = False
        realized = 0.0
        trade = None

        if action == "BUY" and price > 0 and position_index is None and len(positions) < int(state.get("max_open_positions", 5)):
            allocation = min(float(state.get("balance", 0.0)) * 0.20, float(state.get("balance", 0.0)))
            if allocation > 0:
                quantity = allocation / price
                position = {
                    "symbol": symbol,
                    "side": "BUY",
                    "quantity": quantity,
                    "entry_price": price,
                    "price": price,
                    "pnl": 0.0,
                    "confidence": confidence,
                    "created_at": now,
                }
                positions.append(position)
                state["balance"] -= allocation
                executed = True
                trade = {
                    "action": "BUY",
                    "symbol": symbol,
                    "quantity": quantity,
                    "price": price,
                    "pnl": 0.0,
                    "created_at": now,
                }
        elif action == "SELL" and price > 0 and position_index is not None:
            position = positions[position_index]
            proceeds = float(position.get("quantity", 0.0)) * price
            realized = proceeds - (float(position.get("quantity", 0.0)) * float(position.get("entry_price", price)))
            state["balance"] += proceeds
            positions.pop(position_index)
            state["daily_pnl"] += realized
            state["total_pnl"] += realized
            executed = True
            trade = {
                "action": "SELL",
                "symbol": symbol,
                "quantity": float(position.get("quantity", 0.0)),
                "price": price,
                "pnl": realized,
                "created_at": now,
            }

        for position in positions:
            if position.get("symbol") == symbol and price > 0:
                position["price"] = price
                position["pnl"] = (price - float(position.get("entry_price", price))) * float(position.get("quantity", 0.0))

        if trade:
            history = list(state.get("trade_history") or [])
            state["trade_history"] = [*history, trade][-100:]

        state["positions"] = positions
        state["active_positions"] = len(positions)
        state["portfolio_value"] = float(state.get("balance", 0.0)) + sum(
            float(p.get("quantity", 0.0)) * float(p.get("price", p.get("entry_price", 0.0)))
            for p in positions
        )
        state["cycles_today"] = int(state.get("cycles_today", 0)) + 1
        state["last_cycle_at"] = now
        counts = state.setdefault("decision_counts", {"BUY": 0, "SELL": 0, "HOLD": 0})
        counts[action] = int(counts.get(action, 0)) + 1
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
        state["last_error"] = None
        state["updated_at"] = now
        await self.ctx.storage.put("state", state)
        return state

    async def record_cycle_payload(self, payload):
        """RPC-safe cycle recorder using one structured-cloneable argument."""
        payload = payload if isinstance(payload, dict) else {}
        return await self.record_cycle(
            payload.get("decision", "HOLD"),
            payload.get("confidence", 0.0),
            payload.get("symbol", "BTC/IDR"),
            payload.get("price", 0.0),
            payload.get("reasoning", ""),
        )
