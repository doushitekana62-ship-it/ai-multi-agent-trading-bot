"""Persistent paper-trading state backed by a Durable Object."""
from __future__ import annotations

from datetime import datetime, timezone

from workers import DurableObject

from paper_cycle import run_paper_cycle

CYCLE_INTERVAL_MS = 60_000

DEFAULT_STATE = {
    "enabled": False, "mode": "paper", "cycle_running": False, "started_at": None,
    "last_cycle_at": None, "last_cycle_started_at": None, "last_cycle_finished_at": None,
    "last_cycle_status": "idle", "cycles_today": 0, "cycle_failures": 0,
    "consecutive_cycle_failures": 0, "balance": 10_000_000.0, "initial_balance": 10_000_000.0,
    "portfolio_value": 10_000_000.0, "daily_pnl": 0.0, "total_pnl": 0.0,
    "daily_trades": 0, "total_trades": 0, "active_positions": 0, "max_open_positions": 5,
    "decision_counts": {"BUY": 0, "SELL": 0, "HOLD": 0}, "positions": [], "trade_history": [],
    "last_decision": None, "last_error": None, "paper_pair": "btc_idr", "scheduler_active": False,
    "scheduler_source": "durable_object_alarm", "last_scheduler_at": None,
    "scheduler_invocations": 0, "next_cycle_at": None, "updated_at": None,
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _iso_from_ms(timestamp_ms):
    return datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc).isoformat()


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
        state.setdefault("last_cycle_started_at", None)
        state.setdefault("last_cycle_finished_at", None)
        state.setdefault("last_cycle_status", "idle")
        state.setdefault("cycle_failures", 0)
        state.setdefault("consecutive_cycle_failures", 0)
        state.setdefault("scheduler_active", bool(state.get("enabled")))
        state.setdefault("scheduler_source", "durable_object_alarm")
        state.setdefault("last_scheduler_at", None)
        state.setdefault("scheduler_invocations", 0)
        state.setdefault("next_cycle_at", None)
        return state

    async def get_state(self):
        return await self._get()

    async def get_paper_market_history(self):
        value = await self.ctx.storage.get("paper_market_history")
        return value if isinstance(value, list) else []

    async def set_paper_market_history(self, history):
        value = history if isinstance(history, list) else []
        await self.ctx.storage.put("paper_market_history", value[-120:])
        return value[-120:]

    async def ensure_scheduler(self):
        state = await self._get()
        if not state.get("enabled") or state.get("cycle_running"):
            return state
        current_alarm = await self.ctx.storage.getAlarm()
        if current_alarm is None:
            next_ms = int(datetime.now(timezone.utc).timestamp() * 1000) + CYCLE_INTERVAL_MS
            self.ctx.storage.setAlarm(next_ms)
            state["scheduler_active"] = True
            state["next_cycle_at"] = _iso_from_ms(next_ms)
            state["updated_at"] = _now()
            await self.ctx.storage.put("state", state)
        return state

    async def enable_paper(self, pair="btc_idr"):
        state = await self._get()
        now = _now()
        state["enabled"] = True
        state["mode"] = "paper"
        state["cycle_running"] = False
        state["started_at"] = now
        state["last_cycle_status"] = "waiting"
        state["cycle_failures"] = 0
        state["consecutive_cycle_failures"] = 0
        state["last_error"] = None
        state["paper_pair"] = str(pair or "btc_idr").strip().lower() or "btc_idr"
        state["scheduler_active"] = True
        state["scheduler_source"] = "durable_object_alarm"
        state["updated_at"] = now
        current_alarm = await self.ctx.storage.getAlarm()
        if current_alarm is None:
            next_ms = int(datetime.now(timezone.utc).timestamp() * 1000) + CYCLE_INTERVAL_MS
            self.ctx.storage.setAlarm(next_ms)
            state["next_cycle_at"] = _iso_from_ms(next_ms)
        else:
            state["next_cycle_at"] = _iso_from_ms(current_alarm)
        await self.ctx.storage.put("state", state)
        return state

    async def start(self, pair="btc_idr"):
        return await self.enable_paper(pair)

    async def stop(self):
        state = await self._get()
        state["enabled"] = False
        state["cycle_running"] = False
        state["scheduler_active"] = False
        state["next_cycle_at"] = None
        state["last_error"] = None
        state["last_cycle_status"] = "stopped"
        state["updated_at"] = _now()
        self.ctx.storage.deleteAlarm()
        await self.ctx.storage.put("state", state)
        return state

    async def reset(self):
        self.ctx.storage.deleteAlarm()
        await self.ctx.storage.delete("paper_market_history")
        state = _copy_default_state()
        state["updated_at"] = _now()
        await self.ctx.storage.put("state", state)
        return state

    async def begin_cycle(self):
        """Begin a cycle using an RPC-safe dictionary result.

        Durable Object RPC serializes structured-clone-compatible values. Returning
        a tuple here made the remote call fragile in the Python Worker runtime.
        Keep the RPC contract as a plain dictionary so the Worker can reliably
        receive the cycle lock result.
        """
        state = await self._get()
        if not state.get("enabled"):
            return {"ok": False, "state": state, "reason": "paper_trading_disabled"}
        if state.get("cycle_running"):
            return {"ok": False, "state": state, "reason": "cycle_already_running"}
        now = _now()
        state["cycle_running"] = True
        state["last_error"] = None
        state["last_cycle_started_at"] = now
        state["last_cycle_status"] = "running"
        state["scheduler_active"] = True
        state["updated_at"] = now
        await self.ctx.storage.put("state", state)
        return {"ok": True, "state": state, "reason": None}

    async def finish_cycle(self, error=None):
        state = await self._get()
        now = _now()
        state["cycle_running"] = False
        state["last_cycle_finished_at"] = now
        state["last_cycle_status"] = "failed" if error else "completed"
        state["last_error"] = str(error) if error else None
        if error:
            state["cycle_failures"] = int(state.get("cycle_failures", 0)) + 1
            state["consecutive_cycle_failures"] = int(state.get("consecutive_cycle_failures", 0)) + 1
        else:
            state["consecutive_cycle_failures"] = 0
        state["updated_at"] = now
        await self.ctx.storage.put("state", state)
        return state

    async def record_orchestrator(self, metadata):
        safe = metadata if isinstance(metadata, dict) else {}
        await self.ctx.storage.put("last_orchestrator", safe)
        return safe

    async def record_cycle(self, decision=None, confidence=0.0, symbol="BTC/IDR", price=0.0, reasoning=""):
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
                positions.append({"symbol": symbol, "side": "BUY", "quantity": quantity, "entry_price": price, "price": price, "pnl": 0.0, "confidence": confidence, "created_at": now})
                state["balance"] -= allocation
                executed = True
                trade = {"action": "BUY", "symbol": symbol, "quantity": quantity, "price": price, "pnl": 0.0, "created_at": now}
        elif action == "SELL" and price > 0 and position_index is not None:
            position = positions[position_index]
            proceeds = float(position.get("quantity", 0.0)) * price
            realized = proceeds - float(position.get("quantity", 0.0)) * float(position.get("entry_price", price))
            state["balance"] += proceeds
            positions.pop(position_index)
            state["daily_pnl"] += realized
            state["total_pnl"] += realized
            executed = True
            trade = {"action": "SELL", "symbol": symbol, "quantity": float(position.get("quantity", 0.0)), "price": price, "pnl": realized, "created_at": now}

        for position in positions:
            if position.get("symbol") == symbol and price > 0:
                position["price"] = price
                position["pnl"] = (price - float(position.get("entry_price", price))) * float(position.get("quantity", 0.0))
        if trade:
            state["trade_history"] = [*(list(state.get("trade_history") or [])), trade][-100:]
        state["positions"] = positions
        state["active_positions"] = len(positions)
        state["portfolio_value"] = float(state.get("balance", 0.0)) + sum(float(p.get("quantity", 0.0)) * float(p.get("price", p.get("entry_price", 0.0))) for p in positions)
        state["cycles_today"] = int(state.get("cycles_today", 0)) + 1
        state["last_cycle_at"] = now
        state["last_cycle_finished_at"] = now
        state["last_cycle_status"] = "completed"
        counts = state.setdefault("decision_counts", {"BUY": 0, "SELL": 0, "HOLD": 0})
        counts[action] = int(counts.get(action, 0)) + 1
        if executed:
            state["daily_trades"] = int(state.get("daily_trades", 0)) + 1
            state["total_trades"] = int(state.get("total_trades", 0)) + 1
        state["last_decision"] = {"action": action, "confidence": confidence, "symbol": symbol, "price": price, "executed": executed, "realized_pnl": realized, "reasoning": reasoning, "created_at": now}
        state["cycle_running"] = False
        state["last_error"] = None
        state["consecutive_cycle_failures"] = 0
        state["updated_at"] = now
        await self.ctx.storage.put("state", state)
        return state

    async def record_cycle_payload(self, payload):
        payload = payload if isinstance(payload, dict) else {}
        return await self.record_cycle(payload.get("decision", "HOLD"), payload.get("confidence", 0.0), payload.get("symbol", "BTC/IDR"), payload.get("price", 0.0), payload.get("reasoning", ""))

    async def alarm(self, alarm_info=None):
        state = await self._get()
        now = _now()
        state["last_scheduler_at"] = now
        state["scheduler_invocations"] = int(state.get("scheduler_invocations", 0)) + 1
        state["scheduler_active"] = bool(state.get("enabled"))
        state["next_cycle_at"] = None
        await self.ctx.storage.put("state", state)
        if not state.get("enabled"):
            self.ctx.storage.deleteAlarm()
            state["scheduler_active"] = False
            state["updated_at"] = _now()
            await self.ctx.storage.put("state", state)
            return
        pair = state.get("paper_pair") or "btc_idr"
        try:
            await run_paper_cycle(self.env, self, pair)
        except Exception as exc:
            await self.finish_cycle(f"alarm_cycle_error: {exc}")
        state = await self._get()
        if not state.get("enabled"):
            self.ctx.storage.deleteAlarm()
            state["scheduler_active"] = False
            state["next_cycle_at"] = None
        else:
            next_ms = int(datetime.now(timezone.utc).timestamp() * 1000) + CYCLE_INTERVAL_MS
            self.ctx.storage.setAlarm(next_ms)
            state["scheduler_active"] = True
            state["next_cycle_at"] = _iso_from_ms(next_ms)
        state["updated_at"] = _now()
        await self.ctx.storage.put("state", state)
