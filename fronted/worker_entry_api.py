"""Compatibility routing layer for the existing Cloudflare Python Worker.

The dashboard historically used /api/dashboard/paper/* while the current
Worker runtime exposes the authoritative paper controls under /api/bot/*.
Keep both contracts without changing the dashboard layout or paper state model.
"""
from __future__ import annotations

from worker_entry import Default as BaseDefault, PaperTradingState


class Default(BaseDefault):
    async def _handle_state_routes(self, request, path):
        aliases = {
            "/api/dashboard/paper/start": "/api/bot/start",
            "/api/dashboard/paper/stop": "/api/bot/stop",
            "/api/dashboard/paper/status": "/api/bot/status",
            "/api/dashboard/paper/cycle": "/api/bot/cycle",
            "/api/dashboard/paper/reset": "/api/bot/reset",
        }
        return await super()._handle_state_routes(request, aliases.get(path, path))


__all__ = ["Default", "PaperTradingState"]
