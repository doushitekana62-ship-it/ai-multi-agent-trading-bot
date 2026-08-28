"""Production Cloudflare Worker entrypoint.

This adapter keeps the existing dashboard/paper-trading implementation while
making runtime health, INDODAX market data, and Durable Object dashboard state
explicit. The paper account state remains authoritative in the Durable Object;
Supabase is not required for the dashboard to display a valid paper session.
"""
from __future__ import annotations

import json

from js import fetch
from pyodide.ffi import to_js
from workers import Response

import cf_worker
from worker_entry import _state_response
from worker_entry_api import Default as BaseDefault, PaperTradingState, _state_stub


async def _probe_ai_engine(env):
    base_url = str(getattr(env, "AI_ENGINE_URL", "") or "").strip().rstrip("/")
    if not base_url:
        return {"configured": False, "reachable": False, "status": "not_configured"}
    try:
        response = await fetch(
            f"{base_url}/ready",
            to_js({"method": "GET", "headers": {"Accept": "application/json"}}),
        )
        status_code = int(response.status)
        text = await response.text()
        try:
            payload = json.loads(text)
        except Exception:
            payload = {}
        return {
            "configured": True,
            "reachable": 200 <= status_code < 300,
            "http_status": status_code,
            "status": payload.get("status", "unhealthy") if isinstance(payload, dict) else "unhealthy",
            "secret_configured": bool(payload.get("ai_engine_secret_configured")) if isinstance(payload, dict) else False,
        }
    except Exception as exc:
        return {"configured": True, "reachable": False, "status": "unreachable", "error": type(exc).__name__}


class Default(BaseDefault):
    async def _handle_state_routes(self, request, path):
        if path == "/api/health" and request.method == "GET":
            market = await cf_worker._market_overview({"env": self.env, "query_string": b"pair=btc_idr"})
            ai = await _probe_ai_engine(self.env)
            jwt_configured = len(str(getattr(self.env, "JWT_SECRET_KEY", "") or "").strip()) >= 32
            admin_configured = bool(
                str(getattr(self.env, "ADMIN_USERNAME", "") or "").strip()
                and str(getattr(self.env, "ADMIN_PASSWORD", "") or "")
            )
            paper_binding = getattr(self.env, "PAPER_STATE", None) is not None
            healthy = bool(market.get("available")) and jwt_configured and admin_configured and paper_binding
            return Response.json(
                {
                    "ok": healthy,
                    "service": "ai-trading-dashboard-worker",
                    "runtime": "cloudflare-python-worker",
                    "status": "healthy" if healthy else "degraded",
                    "checks": {
                        "indodax_public_api": {
                            "ok": bool(market.get("available")),
                            "last_price": market.get("last"),
                            "pair": market.get("pair", "btc_idr"),
                        },
                        "paper_state": {"ok": paper_binding, "type": "durable_object"},
                        "authentication": {"jwt_configured": jwt_configured, "admin_configured": admin_configured},
                        "ai_engine": ai,
                    },
                    "real_trading": "locked",
                },
                status=200 if healthy else 503,
            )

        if path == "/api/market/overview" and request.method == "GET":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            query_string = request.url.split("?", 1)[1] if "?" in request.url else ""
            market = await cf_worker._market_overview({
                "env": self.env,
                "query_string": query_string.encode("latin-1"),
            })
            return Response.json(market, status=200 if market.get("available") else 503)

        if path == "/api/market/insights" and request.method == "GET":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            return Response.json(await cf_worker._market_insights({"env": self.env}), status=200)

        if path == "/api/dashboard/status" and request.method == "GET":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            stub = await _state_stub(self.env)
            state = await stub.ensure_scheduler()
            market = await cf_worker._market_overview({"env": self.env, "query_string": b"pair=btc_idr"})
            ai = await _probe_ai_engine(self.env)
            enabled = bool(state.get("enabled"))
            result = _state_response(state)
            result.update({
                "daily_pnl": float(state.get("daily_pnl", 0.0)),
                "daily_trades": int(state.get("daily_trades", 0)),
                "total_trades": int(state.get("total_trades", 0)),
                "active_positions": int(state.get("active_positions", 0)),
                "last_orchestrator": await stub.ctx.storage.get("last_orchestrator"),
                "market_data": {
                    "source": "INDODAX public market data",
                    "available": bool(market.get("available")),
                    "fresh": bool(market.get("available")),
                    "stale": not bool(market.get("available")),
                    "pair": market.get("pair"),
                },
                "ai_engine": ai,
                "system_health": {
                    "database": {"connected": True, "diagnostic": "durable_object_state"},
                    "market_data": {"fresh": bool(market.get("available")), "stale": not bool(market.get("available"))},
                    "mode": "paper",
                    "engine": {
                        "running": enabled,
                        "enabled": enabled,
                        "cycle_running": bool(state.get("cycle_running")),
                        "state": "RUNNING" if enabled else "OFF",
                        "last_cycle_status": state.get("last_cycle_status", "idle"),
                        "last_error": state.get("last_error"),
                    },
                },
            })
            return Response.json(result, status=200)

        if path == "/api/dashboard/positions" and request.method == "GET":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            state = await (await _state_stub(self.env)).get_state()
            positions = list(state.get("positions") or [])
            return Response.json({
                "positions": positions,
                "active_positions": int(state.get("active_positions", len(positions))),
                "currency": "IDR",
                "currency_symbol": "Rp",
                "source": "durable_object_paper_state",
            })

        if path == "/api/dashboard/performance" and request.method == "GET":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            state = await (await _state_stub(self.env)).get_state()
            history = list(state.get("trade_history") or [])
            closed = [trade for trade in history if str(trade.get("status", "")).upper() == "CLOSED"]
            pnl = sum(float(trade.get("pnl") or 0.0) for trade in closed)
            wins = sum(1 for trade in closed if float(trade.get("pnl") or 0.0) > 0)
            return Response.json({
                "performance": {
                    "total_pnl": pnl,
                    "win_rate": (wins / len(closed)) if closed else 0.0,
                    "closed_trades": len(closed),
                    "currency": "IDR",
                    "currency_symbol": "Rp",
                    "source": "durable_object_paper_state",
                }
            })

        return await super()._handle_state_routes(request, path)


__all__ = ["Default", "PaperTradingState"]
