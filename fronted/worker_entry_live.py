"""Production Cloudflare Worker entrypoint and runtime health routes."""
from __future__ import annotations

from workers import Response

import cf_worker
from indodax_client import market_insights, market_overview, pair_from_query
from worker_entry import _state_response
from worker_entry_api import Default as BaseDefault, PaperTradingState, _state_stub, _ai_engine_status


class Default(BaseDefault):
    async def _handle_state_routes(self, request, path):
        if path == "/api/health" and request.method == "GET":
            market = await market_overview("btc_idr")
            jwt_ok = len(str(getattr(self.env, "JWT_SECRET_KEY", "") or "").strip()) >= 32
            admin_ok = bool(str(getattr(self.env, "ADMIN_USERNAME", "") or "").strip() and str(getattr(self.env, "ADMIN_PASSWORD", "") or ""))
            paper_ok = getattr(self.env, "PAPER_STATE", None) is not None
            ok = bool(market.get("available")) and jwt_ok and admin_ok and paper_ok
            return Response.json({
                "ok": ok,
                "service": "ai-trading-dashboard-worker",
                "runtime": "cloudflare-python-worker",
                "status": "healthy" if ok else "degraded",
                "checks": {
                    "indodax_public_api": {"ok": bool(market.get("available")), "last_price": market.get("last"), "pair": market.get("pair")},
                    "paper_state": {"ok": paper_ok, "type": "durable_object"},
                    "authentication": {"jwt_configured": jwt_ok, "admin_configured": admin_ok},
                    "ai_engine": _ai_engine_status(self.env),
                },
                "real_trading": "locked",
            }, status=200 if ok else 503)

        if path == "/api/market/overview" and request.method == "GET":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            query = request.url.split("?", 1)[1] if "?" in request.url else ""
            market = await market_overview(pair_from_query(query))
            return Response.json(market, status=200 if market.get("available") else 503)

        if path == "/api/market/insights" and request.method == "GET":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            return Response.json(await market_insights(), status=200)

        if path == "/api/dashboard/status" and request.method == "GET":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            stub = await _state_stub(self.env)
            state = await stub.ensure_scheduler()
            pair = state.get("paper_pair") or "btc_idr"
            market = await market_overview(pair)
            latest = await stub.ctx.storage.get("last_orchestrator")
            enabled = bool(state.get("enabled"))
            result = _state_response(state)
            result.update({
                "daily_pnl": float(state.get("daily_pnl", 0.0)),
                "daily_trades": int(state.get("daily_trades", 0)),
                "total_trades": int(state.get("total_trades", 0)),
                "active_positions": int(state.get("active_positions", 0)),
                "last_orchestrator": latest,
                "ai_engine": _ai_engine_status(self.env),
                "market_data": {
                    "source": "INDODAX public API",
                    "available": bool(market.get("available")),
                    "fresh": bool(market.get("available")),
                    "stale": not bool(market.get("available")),
                    "pair": market.get("pair"),
                    "last": market.get("last"),
                    "recent_move": market.get("recent_move"),
                    "error": market.get("error"),
                },
                "manual_control": True,
                "automation_enabled": True,
                "cycle_schedule": "durable_object_alarm_1m",
                "scheduler": {
                    "active": bool(state.get("scheduler_active")) and enabled,
                    "source": state.get("scheduler_source", "durable_object_alarm"),
                    "last_run_at": state.get("last_scheduler_at"),
                    "next_run_at": state.get("next_cycle_at"),
                    "invocations": int(state.get("scheduler_invocations", 0)),
                },
                "cycle": {
                    "number": int(state.get("cycles_today", 0)),
                    "status": state.get("last_cycle_status", "idle"),
                    "last_started_at": state.get("last_cycle_started_at"),
                    "last_finished_at": state.get("last_cycle_finished_at"),
                    "last_cycle_at": state.get("last_cycle_at"),
                    "failures": int(state.get("cycle_failures", 0)),
                    "consecutive_failures": int(state.get("consecutive_cycle_failures", 0)),
                    "last_error": state.get("last_error"),
                },
                "system_health": {
                    "database": {"connected": True, "diagnostic": "durable_object_state"},
                    "market_data": {"fresh": bool(market.get("available")), "stale": not bool(market.get("available"))},
                    "mode": "paper",
                    "engine": {"running": enabled, "enabled": enabled, "cycle_running": bool(state.get("cycle_running")), "state": "RUNNING" if enabled else "OFF", "last_cycle_status": state.get("last_cycle_status", "idle"), "last_error": state.get("last_error")},
                },
            })
            return Response.json(result, status=200)

        if path == "/api/dashboard/positions" and request.method == "GET":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            state = await (await _state_stub(self.env)).get_state(); positions = list(state.get("positions") or [])
            return Response.json({"positions": positions, "active_positions": int(state.get("active_positions", len(positions))), "currency": "IDR", "currency_symbol": "Rp"})

        if path == "/api/dashboard/performance" and request.method == "GET":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            state = await (await _state_stub(self.env)).get_state(); history = list(state.get("trade_history") or [])
            closed = [t for t in history if str(t.get("status", "")).upper() == "CLOSED"]
            pnl = sum(float(t.get("pnl") or 0.0) for t in closed); wins = sum(1 for t in closed if float(t.get("pnl") or 0.0) > 0)
            return Response.json({"performance": {"total_pnl": pnl, "win_rate": wins / len(closed) if closed else 0.0, "closed_trades": len(closed), "currency": "IDR", "currency_symbol": "Rp"}})

        return await super()._handle_state_routes(request, path)


__all__ = ["Default", "PaperTradingState"]
