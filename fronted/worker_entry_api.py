"""Compatibility routing layer for the Cloudflare Python Worker.

The dashboard uses /api/dashboard/paper/* while the Worker runtime exposes
its authoritative paper controls under /api/bot/*. Paper execution is manually
gated: the user explicitly turns the bot ON/OFF. While ON, Cloudflare's Cron
Trigger may execute one guarded paper cycle per minute; Cron can never enable
the bot by itself.
"""
from __future__ import annotations

from workers import Response

from worker_entry import (
    Default as BaseDefault,
    PaperTradingState,
    _paper_cycle,
    _request_pair,
    _state_response,
    _state_stub,
)


class Default(BaseDefault):
    async def _handle_state_routes(self, request, path):
        aliases = {
            "/api/dashboard/paper/start": "/api/bot/start",
            "/api/dashboard/paper/stop": "/api/bot/stop",
            "/api/dashboard/paper/status": "/api/bot/status",
            "/api/dashboard/paper/cycle": "/api/bot/cycle",
            "/api/dashboard/paper/reset": "/api/bot/reset",
        }
        target = aliases.get(path, path)

        if target == "/api/bot/start" and request.method == "POST":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            try:
                stub = await _state_stub(self.env)
                pair = _request_pair(request)
                state = await stub.enable_paper(pair)
                payload = _state_response(state)
                payload.update({
                    "ok": True,
                    "manual_control": True,
                    "automation_enabled": True,
                    "cycle_schedule": "1m_while_enabled",
                    "message": "Paper trading enabled manually. Cycles run only while BOT ON.",
                })
                return Response.json(payload, status=200)
            except Exception as exc:
                return Response.json(
                    {
                        "ok": False,
                        "detail": "Paper trading could not be enabled",
                        "reason": "paper_state_rpc_error",
                        "error": str(exc),
                    },
                    status=503,
                )

        if target == "/api/bot/stop" and request.method == "POST":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            try:
                stub = await _state_stub(self.env)
                state = await stub.stop()
                payload = _state_response(state)
                payload.update({
                    "ok": True,
                    "manual_control": True,
                    "automation_enabled": True,
                    "cycle_schedule": "1m_while_enabled",
                    "message": "Paper trading disabled manually. No further cycles will run.",
                })
                return Response.json(payload, status=200)
            except Exception as exc:
                return Response.json(
                    {
                        "ok": False,
                        "detail": "Paper trading could not be stopped",
                        "reason": "paper_state_rpc_error",
                        "error": str(exc),
                    },
                    status=503,
                )

        if target == "/api/bot/cycle" and request.method == "POST":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            cycle = await _paper_cycle(self.env, _request_pair(request))
            return Response.json(cycle, status=200 if cycle.get("ok") else 409)

        # Make the dashboard health indicator represent the persistent bot
        # gate, not the instantaneous sub-second cycle lock.
        if target == "/api/dashboard/status" and request.method == "GET":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            stub = await _state_stub(self.env)
            state = await stub.get_state()
            result = _state_response(state)
            result["daily_pnl"] = float(state.get("daily_pnl", 0.0))
            result["daily_trades"] = int(state.get("daily_trades", 0))
            result["total_trades"] = int(state.get("total_trades", 0))
            result["active_positions"] = int(state.get("active_positions", 0))
            enabled = bool(state.get("enabled"))
            cycle_running = bool(state.get("cycle_running"))
            result["manual_control"] = True
            result["automation_enabled"] = True
            result["cycle_schedule"] = "1m_while_enabled"
            result["system_health"] = {
                "database": {"connected": True, "diagnostic": "durable_object_state"},
                "market_data": {"fresh": True, "stale": False, "age_seconds": 0},
                "mode": "paper",
                "engine": {
                    "running": enabled,
                    "enabled": enabled,
                    "cycle_running": cycle_running,
                    "state": "RUNNING" if enabled else "OFF",
                },
            }
            return Response.json(result)

        return await super()._handle_state_routes(request, target)

    async def scheduled(self, controller, env, ctx):
        """Run exactly one guarded paper cycle only after manual START.

        The Cron Trigger is intentionally a scheduler, not an activation
        mechanism. BOT OFF means no cycle. STOP persists enabled=False in the
        Durable Object and therefore blocks all subsequent scheduled cycles.
        """
        stub = await _state_stub(env)
        state = await stub.get_state()
        if not state.get("enabled"):
            return
        pair = state.get("paper_pair") or "btc_idr"
        try:
            await _paper_cycle(env, pair)
        except Exception:
            # _paper_cycle already releases its cycle gate on handled failures.
            # Never let a scheduled exception become an unhandled Worker error.
            return


__all__ = ["Default", "PaperTradingState"]
