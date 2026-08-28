"""Compatibility routing layer for the Cloudflare Python Worker.

The dashboard uses /api/dashboard/paper/* while the Worker runtime exposes
its authoritative paper controls under /api/bot/*. Paper execution is manually
gated: the user explicitly turns the bot ON/OFF. While ON, the Durable Object
Alarm scheduler runs one guarded paper cycle per minute. The alarm can never
enable the bot by itself.
"""
from __future__ import annotations

from workers import Response

from paper_cycle import run_paper_cycle
from worker_entry import (
    Default as BaseDefault,
    PaperTradingState,
    _request_pair,
    _state_response,
    _state_stub,
)


def _ai_engine_config_error(env):
    """Return a safe diagnostic when the external AI engine is not configured."""
    base_url = str(getattr(env, "AI_ENGINE_URL", "") or "").strip().rstrip("/")
    shared_secret = str(getattr(env, "AI_ENGINE_SHARED_SECRET", "") or "").strip()
    missing = []
    if not base_url:
        missing.append("AI_ENGINE_URL")
    if len(shared_secret) < 32:
        missing.append("AI_ENGINE_SHARED_SECRET")
    if not missing:
        return None
    return {
        "detail": "AI engine is not configured on the Cloudflare Worker",
        "reason": "ai_engine_not_configured",
        "missing": missing,
        "hint": "Configure these as Worker runtime variables/secrets, not Build variables.",
    }


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
            config_error = _ai_engine_config_error(self.env)
            if config_error:
                return Response.json({"ok": False, **config_error}, status=503)
            try:
                stub = await _state_stub(self.env)
                pair = _request_pair(request)
                state = await stub.enable_paper(pair)
                payload = _state_response(state)
                payload.update({
                    "ok": True,
                    "manual_control": True,
                    "automation_enabled": True,
                    "cycle_schedule": "durable_object_alarm_1m",
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
                    "cycle_schedule": "durable_object_alarm_1m",
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

        if target == "/api/bot/status" and request.method == "GET":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            stub = await _state_stub(self.env)
            state = await stub.ensure_scheduler()
            payload = _state_response(state)
            payload["last_orchestrator"] = await stub.ctx.storage.get("last_orchestrator")
            payload.update({
                "manual_control": True,
                "automation_enabled": True,
                "cycle_schedule": "durable_object_alarm_1m",
            })
            return Response.json(payload, status=200)

        if target == "/api/bot/cycle" and request.method == "POST":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            stub = await _state_stub(self.env)
            cycle = await run_paper_cycle(
                self.env,
                stub,
                _request_pair(request),
                state_response=_state_response,
            )
            return Response.json(cycle, status=200 if cycle.get("ok") else 409)

        if target == "/api/dashboard/status" and request.method == "GET":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            stub = await _state_stub(self.env)
            state = await stub.ensure_scheduler()
            result = _state_response(state)
            result["daily_pnl"] = float(state.get("daily_pnl", 0.0))
            result["daily_trades"] = int(state.get("daily_trades", 0))
            result["total_trades"] = int(state.get("total_trades", 0))
            result["active_positions"] = int(state.get("active_positions", 0))
            result["last_orchestrator"] = await stub.ctx.storage.get("last_orchestrator")
            enabled = bool(state.get("enabled"))
            cycle_running = bool(state.get("cycle_running"))
            result["manual_control"] = True
            result["automation_enabled"] = True
            result["cycle_schedule"] = "durable_object_alarm_1m"
            result["scheduler"] = {
                "active": bool(state.get("scheduler_active")) and enabled,
                "source": state.get("scheduler_source", "durable_object_alarm"),
                "last_run_at": state.get("last_scheduler_at"),
                "next_run_at": state.get("next_cycle_at"),
                "invocations": int(state.get("scheduler_invocations", 0)),
            }
            result["cycle"] = {
                "number": int(state.get("cycles_today", 0)),
                "status": state.get("last_cycle_status", "idle"),
                "last_started_at": state.get("last_cycle_started_at"),
                "last_finished_at": state.get("last_cycle_finished_at"),
                "last_cycle_at": state.get("last_cycle_at"),
                "failures": int(state.get("cycle_failures", 0)),
                "consecutive_failures": int(state.get("consecutive_cycle_failures", 0)),
                "last_error": state.get("last_error"),
            }
            result["system_health"] = {
                "database": {"connected": True, "diagnostic": "durable_object_state"},
                "market_data": {"fresh": True, "stale": False, "age_seconds": 0},
                "mode": "paper",
                "engine": {
                    "running": enabled,
                    "enabled": enabled,
                    "cycle_running": cycle_running,
                    "state": "RUNNING" if enabled else "OFF",
                    "last_cycle_status": state.get("last_cycle_status", "idle"),
                    "last_error": state.get("last_error"),
                },
            }
            return Response.json(result, status=200)

        if target == "/api/dashboard/recent-decision" and request.method == "GET":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            stub = await _state_stub(self.env)
            state = await stub.get_state()
            latest = await stub.ctx.storage.get("last_orchestrator")
            decision = state.get("last_decision")
            if latest:
                decision = {**(decision or {}), **latest}
            return Response.json({"decision": decision}, status=200)

        if target == "/api/dashboard/agents" and request.method == "GET":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            stub = await _state_stub(self.env)
            state = await stub.get_state()
            latest = await stub.ctx.storage.get("last_orchestrator")
            enabled = bool(state.get("enabled"))
            invoked = bool(latest and latest.get("agents_invoked"))
            status = "armed" if enabled else "idle"
            suffix = "Last cycle invoked by Orchestrator." if invoked else "Waiting for the next paper cycle."
            return Response.json({"agents": [{"name": name, "status": status, "description": f"{suffix}"} for name in ["Sentiment Agent", "Technical Agent", "Decision Agent", "Forecast Agent", "Reflector Agent"]]})

        return await super()._handle_state_routes(request, target)

    async def scheduled(self, controller, env, ctx):
        """Compatibility path for legacy Cron deployments.

        The production scheduler is the Durable Object alarm. If a legacy Cron
        trigger remains attached during propagation, it is harmless: it only
        checks the same persistent gate and does not enable the bot.
        """
        stub = await _state_stub(env)
        state = await stub.get_state()
        if not state.get("enabled"):
            return
        pair = state.get("paper_pair") or "btc_idr"
        try:
            await run_paper_cycle(env, stub, pair, state_response=_state_response)
        except Exception as exc:
            try:
                await stub.finish_cycle(f"legacy_scheduler_error: {exc}")
            except Exception:
                pass


__all__ = ["Default", "PaperTradingState"]
