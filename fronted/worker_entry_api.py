"""Compatibility routing layer for the Cloudflare Python Worker.

The dashboard uses /api/dashboard/paper/* while the Worker runtime exposes
its authoritative paper controls under /api/bot/*. This layer keeps both
contracts and makes the start operation resilient to Durable Object RPC
errors instead of allowing an unhandled Worker exception to reach the browser.
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

        # Handle START explicitly so the dashboard does not depend on the
        # older Durable Object RPC method name `start`.
        if target == "/api/bot/start" and request.method == "POST":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)

            try:
                stub = await _state_stub(self.env)
                state = await stub.enable_paper()
            except Exception as exc:
                # RPC exceptions otherwise propagate out of the Worker and
                # become the Cloudflare "unhandled exception" page.
                return Response.json(
                    {
                        "ok": False,
                        "detail": "Paper trading could not be started",
                        "reason": "paper_state_rpc_error",
                        "error": str(exc),
                    },
                    status=503,
                )

            try:
                cycle = await _paper_cycle(self.env, _request_pair(request))
                return Response.json(
                    {
                        **_state_response(cycle.get("state") or state),
                        "message": "Paper trading started and one execution cycle completed.",
                        "cycle": cycle,
                    },
                    status=200 if cycle.get("ok") else 409,
                )
            except Exception as exc:
                try:
                    current = await stub.get_state()
                except Exception:
                    current = state
                return Response.json(
                    {
                        **_state_response(current),
                        "ok": False,
                        "detail": "Paper trading started but the first cycle failed",
                        "reason": "paper_cycle_error",
                        "error": str(exc),
                    },
                    status=503,
                )

        return await super()._handle_state_routes(request, target)


__all__ = ["Default", "PaperTradingState"]
