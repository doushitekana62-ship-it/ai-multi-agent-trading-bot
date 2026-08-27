"""Cloudflare Worker entrypoint with persistent paper-trading control."""
from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlparse

import asgi
from workers import WorkerEntrypoint, Response
from js import fetch
from pyodide.ffi import to_js

import cf_worker
from paper_state import PaperTradingState


async def _access_only(scope):
    value = cf_worker._authorization(scope)
    if not value.lower().startswith("bearer "):
        return None
    payload = cf_worker._verify_token(scope, value[7:].strip())
    if not payload or payload.get("type") != "access":
        return None
    return payload


cf_worker._require_user = _access_only


def _make_refresh_token(env, username: str) -> str:
    secret = str(getattr(env, "JWT_SECRET_KEY", "") or "").strip()
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be at least 32 characters")
    now = int(time.time())
    header = cf_worker._b64url(cf_worker._json_bytes({"alg": "HS256", "typ": "JWT"}))
    payload = cf_worker._b64url(cf_worker._json_bytes({"sub": username, "iat": now, "exp": now + 7 * 24 * 60 * 60, "type": "refresh"}))
    signing_input = f"{header}.{payload}"
    signature = hmac.new(secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest()
    return f"{signing_input}.{cf_worker._b64url(signature)}"


async def _state_stub(env):
    return env.PAPER_STATE.getByName("global")


def _runtime_hours(started_at):
    if not started_at:
        return 0.0
    try:
        started = time.mktime(time.strptime(str(started_at)[:19], "%Y-%m-%dT%H:%M:%S"))
        return max(0.0, (time.time() - started) / 3600.0)
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _state_response(state):
    decision_counts = dict(state.get("decision_counts") or {})
    enabled = bool(state.get("enabled"))
    cycle_running = bool(state.get("cycle_running"))
    return {
        **state,
        "bot_enabled": enabled,
        "enabled": enabled,
        "cycle_running": cycle_running,
        "mode": "paper",
        "currency": "IDR",
        "currency_symbol": "Rp",
        "max_open_positions": int(state.get("max_open_positions", 5)),
        "runtime_hours": _runtime_hours(state.get("started_at")) if enabled else 0.0,
        "decision_counts": {"BUY": int(decision_counts.get("BUY", 0)), "SELL": int(decision_counts.get("SELL", 0)), "HOLD": int(decision_counts.get("HOLD", 0))},
        "safety": {"mode": "paper", "real_trading_locked": True, "bot_enabled": enabled, "cycle_running": cycle_running},
    }


async def _supabase_health(env):
    """Probe a real public table through PostgREST without exposing secrets."""
    url = str(getattr(env, "SUPABASE_URL", "") or "").strip().rstrip("/")
    key = str(getattr(env, "SUPABASE_SERVICE_ROLE_KEY", "") or "").strip()
    if not url or not key:
        return {"connected": False, "reason": "credentials_missing"}
    try:
        response = await fetch(
            f"{url}/rest/v1/decisions?select=id&limit=1",
            to_js({
                "method": "GET",
                "headers": {
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                    "Accept": "application/json",
                },
            }),
        )
        code = int(response.status)
        if 200 <= code < 300:
            return {"connected": True, "reason": "rest_probe_ok"}
        if code in (401, 403):
            return {"connected": False, "reason": "invalid_credentials", "http_status": code}
        if code == 404:
            return {"connected": False, "reason": "decisions_table_not_found", "http_status": code}
        return {"connected": False, "reason": "supabase_http_error", "http_status": code}
    except Exception:
        return {"connected": False, "reason": "network_or_runtime_error"}


async def _paper_cycle(env, pair="btc_idr"):
    """Run one safe paper-only cycle through the persistent state gate."""
    stub = await _state_stub(env)
    ok, _, reason = await stub.begin_cycle()
    if not ok:
        return {"ok": False, "reason": reason, "state": _state_response(await stub.get_state())}

    try:
        scope = {"env": env, "query_string": f"pair={pair}".encode("latin-1")}
        market = await cf_worker._market_overview(scope)
        if not market.get("available") or float(market.get("last") or 0) <= 0:
            await stub.finish_cycle()
            return {"ok": False, "reason": "market_data_unavailable", "state": _state_response(await stub.get_state())}

        move = float(market.get("recent_move") or 0.0)
        high = float(market.get("high") or 0.0)
        low = float(market.get("low") or 0.0)
        last = float(market.get("last") or 0.0)
        range_position = ((last - low) / (high - low) * 100.0) if high > low else 50.0

        # Smoke-test signal only. This is deliberately NOT the multi-agent AI
        # decision engine; it proves the paper state/execution path end-to-end.
        if move >= 0.15 or range_position >= 80.0:
            action = "BUY"
            confidence = min(0.95, 0.60 + max(abs(move), range_position - 70.0) / 100.0)
        elif move <= -0.15 or range_position <= 20.0:
            action = "SELL"
            confidence = min(0.95, 0.60 + max(abs(move), 20.0 - range_position) / 100.0)
        else:
            action, confidence = "HOLD", 0.50

        state = await stub.record_cycle(
            decision=action,
            confidence=confidence,
            symbol=market["pair"].upper().replace("_", "/"),
            price=last,
            reasoning=f"Paper pipeline smoke-test signal: recent_move={move:.4f}%, range_position={range_position:.1f}%.",
        )
        return {"ok": True, "action": action, "confidence": confidence, "market": market, "state": _state_response(state)}
    except Exception as exc:
        await stub.finish_cycle()
        return {"ok": False, "reason": "cycle_error", "error": str(exc), "state": _state_response(await stub.get_state())}


class Default(WorkerEntrypoint):
    async def _verify_access(self, request):
        value = request.headers.get("authorization", "")
        if not value.lower().startswith("bearer "):
            return None
        token = value[7:].strip()
        secret = str(getattr(self.env, "JWT_SECRET_KEY", "") or "").strip()
        if len(secret) < 32:
            return None
        scope = {"headers": [(b"authorization", value.encode("latin-1"))], "env": self.env}
        payload = cf_worker._verify_token(scope, token)
        if not payload or payload.get("type") != "access":
            return None
        return payload

    async def _handle_auth(self, request, path):
        if path == "/api/auth/login" and request.method == "POST":
            configured_user = str(getattr(self.env, "ADMIN_USERNAME", "") or "").strip()
            configured_password = str(getattr(self.env, "ADMIN_PASSWORD", "") or "")
            if not configured_user or not configured_password:
                return Response.json({"detail": "Dashboard authentication is not configured"}, status=503)
            try:
                body = await request.json()
                username = str(body.get("username", ""))
                password = str(body.get("password", ""))
            except Exception:
                return Response.json({"detail": "Invalid JSON request body"}, status=400)
            secret = str(getattr(self.env, "JWT_SECRET_KEY", "") or "").strip()
            if len(secret) < 32:
                return Response.json({"detail": "JWT_SECRET_KEY must be at least 32 characters"}, status=503)
            supplied = hmac.new(secret.encode("utf-8"), password.encode("utf-8"), hashlib.sha256).digest()
            expected = hmac.new(secret.encode("utf-8"), configured_password.encode("utf-8"), hashlib.sha256).digest()
            if username != configured_user or not hmac.compare_digest(supplied, expected):
                return Response.json({"detail": "Incorrect username or password"}, status=401)
            token = cf_worker._make_token({"env": self.env}, configured_user)
            refresh = _make_refresh_token(self.env, configured_user)
            return Response.json({"access_token": token, "refresh_token": refresh, "token_type": "bearer", "expires_in": 1800, "refresh_expires_in": 7 * 24 * 60, "username": configured_user})

        if path == "/api/auth/refresh" and request.method == "POST":
            try:
                body = await request.json()
                refresh = str(body.get("refresh_token", ""))
            except Exception:
                return Response.json({"detail": "Invalid JSON request body"}, status=400)
            payload = cf_worker._verify_token({"env": self.env}, refresh)
            if not payload or payload.get("type") != "refresh":
                return Response.json({"detail": "Invalid or expired refresh token"}, status=401)
            username = payload.get("sub")
            configured_user = str(getattr(self.env, "ADMIN_USERNAME", "") or "").strip()
            if not username or username != configured_user:
                return Response.json({"detail": "User not found"}, status=401)
            token = cf_worker._make_token({"env": self.env}, username)
            return Response.json({"access_token": token, "token_type": "bearer", "expires_in": 1800})

        if path == "/api/auth/verify" and request.method == "GET":
            payload = await self._verify_access(request)
            if not payload:
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            return Response.json({"username": payload.get("sub"), "is_authenticated": True})

        if path == "/api/auth/logout" and request.method == "POST":
            payload = await self._verify_access(request)
            if not payload:
                return Response.json({"detail": "Invalid or expired token"}, status=401)
            return Response.json({"message": "Logged out successfully", "status": "success"})
        return None

    async def _handle_state_routes(self, request, path):
        protected = path.startswith("/api/dashboard/") or path.startswith("/api/bot/")
        if protected and not await self._verify_access(request):
            return Response.json({"detail": "Invalid or expired token"}, status=401)
        stub = await _state_stub(self.env)

        if path == "/api/bot/status" and request.method == "GET":
            return Response.json(_state_response(await stub.get_state()))

        if path == "/api/bot/start" and request.method == "POST":
            state = await stub.start()
            cycle = await _paper_cycle(self.env)
            return Response.json({**_state_response(cycle.get("state") or state), "message": "Paper trading started and one execution cycle completed.", "cycle": cycle})

        if path == "/api/bot/stop" and request.method == "POST":
            state = await stub.stop()
            return Response.json({**_state_response(state), "message": "Paper trading stopped. Real trading remains locked."})

        if path == "/api/bot/cycle" and request.method == "POST":
            cycle = await _paper_cycle(self.env)
            return Response.json(cycle, status=200 if cycle.get("ok") else 409)

        if path == "/api/dashboard/analyze" and request.method == "POST":
            if not (await stub.get_state()).get("enabled"):
                return Response.json({"detail": "Paper trading is OFF. Start the bot first.", "bot_enabled": False}, status=409)
            cycle = await _paper_cycle(self.env)
            return Response.json(cycle, status=200 if cycle.get("ok") else 409)

        if path == "/api/bot/reset" and request.method == "POST":
            state = await stub.reset()
            return Response.json({**_state_response(state), "message": "Paper trading state reset."})

        if path == "/api/dashboard/status" and request.method == "GET":
            state = await stub.get_state()
            result = _state_response(state)
            supabase_configured = bool(str(getattr(self.env, "SUPABASE_URL", "") or "").strip() and str(getattr(self.env, "SUPABASE_SERVICE_ROLE_KEY", "") or "").strip())
            supabase_health = await _supabase_health(self.env) if supabase_configured else {"connected": False, "reason": "credentials_missing"}
            supabase_connected = bool(supabase_health.get("connected"))
            cycle_running = bool(state.get("cycle_running"))
            result.update({
                "daily_pnl": float(state.get("daily_pnl", 0.0)),
                "daily_trades": int(state.get("daily_trades", 0)),
                "total_trades": int(state.get("total_trades", 0)),
                "active_positions": int(state.get("active_positions", 0)),
                "database": {"configured": supabase_configured, "connected": supabase_connected, "status": "connected" if supabase_connected else ("not_configured" if not supabase_configured else "unreachable"), "diagnostic": supabase_health.get("reason")},
                "market_data": {"source": "INDODAX public market data", "available": True, "fresh": None, "stale": None, "age_seconds": None},
                "system_health": {"database": {"connected": supabase_connected, "diagnostic": supabase_health.get("reason")}, "market_data": {"fresh": None, "stale": None, "age_seconds": None}, "mode": state.get("mode", "paper"), "engine": {"running": cycle_running}},
            })
            return Response.json(result)

        if path == "/api/dashboard/positions" and request.method == "GET":
            state = await stub.get_state()
            return Response.json({"positions": state.get("positions", []), "active_positions": int(state.get("active_positions", 0)), "currency": "IDR", "currency_symbol": "Rp"})

        if path == "/api/dashboard/performance" and request.method == "GET":
            state = await stub.get_state()
            trades = int(state.get("total_trades", 0))
            return Response.json({"performance": {"total_pnl": float(state.get("total_pnl", 0.0)), "daily_pnl": float(state.get("daily_pnl", 0.0)), "closed_trades": trades, "win_rate": 0.0, "currency": "IDR", "currency_symbol": "Rp"}})

        if path == "/api/dashboard/recent-decision" and request.method == "GET":
            state = await stub.get_state()
            return Response.json({"decision": state.get("last_decision")})

        if path == "/api/dashboard/agents" and request.method == "GET":
            enabled = bool((await stub.get_state()).get("enabled"))
            status = "armed" if enabled else "idle"
            return Response.json({"agents": [{"name": name, "status": status, "description": "Paper execution pipeline; AI agents are not invoked by this worker cycle."} for name in ["Sentiment Agent", "Technical Agent", "Decision Agent", "Forecast Agent", "Reflector Agent"]]})

        return None

    async def scheduled(self, controller, env, ctx):
        # If a Cron Trigger is later configured, every scheduled invocation
        # becomes a paper cycle only while the persistent bot gate is enabled.
        state = await env.PAPER_STATE.getByName("global").get_state()
        if state.get("enabled"):
            await _paper_cycle(env)

    async def fetch(self, request):
        url = urlparse(request.url)
        path = url.path
        auth_response = await self._handle_auth(request, path)
        if auth_response is not None:
            return auth_response
        state_response = await self._handle_state_routes(request, path)
        if state_response is not None:
            return state_response
        return await asgi.fetch(cf_worker.app, request, self.env)


__all__ = ["Default", "PaperTradingState"]
