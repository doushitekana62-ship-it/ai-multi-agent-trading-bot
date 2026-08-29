"""Single routing authority for the production Cloudflare Worker.

The Worker entrypoint is intentionally split into two layers: this module owns
all dashboard/paper/API routing, while worker_entry_live.py is only a thin
production adapter. Paper state remains owned by the Durable Object and every
paper cycle remains explicitly gated by BOT ON.
"""
from __future__ import annotations

from workers import Response

import cf_worker
from paper_cycle import run_paper_cycle
from worker_entry import Default as BaseDefault, PaperTradingState, _request_pair, _state_response, _state_stub


class Default(BaseDefault):
    async def _handle_state_routes(self, request, path):
        aliases = {"/api/dashboard/paper/start": "/api/bot/start", "/api/dashboard/paper/stop": "/api/bot/stop", "/api/dashboard/paper/status": "/api/bot/status", "/api/dashboard/paper/cycle": "/api/bot/cycle", "/api/dashboard/paper/reset": "/api/bot/reset"}
        target = aliases.get(path, path)

        if target == "/api/health" and request.method == "GET":
            market = await cf_worker._market_overview({"env": self.env, "query_string": b"pair=btc_idr"})
            jwt_ok = len(str(getattr(self.env, "JWT_SECRET_KEY", "") or "").strip()) >= 32
            admin_ok = bool(str(getattr(self.env, "ADMIN_USERNAME", "") or "").strip() and str(getattr(self.env, "ADMIN_PASSWORD", "") or ""))
            paper_ok = getattr(self.env, "PAPER_STATE", None) is not None
            ok = bool(market.get("available")) and jwt_ok and admin_ok and paper_ok
            return Response.json({"ok": ok, "service": "ai-trading-dashboard-worker", "runtime": "cloudflare-python-worker", "status": "healthy" if ok else "degraded", "checks": {"indodax_public_api": {"ok": bool(market.get("available")), "last_price": market.get("last"), "pair": market.get("pair")}, "paper_state": {"ok": paper_ok, "type": "durable_object"}, "authentication": {"jwt_configured": jwt_ok, "admin_configured": admin_ok}}, "real_trading": "locked"}, status=200 if ok else 503)

        if target == "/api/market/overview" and request.method == "GET":
            if not await self._verify_access(request): return Response.json({"detail": "Invalid or expired token"}, status=401)
            query = request.url.split("?", 1)[1] if "?" in request.url else ""
            market = await cf_worker._market_overview({"env": self.env, "query_string": query.encode("latin-1")})
            return Response.json(market, status=200 if market.get("available") else 503)

        if target == "/api/market/insights" and request.method == "GET":
            if not await self._verify_access(request): return Response.json({"detail": "Invalid or expired token"}, status=401)
            return Response.json(await cf_worker._market_insights({"env": self.env}), status=200)

        if target == "/api/bot/start" and request.method == "POST":
            if not await self._verify_access(request): return Response.json({"detail": "Invalid or expired token"}, status=401)
            try:
                stub = await _state_stub(self.env); state = await stub.enable_paper(_request_pair(request)); payload = _state_response(state)
                payload.update({"ok": True, "manual_control": True, "automation_enabled": True, "cycle_schedule": "durable_object_alarm_1m", "message": "Paper trading enabled manually. Cycles run only while BOT ON."})
                return Response.json(payload, status=200)
            except Exception as exc:
                return Response.json({"ok": False, "detail": "Paper trading could not be enabled", "reason": "paper_state_rpc_error", "error": str(exc)}, status=503)

        if target == "/api/bot/stop" and request.method == "POST":
            if not await self._verify_access(request): return Response.json({"detail": "Invalid or expired token"}, status=401)
            try:
                state = await (await _state_stub(self.env)).stop(); payload = _state_response(state)
                payload.update({"ok": True, "manual_control": True, "automation_enabled": True, "cycle_schedule": "durable_object_alarm_1m", "message": "Paper trading disabled manually. No further cycles will run."})
                return Response.json(payload, status=200)
            except Exception as exc:
                return Response.json({"ok": False, "detail": "Paper trading could not be stopped", "reason": "paper_state_rpc_error", "error": str(exc)}, status=503)

        if target == "/api/bot/status" and request.method == "GET":
            if not await self._verify_access(request): return Response.json({"detail": "Invalid or expired token"}, status=401)
            stub = await _state_stub(self.env); state = await stub.ensure_scheduler(); payload = _state_response(state); payload["last_orchestrator"] = await stub.ctx.storage.get("last_orchestrator")
            payload.update({"manual_control": True, "automation_enabled": True, "cycle_schedule": "durable_object_alarm_1m"})
            return Response.json(payload, status=200)

        if target == "/api/bot/cycle" and request.method == "POST":
            if not await self._verify_access(request): return Response.json({"detail": "Invalid or expired token"}, status=401)
            stub = await _state_stub(self.env); cycle = await run_paper_cycle(self.env, stub, _request_pair(request), state_response=_state_response)
            return Response.json(cycle, status=200 if cycle.get("ok") else 409)

        if target == "/api/dashboard/analyze" and request.method == "POST":
            if not await self._verify_access(request): return Response.json({"detail": "Invalid or expired token"}, status=401)
            stub = await _state_stub(self.env)
            if not (await stub.get_state()).get("enabled"): return Response.json({"detail": "Paper trading is OFF. Start the bot first.", "bot_enabled": False}, status=409)
            cycle = await run_paper_cycle(self.env, stub, _request_pair(request), state_response=_state_response)
            return Response.json(cycle, status=200 if cycle.get("ok") else 409)

        if target == "/api/bot/reset" and request.method == "POST":
            if not await self._verify_access(request): return Response.json({"detail": "Invalid or expired token"}, status=401)
            state = await (await _state_stub(self.env)).reset(); return Response.json({**_state_response(state), "message": "Paper trading state reset."}, status=200)

        if target == "/api/dashboard/status" and request.method == "GET":
            if not await self._verify_access(request): return Response.json({"detail": "Invalid or expired token"}, status=401)
            stub = await _state_stub(self.env); state = await stub.ensure_scheduler(); market = await cf_worker._market_overview({"env": self.env, "query_string": f"pair={state.get('paper_pair') or 'btc_idr'}".encode("latin-1")}); result = _state_response(state)
            result.update({"daily_pnl": float(state.get("daily_pnl", 0.0)), "daily_trades": int(state.get("daily_trades", 0)), "total_trades": int(state.get("total_trades", 0)), "active_positions": int(state.get("active_positions", 0)), "last_orchestrator": await stub.ctx.storage.get("last_orchestrator"), "market_data": {"source": "INDODAX public API", "available": bool(market.get("available")), "fresh": bool(market.get("available")), "stale": not bool(market.get("available")), "pair": market.get("pair"), "last": market.get("last"), "recent_move": market.get("recent_move")}, "manual_control": True, "automation_enabled": True, "cycle_schedule": "durable_object_alarm_1m", "scheduler": {"active": bool(state.get("scheduler_active")) and bool(state.get("enabled")), "source": state.get("scheduler_source", "durable_object_alarm"), "last_run_at": state.get("last_scheduler_at"), "next_run_at": state.get("next_cycle_at"), "invocations": int(state.get("scheduler_invocations", 0))}, "cycle": {"number": int(state.get("cycles_today", 0)), "status": state.get("last_cycle_status", "idle"), "last_started_at": state.get("last_cycle_started_at"), "last_finished_at": state.get("last_cycle_finished_at"), "last_cycle_at": state.get("last_cycle_at"), "failures": int(state.get("cycle_failures", 0)), "consecutive_failures": int(state.get("consecutive_cycle_failures", 0)), "last_error": state.get("last_error")}, "system_health": {"database": {"connected": True, "diagnostic": "durable_object_state"}, "market_data": {"fresh": bool(market.get("available")), "stale": not bool(market.get("available"))}, "mode": "paper", "engine": {"running": bool(state.get("enabled")), "enabled": bool(state.get("enabled")), "cycle_running": bool(state.get("cycle_running")), "state": "RUNNING" if state.get("enabled") else "OFF", "last_cycle_status": state.get("last_cycle_status", "idle"), "last_error": state.get("last_error")}}})
            return Response.json(result, status=200)

        if target == "/api/dashboard/positions" and request.method == "GET":
            if not await self._verify_access(request): return Response.json({"detail": "Invalid or expired token"}, status=401)
            state = await (await _state_stub(self.env)).get_state(); positions = list(state.get("positions") or [])
            return Response.json({"positions": positions, "active_positions": int(state.get("active_positions", len(positions))), "currency": "IDR", "currency_symbol": "Rp"}, status=200)

        if target == "/api/dashboard/performance" and request.method == "GET":
            if not await self._verify_access(request): return Response.json({"detail": "Invalid or expired token"}, status=401)
            state = await (await _state_stub(self.env)).get_state(); history = list(state.get("trade_history") or []); closed = [trade for trade in history if str(trade.get("status", "")).upper() == "CLOSED"]; pnl = sum(float(trade.get("pnl") or 0.0) for trade in closed); wins = sum(1 for trade in closed if float(trade.get("pnl") or 0.0) > 0)
            return Response.json({"performance": {"total_pnl": pnl, "win_rate": wins / len(closed) if closed else 0.0, "closed_trades": len(closed), "currency": "IDR", "currency_symbol": "Rp"}}, status=200)

        if target == "/api/dashboard/recent-decision" and request.method == "GET":
            if not await self._verify_access(request): return Response.json({"detail": "Invalid or expired token"}, status=401)
            stub = await _state_stub(self.env); state = await stub.get_state(); latest = await stub.ctx.storage.get("last_orchestrator"); decision = state.get("last_decision")
            if latest: decision = {**(decision or {}), **latest}
            return Response.json({"decision": decision}, status=200)

        if target == "/api/dashboard/agents" and request.method == "GET":
            if not await self._verify_access(request): return Response.json({"detail": "Invalid or expired token"}, status=401)
            stub = await _state_stub(self.env); state = await stub.get_state(); latest = await stub.ctx.storage.get("last_orchestrator"); invoked = bool(latest and latest.get("agents_invoked")); status = "armed" if state.get("enabled") else "idle"; suffix = "Last cycle invoked by Orchestrator." if invoked else "Waiting for the next paper cycle."
            return Response.json({"agents": [{"name": name, "status": status, "description": suffix} for name in ["Sentiment Agent", "Technical Agent", "Decision Agent", "Forecast Agent", "Reflector Agent"]]}, status=200)

        return await super()._handle_state_routes(request, target)

    async def scheduled(self, controller, env, ctx):
        stub = await _state_stub(env); state = await stub.get_state()
        if not state.get("enabled"): return
        try:
            await run_paper_cycle(env, stub, state.get("paper_pair") or "btc_idr", state_response=_state_response)
        except Exception as exc:
            try: await stub.finish_cycle(f"legacy_scheduler_error: {exc}")
            except Exception: pass


__all__ = ["Default", "PaperTradingState"]
