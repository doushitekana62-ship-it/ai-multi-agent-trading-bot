"""Persistent paper-trading state backed by a SQLite Durable Object."""
from __future__ import annotations

from datetime import datetime, timezone
from workers import DurableObject


DEFAULT_STATE = {
    "enabled": False,
    "mode": "paper",
    "cycle_running": False,
    "cycle_started_at": None,
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


CYCLE_LOCK_TIMEOUT_SECONDS = 10 * 60


def _now():
    return datetime.now(timezone.utc)


def _iso_now():
    return _now().isoformat()


def _lock_is_stale(started_at):
    if not started_at:
        return True
    try:
        raw = str(started_at).replace("Z", "+00:00")
        started = datetime.fromisoformat(raw)
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        return (_now() - started).total_seconds() >= CYCLE_LOCK_TIMEOUT_SECONDS
    except (TypeError, ValueError, OverflowError):
        return True


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
        else:
            # Backward-compatible migration for state created before the lock.
            state.setdefault("cycle_running", False)
            state.setdefault("cycle_started_at", None)
        return state

    async def get_state(self):
        return await self._get()

    async def start(self):
        state = await self._get()
        now = _iso_now()
        state["enabled"] = True
        state["mode"] = "paper"
        state["cycle_running"] = False
        state["cycle_started_at"] = None
        state["started_at"] = state["started_at"] or now
        state["updated_at"] = now
        await self.ctx.storage.put("state", state)
        return state

    async def stop(self):
        state = await self._get()
        state["enabled"] = False
        state["cycle_running"] = False
        state["cycle_started_at"] = None
        state["updated_at"] = _iso_now()
        await self.ctx.storage.put("state", state)
        return state

    async def reset(self):
        state = dict(DEFAULT_STATE)
        state["decision_counts"] = dict(DEFAULT_STATE["decision_counts"])
        state["positions"] = []
        state["updated_at"] = _iso_now()
        await self.ctx.storage.put("state", state)
        return state

    async def begin_cycle(self):
        """Atomically arm exactly one explicit AI cycle.

        Dashboard polling never calls this method. A cycle can begin only after
        the persistent paper bot has been explicitly enabled.
        """
        state = await self._get()
        if not state.get("enabled"):
            return {"started": False, "reason": "bot_disabled", "state": state}

        if state.get("cycle_running"):
            if not _lock_is_stale(state.get("cycle_started_at")):
                return {"started": False, "reason": "cycle_already_running", "state": state}
            # A worker invocation can disappear before releasing the lock.
            # Recover only after the bounded timeout, never immediately.
            state["cycle_running"] = False
            state["cycle_started_at"] = None

        now = _iso_now()
        state["cycle_running"] = True
        state["cycle_started_at"] = now
        state["updated_at"] = now
        await self.ctx.storage.put("state", state)
        return {"started": True, "reason": "cycle_lock_acquired", "state": state}

    async def finish_cycle(self, decision=None, confidence=0.0):
        """Release the cycle lock and record the completed decision."""
        state = await self._get()
        if not state.get("cycle_running"):
            return {"finished": False, "reason": "no_cycle_running", "state": state}

        now = _iso_now()
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
        state["cycle_running"] = False
        state["cycle_started_at"] = None
        state["updated_at"] = now
        await self.ctx.storage.put("state", state)
        return {"finished": True, "reason": "cycle_completed", "state": state}

    async def abort_cycle(self, reason="cycle_aborted"):
        """Release an explicit cycle lock without counting a decision."""
        state = await self._get()
        state["cycle_running"] = False
        state["cycle_started_at"] = None
        state["updated_at"] = _iso_now()
        await self.ctx.storage.put("state", state)
        return {"aborted": True, "reason": str(reason), "state": state}

    async def record_cycle(self, decision=None, confidence=0.0):
        """Backward-compatible completed-cycle recorder."""
        state = await self._get()
        if not state.get("enabled"):
            return state

        if not state.get("cycle_running"):
            # Legacy callers did not acquire a lock. Keep the method usable,
            # but do not expose it as the dashboard's cycle trigger.
            now = _iso_now()
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

        result = await self.finish_cycle(decision=decision, confidence=confidence)
        return result["state"]
