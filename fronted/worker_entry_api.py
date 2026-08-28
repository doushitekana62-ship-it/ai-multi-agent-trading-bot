"""Compatibility routing layer for the Cloudflare Python Worker.

The dashboard uses /api/dashboard/paper/* while the Worker runtime exposes
its authoritative paper controls under /api/bot/*. Paper execution is manual:
START/STOP are explicit user controls and START only arms the persistent paper
state. A separate Analyze request executes one paper cycle.
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

        # START is an explicit safety control only. It must NOT execute a
        # trading cycle. A cycle is triggered separately by the dashboard's
        # explicit Analyze action while the paper gate is ON.
        if target == "/api/bot/start" and request.method == "POST":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)

            try:
                stub = await _state_stub(self.env)
                state = await stub.enable_paper()
                state = _state_response(state)
                state.update({
                    "manual_control": True,
                    "automation_enabled": False,
                    "message": "Paper trading enabled manually. No cycle was started.",
                })
                return Response.json(state, status=200)
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
                state = _state_response(state)
                state.update({
                    "manual_control": True,
                    "automation_enabled": False,
                    "message": "Paper trading disabled manually. No further cycles can run.",
                })
                return Response.json(state, status=200)
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

        # Manual cycle endpoint remains available, but the persistent gate
        # must already be ON. It never runs when the bot is OFF.
        if target == "/api/bot/cycle" and request.method == "POST":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            cycle = await _paper_cycle(self.env, _request_pair(request))
            return Response.json(cycle, status=200 if cycle.get("ok") else 409)

        return await super()._handle_state_routes(request, target)


__all__ = ["Default", "PaperTradingState"]
