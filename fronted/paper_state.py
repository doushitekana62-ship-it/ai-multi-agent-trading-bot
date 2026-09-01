"""Persistent paper-trading state backed by a Durable Object."""
from __future__ import annotations

from datetime import datetime, timezone

from workers import DurableObject

from paper_cycle import run_market_observation, run_paper_cycle

CYCLE_INTERVAL_MS = 5_000
DECISION_INTERVAL_MS = 60_000
MAX_POSITIONS = 3
DEFAULT_POSITION_ALLOCATION = 0.10
STATE_VERSION = 3
MARKET_HISTORY_LIMIT = 1440

DEFAULT_STATE = {
    "state_version": STATE_VERSION,
    "enabled": False,
    "mode": "paper",
    "cycle_running": False,
    "started_at": None,
    "last_cycle_at": None,
    "last_cycle_started_at": None,
    "last_cycle_finished_at": None,
    "last_cycle_status": "idle",
    "cycles_today": 0,
    "cycle_failures": 0,
    "consecutive_cycle_failures": 0,
    "balance": 10_000_000.0,
    "initial_balance": 10_000_000.0,
    "portfolio_value": 10_000_000.0,
    "daily_pnl": 0.0,
    "total_pnl": 0.0,
    "daily_trades": 0,
    "total_trades": 0,
    "active_positions": 0,
    "max_open_positions": MAX_POSITIONS,
    "position_allocation": DEFAULT_POSITION_ALLOCATION,
    "decision_counts": {"BUY": 0, "SELL": 0, "HOLD": 0},
    "positions": [],
    "trade_history": [],
    "last_decision": None,
    "last_error": None,
    "paper_pair": "btc_idr",
    "scheduler_active": False,
    "scheduler_source": "durable_object_alarm",
    "last_scheduler_at": None,
    "scheduler_invocations": 0,
    "next_cycle_at": None,
    "updated_at": None,
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _iso_from_ms(ms):
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()


def _safe_limit(value, default=MAX_POSITIONS):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = default
    return max(1, min(MAX_POSITIONS, value))


def _copy_default_state():
    state = dict(DEFAULT_STATE)
    state["decision_counts"] = dict(DEFAULT_STATE["decision_counts"])
    state["positions"] = []
    state["trade_history"] = []
    return state


class PaperTradingState(DurableObject):
    """Single authoritative paper account, position limit and scheduler state."""

    def __init__(self, ctx, env):
        super().__init__(ctx, env)
        self.ctx = ctx
        self.env = env

    async def _get(self):
        state = await self.ctx.storage.get("state")
        if not isinstance(state, dict):
            state = _copy_default_state()
        state.setdefault("state_version", STATE_VERSION)
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
        state["max_open_positions"] = _safe_limit(state.get("max_open_positions"))
        try:
            allocation = float(state.get("position_allocation", DEFAULT_POSITION_ALLOCATION))
        except (TypeError, ValueError):
            allocation = DEFAULT_POSITION_ALLOCATION
        state["position_allocation"] = max(0.01, min(DEFAULT_POSITION_ALLOCATION, allocation))
        state["active_positions"] = len(state.get("positions") or [])
        state["state_version"] = STATE_VERSION
        await self.ctx.storage.put("state", state)
        return state

    async def get_state(self):
        return await self._get()

    async def get_settings(self):
        state = await self._get()
        return {
            "max_open_positions": state["max_open_positions"],
            "position_allocation": state["position_allocation"],
            "active_positions": state["active_positions"],
            "hard_max_positions": MAX_POSITIONS,
            "updated_at": state.get("updated_at"),
        }

    async def get_paper_market_history(self):
        value = await self.ctx.storage.get("paper_market_history")
        return value if isinstance(value, list) else []

    async def set_paper_market_history(self, history):
        value = history if isinstance(history, list) else []
        value = value[-MARKET_HISTORY_LIMIT:]
        await self.ctx.storage.put("paper_market_history", value)
        return value

    async def _arm(self):
        alarm = await self.ctx.storage.getAlarm()
        if alarm is None:
            ms = int(datetime.now(timezone.utc).timestamp() * 1000) + CYCLE_INTERVAL_MS
            self.ctx.storage.setAlarm(ms)
            return _iso_from_ms(ms)
        return _iso_from_ms(alarm)

    async def ensure_scheduler(self):
        state = await self._get()
        if state.get("enabled") and not state.get("cycle_running"):
            state["scheduler_active"] = True
            state["next_cycle_at"] = await self._arm()
            state["updated_at"] = _now()
            await self.ctx.storage.put("state", state)
        return state

    async def enable_paper(self, pair="btc_idr"):
        state = await self._get()
        now = _now()
        state.update({
            "enabled": True,
            "mode": "paper",
            "cycle_running": False,
            "started_at": now,
            "last_cycle_status": "waiting",
            "cycle_failures": 0,
            "consecutive_cycle_failures": 0,
            "last_error": None,
            "paper_pair": str(pair or "btc_idr").strip().lower() or "btc_idr",
            "scheduler_active": True,
            "scheduler_source": "durable_object_alarm",
            "updated_at": now,
        })
        state["next_cycle_at"] = await self._arm()
        await self.ctx.storage.put("state", state)
        return state

    async def start(self, pair="btc_idr"):
        return await self.enable_paper(pair)

    async def set_position_limit(self, value):
        state = await self._get()
        state["max_open_positions"] = _safe_limit(value)
        state["active_positions"] = len(state.get("positions") or [])
        state["updated_at"] = _now()
        await self.ctx.storage.put("state", state)
        return state

    async def stop(self):
        state = await self._get()
        state.update({
            "enabled": False,
            "cycle_running": False,
            "scheduler_active": False,
            "next_cycle_at": None,
            "last_error": None,
            "last_cycle_status": "stopped",
            "updated_at": _now(),
        })
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
        state = await self._get()
        if not state.get("enabled"):
            return {"ok": False, "state": state, "reason": "paper_trading_disabled"}
        if state.get("cycle_running"):
            return {"ok": False, "state": state, "reason": "cycle_already_running"}
        now = _now()
        state.update({
            "cycle_running": True,
            "last_error": None,
            "last_cycle_started_at": now,
            "last_cycle_status": "running",
            "scheduler_active": True,
            "updated_at": now,
        })
        await self.ctx.storage.put("state", state)
        return {"ok": True, "state": state, "reason": None}

    async def finish_cycle(self, error=None):
        state = await self._get()
        now = _now()
        state.update({
            "cycle_running": False,
            "last_cycle_finished_at": now,
            "last_cycle_status": "failed" if error else "completed",
            "last_error": str(error) if error else None,
            "updated_at": now,
        })
        if error:
            state["cycle_failures"] = int(state.get("cycle_failures", 0)) + 1
            state["consecutive_cycle_failures"] = int(state.get("consecutive_cycle_failures", 0)) + 1
        else:
            state["consecutive_cycle_failures"] = 0
        await self.ctx.storage.put("state", state)
        return state

    async def record_orchestrator(self, metadata):
        safe = metadata if isinstance(metadata, dict) else {}
        await self.ctx.storage.put("last_orchestrator", safe)
        return safe

    async def record_cycle(self, decision=None, confidence=0.0, symbol="BTC/IDR", price=0.0, reasoning="", analysis=None):
        state = await self._get()
        if not state.get("enabled"):
            return state
        now = _now()
        action = str(decision or "HOLD").upper()
        action = action if action in {"BUY", "SELL", "HOLD"} else "HOLD"
        try:
            price = float(price or 0)
        except (TypeError, ValueError):
            price = 0.0
        try:
            confidence = max(0.0, min(1.0, float(confidence or 0)))
        except (TypeError, ValueError):
            confidence = 0.0

        positions = list(state.get("positions") or [])
        idx = next((i for i, p in enumerate(positions) if p.get("symbol") == symbol), None)
        executed = False
        realized = 0.0
        trade = None

        if action == "BUY" and price > 0 and idx is None and len(positions) < state["max_open_positions"]:
            try:
                equity = float(state.get("balance", 0)) + sum(
                    float(p.get("quantity", 0)) * float(p.get("price", p.get("entry_price", 0)))
                    for p in positions
                )
                allocation = min(equity * state["position_allocation"], float(state.get("balance", 0)))
            except (TypeError, ValueError):
                allocation = 0.0
                equity = 0.0
            if allocation > 0:
                qty = allocation / price
                positions.append({
                    "symbol": symbol,
                    "side": "BUY",
                    "quantity": qty,
                    "entry_price": price,
                    "price": price,
                    "capital": allocation,
                    "position_size": allocation / equity if equity else 0,
                    "pnl": 0.0,
                    "unrealized_pnl": 0.0,
                    "confidence": confidence,
                    "created_at": now,
                })
                state["balance"] = float(state.get("balance", 0)) - allocation
                executed = True
                trade = {"action": "BUY", "symbol": symbol, "quantity": qty, "price": price, "pnl": 0.0, "confidence": confidence, "created_at": now}
        elif action == "SELL" and price > 0 and idx is not None:
            position = positions[idx]
            qty = float(position.get("quantity", 0))
            entry = float(position.get("entry_price", price))
            realized = (price - entry) * qty
            state["balance"] = float(state.get("balance", 0)) + qty * price
            positions.pop(idx)
            state["daily_pnl"] = float(state.get("daily_pnl", 0)) + realized
            state["total_pnl"] = float(state.get("total_pnl", 0)) + realized
            executed = True
            trade = {"action": "SELL", "symbol": symbol, "quantity": qty, "price": price, "pnl": realized, "confidence": confidence, "created_at": now}

        for p in positions:
            if p.get("symbol") == symbol and price > 0:
                p["price"] = price
                p["unrealized_pnl"] = (price - float(p.get("entry_price", price))) * float(p.get("quantity", 0))
                p["pnl"] = p["unrealized_pnl"]

        if trade:
            state["trade_history"] = [*list(state.get("trade_history") or []), trade][-100:]
        state["positions"] = positions
        state["active_positions"] = len(positions)
        state["portfolio_value"] = float(state.get("balance", 0)) + sum(
            float(p.get("quantity", 0)) * float(p.get("price", p.get("entry_price", 0))) for p in positions
        )
        state["cycles_today"] = int(state.get("cycles_today", 0)) + 1
        state["last_cycle_at"] = now
        state["last_cycle_finished_at"] = now
        state["last_cycle_status"] = "completed"
        counts = state.setdefault("decision_counts", {"BUY": 0, "SELL": 0, "HOLD": 0})
        counts[action] = int(counts.get(action, 0)) + 1
        if executed:
            state["daily_trades"] = int(state.get("daily_trades", 0)) + 1
            state["total_trades"] = int(state.get("total_trades", 0)) + 1
        last = {
            "action": action,
            "confidence": confidence,
            "symbol": symbol,
            "price": price,
            "executed": executed,
            "realized_pnl": realized,
            "reasoning": reasoning,
            "created_at": now,
        }
        if isinstance(analysis, dict):
            for key in (
                "votes", "market_scores", "confidence_components", "consensus_action", "consensus_score",
                "position_size", "stop_loss", "take_profit", "source", "warning", "raw_action", "summary",
                "execution_gate", "cycle_id", "cycle_number", "market_timestamp", "market_source",
                "move_1m_pct", "move_5m_pct", "move_15m_pct", "move_30m_pct", "pulse_status",
                "current_pulse_status", "pulse_net_move_30m_pct", "pulse_segments", "hold_analysis",
                "candidate_action", "cycle_status",
            ):
                if key in analysis:
                    last[key] = analysis[key]
        if trade:
            last["trade"] = trade
        state["last_decision"] = last
        state["cycle_running"] = False
        state["last_error"] = None
        state["consecutive_cycle_failures"] = 0
        state["updated_at"] = now
        await self.ctx.storage.put("state", state)
        return state

    async def apply_cycle(self, action="HOLD", price=0.0, confidence=0.0, cycle_id=None, metadata=None):
        """Backward-compatible RPC retained for older deployed paper-cycle callers."""
        analysis = dict(metadata) if isinstance(metadata, dict) else {}
        if cycle_id is not None:
            analysis.setdefault("cycle_id", str(cycle_id))
        return await self.record_cycle(
            decision=action,
            confidence=confidence,
            symbol=str(analysis.get("symbol") or "BTC/IDR"),
            price=price,
            reasoning=str(analysis.get("summary") or analysis.get("reasoning") or ""),
            analysis=analysis,
        )

    async def record_cycle_payload(self, payload):
        payload = payload if isinstance(payload, dict) else {}
        analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else None
        return await self.record_cycle(
            payload.get("decision", "HOLD"),
            payload.get("confidence", 0),
            payload.get("symbol", "BTC/IDR"),
            payload.get("price", 0),
            payload.get("reasoning", ""),
            analysis,
        )

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
            return

        try:
            last_cycle_at = state.get("last_cycle_at")
            decision_due = True
            if last_cycle_at:
                try:
                    last_cycle_ms = datetime.fromisoformat(str(last_cycle_at)).timestamp() * 1000.0
                    now_ms = datetime.now(timezone.utc).timestamp() * 1000.0
                    decision_due = (now_ms - last_cycle_ms) >= DECISION_INTERVAL_MS
                except (TypeError, ValueError):
                    decision_due = True
            if decision_due:
                await run_paper_cycle(self.env, self, state.get("paper_pair") or "btc_idr")
            else:
                await run_market_observation(self.env, self, state.get("paper_pair") or "btc_idr", state.get("started_at"))
        except Exception as exc:
            # Observation failures must not be misclassified as decision failures.
            state = await self._get()
            state["last_error"] = f"market_observation_error: {type(exc).__name__}: {exc}"
            state["updated_at"] = _now()
            await self.ctx.storage.put("state", state)

        state = await self._get()
        if not state.get("enabled"):
            self.ctx.storage.deleteAlarm()
            state["scheduler_active"] = False
            state["next_cycle_at"] = None
        else:
            state["next_cycle_at"] = await self._arm()
            state["scheduler_active"] = True
        state["updated_at"] = _now()
        await self.ctx.storage.put("state", state)
