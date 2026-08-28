"""Production dashboard API routing layered on the Cloudflare Worker base."""
from __future__ import annotations

from workers import Response

import cf_worker
from cloudflare_orchestrator import AGENT_NAMES
from paper_cycle import run_paper_cycle
from worker_entry import (
    Default as BaseDefault,
    PaperTradingState,
    _request_pair,
    _state_response,
    _state_stub,
)


def _ai_engine_status(env):
    base_url = str(getattr(env, "AI_ENGINE_URL", "") or "").strip().rstrip("/")
    secret = str(getattr(env, "AI_ENGINE_SHARED_SECRET", "") or "").strip()
    return {
        "configured": bool(base_url and len(secret) >= 32),
        "url_configured": bool(base_url),
        "secret_configured": len(secret) >= 32,
        "fallback_enabled": True,
        "source": "fastapi_cloud_orchestrator_or_local_fallback",
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

        if target == "/api/health" and request.method == "GET":
            market = await cf_worker._market_overview({"env": self.env, "query_string": b"pair=btc_idr"})
            jwt_configured = len(str(getattr(self.env, "JWT_SECRET_KEY", "") or "").strip()) >= 32
            admin_configured = bool(
                str(getattr(self.env, "ADMIN_USERNAME", "") or "").strip()
                and str(getattr(self.env, "ADMIN_PASSWORD", "") or "")
            )
            paper_binding = getattr(self.env, "PAPER_STATE", None) is not None
            ai = _ai_engine_status(self.env)
            healthy = bool(market.get("available")) and jwt_configured and admin_configured and paper_binding
            return Response.json({
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
            }, status=200 if healthy else 503)

        if target == "/api/market/overview" and request.method == "GET":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            query_string = request.url.split("?", 1)[1] if "?" in request.url else ""
            market = await cf_worker._market_overview({
                "env": self.env,
                "query_string": query_string.encode("latin-1"),
            })
            return Response.json(market, status=200 if market.get("available") else 503)

        if target == "/api/market/insights" and request.method == "GET":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            return Response.json(await cf_worker._market_insights({"env": self.env}), status=200)

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
                    "cycle_schedule": "durable_object_alarm_1m",
                    "ai_engine": _ai_engine_status(self.env),
                    "message": "Paper trading enabled manually. AI uses FastAPI when available and a safe local ensemble otherwise.",
                })
                return Response.json(payload, status=200)
            except Exception as exc:
                return Response.json({
                    "ok": False,
                    "detail": "Paper trading could not be enabled",
                    "reason": "paper_state_rpc_error",
                    "error": str(exc),
                }, status=503)

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
                return Response.json({
                    "ok": False,
                    "detail": "Paper trading could not be stopped",
                    "reason": "paper_state_rpc_error",
                    "error": str(exc),
                }, status=503)

        if target == "/api/bot/status" and request.method == "GET":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            stub = await _state_stub(self.env)
            state = await stub.ensure_scheduler()
            payload = _state_response(state)
            payload["last_orchestrator"] = await stub.ctx.storage.get("last_orchestrator")
            payload["ai_engine"] = _ai_engine_status(self.env)
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
            cycle = await run_paper_cycle(self.env, stub, _request_pair(request), state_response=_state_response)
            return Response.json(cycle, status=200 if cycle.get("ok") else 409)

        if target == "/api/dashboard/analyze" and request.method == "POST":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            stub = await _state_stub(self.env)
            if not (await stub.get_state()).get("enabled"):
                return Response.json({"detail": "Paper trading is OFF. Start the bot first.", "bot_enabled": False}, status=409)
            cycle = await run_paper_cycle(self.env, stub, _request_pair(request), state_response=_state_response)
            return Response.json(cycle, status=200 if cycle.get("ok") else 409)

        if target == "/api/bot/reset" and request.method == "POST":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            state = await (await _state_stub(self.env)).reset()
            return Response.json({**_state_response(state), "message": "Paper trading state reset."}, status=200)

        if target == "/api/dashboard/status" and request.method == "GET":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            stub = await _state_stub(self.env)
            state = await stub.ensure_scheduler()
            market = await cf_worker._market_overview({"env": self.env, "query_string": f"pair={state.get('paper_pair') or 'btc_idr'}".encode("latin-1")})
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
                    "source": "INDODAX public market data",
                    "available": bool(market.get("available")),
                    "fresh": bool(market.get("available")),
                    "stale": not bool(market.get("available")),
                    "pair": market.get("pair"),
                    "last": market.get("last"),
                    "recent_move": market.get("recent_move"),
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

        if target == "/api/dashboard/positions" and request.method == "GET":
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
            }, status=200)

        if target == "/api/dashboard/performance" and request.method == "GET":
            if not await self._verify_access(request):
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            state = await (await _state_stub(self.env)).get_state()
            history = list(state.get("trade_history") or [])
            closed = [trade for trade in history if str(trade.get("status", "")).upper() == "CLOSED"]
            pnl = sum(float(trade.get("pnl") or 0.0) for trade in closed)
            wins = sum(1 for trade in closed if float(trade.get("pnl") or 0.0) > 0)
            return Response.json({"performance": {
                "total_pnl": pnl,
                "win_rate": (wins / len(closed)) if closed else 0.0,
                "closed_trades": len(closed),
                "currency": "IDR",
                "currency_symbol": "Rp",
                "source": "durable_object_paper_state",
            }}, status=200)

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
            state = await (await _state_stub(self.env)).get_state()
            latest = await (await _state_stub(self.env)).ctx.storage.get("last_orchestrator")
            invoked = bool(latest and latest.get("agents_invoked"))
            enabled = bool(state.get("enabled"))
            agent_status = "armed" if enabled else "idle"
            suffix = "Last cycle invoked the AI ensemble." if invoked else "Waiting for the next paper cycle."
            return Response.json({"agents": [
                {"name": name, "status": agent_status, "description": suffix} for name in AGENT_NAMES
            ]}, status=200)

        return await super()._handle_state_routes(request, target)

    async def scheduled(self, controller, env, ctx):
        """Legacy compatibility hook; Durable Object Alarm remains authoritative."""
        stub = await _state_stub(env)
        state = await stub.get_state()
        if not state.get("enabled"):
            return
        try:
            await run_paper_cycle(env, stub, state.get("paper_pair") or "btc_idr", state_response=_state_response)
        except Exception as exc:
            await stub.finish_cycle(f"legacy_scheduler_error: {exc}")


__all__ = ["Default", "PaperTradingState"]
