"""Canonical Cloudflare Worker routing authority for the production dashboard.

Production uses this module as the single HTTP entrypoint. Paper trading is
always gated by the Durable Object and the real exchange remains locked.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs, urlencode, urlparse

import asgi
from js import fetch
from pyodide.ffi import to_js
from workers import Response, WorkerEntrypoint

import cf_worker
from paper_cycle import run_paper_cycle
from paper_state import PaperTradingState

RUNTIME_BUILD = "2026-09-04-paper-start-diagnostics-v1"
HISTORY_FIELDS = (
    "id,cycle_at,trading_date,cycle_id,decision_id,trade_id,cycle_number,pair,symbol,"
    "action,candidate_action,raw_action,confidence,execution_status,price,"
    "move_1m_pct,move_30m_pct,realized_pnl,pnl,fees,reasoning,risk_exit_reason,"
    "stop_loss,take_profit,pulse_status,current_pulse_status,consensus_score,"
    "market_source,persistence_status,exit_reason,agent_votes,execution_gate,hold_analysis"
)


def _state_response(state: dict) -> dict:
    counts = dict(state.get("decision_counts") or {})
    enabled = bool(state.get("enabled"))
    positions = list(state.get("positions") or [])
    return {
        **state,
        "bot_enabled": enabled,
        "enabled": enabled,
        "mode": "paper",
        "currency": "IDR",
        "currency_symbol": "Rp",
        "max_open_positions": max(1, min(3, int(state.get("max_open_positions", 3) or 3))),
        "active_positions": len(positions),
        "decision_counts": {"BUY": int(counts.get("BUY", 0)), "SELL": int(counts.get("SELL", 0)), "HOLD": int(counts.get("HOLD", 0))},
        "safety": {"mode": "paper", "real_trading_locked": True, "bot_enabled": enabled, "cycle_running": bool(state.get("cycle_running"))},
    }


def _make_refresh_token(env, username: str) -> str:
    secret = str(getattr(env, "JWT_SECRET_KEY", "") or "").strip()
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be at least 32 characters")
    now = int(time.time())
    header = cf_worker._b64url(cf_worker._json_bytes({"alg": "HS256", "typ": "JWT"}))
    payload = cf_worker._b64url(cf_worker._json_bytes({"sub": username, "iat": now, "exp": now + 7 * 24 * 60 * 60, "type": "refresh"}))
    signing_input = f"{header}.{payload}"
    signature = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{cf_worker._b64url(signature)}"


async def _state_stub(env):
    return env.PAPER_STATE.getByName("global")


def _pair(request, default="btc_idr"):
    try:
        query = parse_qs(urlparse(request.url).query)
        value = query.get("pair", query.get("symbol", [default]))[0]
        return cf_worker._clean_pair(value)
    except Exception:
        return default


def _supabase_key(env):
    return str(
        getattr(env, "SUPABASE_SECRET_KEY", "")
        or getattr(env, "SUPABASE_SERVICE_ROLE_KEY", "")
        or ""
    ).strip()


def _supabase_configured(env):
    return bool(str(getattr(env, "SUPABASE_URL", "") or "").strip() and _supabase_key(env))


def _diagnostic_failure(message, default_code="PAPER_CYCLE_FAILED"):
    text = str(message or "").lower()
    if "paper_runtime_write_enable_failed" in text:
        if "missing" in text or "credentials" in text:
            return {"code": "SUPABASE_CREDENTIALS_MISSING", "stage": "supabase_runtime_write", "message": "Supabase server credential is missing in the Cloudflare Worker."}
        return {"code": "SUPABASE_RUNTIME_WRITE_RPC_FAILED", "stage": "supabase_runtime_write", "message": "Supabase runtime-write RPC was rejected or unreachable."}
    if "market_data_unavailable" in text:
        return {"code": "MARKET_DATA_UNAVAILABLE", "stage": "market_data", "message": "INDODAX market data is unavailable or has no valid price."}
    if "market_observation_persistence_failed" in text:
        return {"code": "MARKET_OBSERVATION_PERSISTENCE_FAILED", "stage": "market_observation", "message": "Market observation could not be persisted to Supabase."}
    if "decision_persistence_failed" in text:
        return {"code": "DECISION_LEDGER_PERSISTENCE_FAILED", "stage": "decision_ledger", "message": "The paper decision could not be persisted to Supabase."}
    if "trade_ledger_persistence_failed" in text:
        return {"code": "TRADE_LEDGER_PERSISTENCE_FAILED", "stage": "trade_ledger", "message": "The paper trade could not be persisted to Supabase."}
    if "decision_trade_link_failed" in text:
        return {"code": "DECISION_TRADE_LINK_FAILED", "stage": "decision_ledger", "message": "Decision was created but linking it to the paper trade failed."}
    if "paper_history_persistence_failed" in text:
        return {"code": "PAPER_HISTORY_PERSISTENCE_FAILED", "stage": "paper_history", "message": "The paper history record could not be persisted to Supabase."}
    if "cloudflareorchestrator" in text or "orchestrator" in text or "ai_engine" in text or "ai engine" in text:
        return {"code": "AI_ENGINE_OR_ORCHESTRATOR_FAILED", "stage": "ai_engine", "message": "The AI/orchestrator analysis stage failed."}
    if "open_trade_not_found_for_sell" in text:
        return {"code": "TRADE_LEDGER_OPEN_POSITION_NOT_FOUND", "stage": "trade_ledger", "message": "The sell cycle could not find the open paper trade in the ledger."}
    if "supabase" in text or "credentials" in text or "rpc" in text:
        return {"code": "SUPABASE_OPERATION_FAILED", "stage": "supabase", "message": "A Supabase operation failed during the paper cycle."}
    return {"code": default_code, "stage": "paper_cycle", "message": "The first paper cycle failed. Check the diagnostic code and Worker logs."}


def _start_diagnostics(env, pair, state=None, failure=None):
    config = _runtime_config(env)
    out = {
        "pair": pair,
        "mode": "paper",
        "real_trading_locked": True,
        "config": config,
        "market_source": "INDODAX public market data",
    }
    if state is not None:
        out["bot_enabled"] = bool(state.get("enabled"))
        out["cycle_running"] = bool(state.get("cycle_running"))
        out["cycle_failures"] = int(state.get("cycle_failures", 0) or 0)
        out["last_cycle_status"] = state.get("last_cycle_status")
    if failure:
        out["failure"] = failure
    return out


async def _verify_access(env, request):
    value = request.headers.get("authorization", "")
    if not value.lower().startswith("bearer "):
        return None
    token = value[7:].strip()
    secret = str(getattr(env, "JWT_SECRET_KEY", "") or "").strip()
    if len(secret) < 32:
        return None
    scope = {"headers": [(b"authorization", value.encode("latin-1"))], "env": env}
    payload = cf_worker._verify_token(scope, token)
    return payload if payload and payload.get("type") == "access" else None


def _runtime_config(env):
    return {
        "jwt_configured": len(str(getattr(env, "JWT_SECRET_KEY", "") or "").strip()) >= 32,
        "admin_configured": bool(str(getattr(env, "ADMIN_USERNAME", "") or "").strip() and str(getattr(env, "ADMIN_PASSWORD", "") or "")),
        "supabase_configured": _supabase_configured(env),
        "supabase_key_source": "SUPABASE_SECRET_KEY" if str(getattr(env, "SUPABASE_SECRET_KEY", "") or "").strip() else ("SUPABASE_SERVICE_ROLE_KEY" if str(getattr(env, "SUPABASE_SERVICE_ROLE_KEY", "") or "").strip() else "missing"),
        "ai_engine_configured": bool(str(getattr(env, "AI_ENGINE_URL", "") or "").strip() and str(getattr(env, "AI_ENGINE_SHARED_SECRET", "") or "").strip()),
        "paper_state_binding": bool(getattr(env, "PAPER_STATE", None)),
    }


async def _supabase_health(env):
    url = str(getattr(env, "SUPABASE_URL", "") or "").strip().rstrip("/")
    key = _supabase_key(env)
    if not url or not key:
        return {"connected": False, "reason": "credentials_missing"}
    try:
        response = await fetch(f"{url}/rest/v1/decisions?select=id&limit=1", to_js({"method": "GET", "headers": {"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"}}))
        code = int(response.status)
        if 200 <= code < 300:
            return {"connected": True, "reason": "rest_probe_ok"}
        if code in (401, 403):
            return {"connected": False, "reason": "invalid_credentials", "http_status": code}
        if code == 404:
            return {"connected": False, "reason": "decisions_table_not_found", "http_status": code}
        return {"connected": False, "reason": "supabase_http_error", "http_status": code}
    except Exception as exc:
        return {"connected": False, "reason": type(exc).__name__}


async def _supabase_rpc(env, function_name: str, payload=None):
    url = str(getattr(env, "SUPABASE_URL", "") or "").strip().rstrip("/")
    key = _supabase_key(env)
    if not url or not key:
        return {"ok": False, "reason": "credentials_missing"}
    try:
        body = payload if isinstance(payload, dict) else {}
        response = await fetch(f"{url}/rest/v1/rpc/{function_name}", to_js({"method": "POST", "headers": {"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json", "Content-Type": "application/json"}, "body": json.dumps(body, separators=(",", ":"))}))
        code = int(response.status)
        text = await response.text()
        if code < 200 or code >= 300:
            return {"ok": False, "reason": f"http_{code}", "detail": text[:500]}
        try:
            result = json.loads(text) if text else None
        except Exception:
            result = None
        return {"ok": True, "result": result}
    except Exception as exc:
        return {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}


async def _history(env, request):
    """Read one small, bounded page of the authoritative Supabase paper ledger."""
    url = str(getattr(env, "SUPABASE_URL", "") or "").strip().rstrip("/")
    key = _supabase_key(env)
    if not url or not key:
        return Response.json({"history": [], "count": 0, "connected": False, "has_next": False, "page": 1, "page_size": 10, "reason": "credentials_missing"}, status=503)
    query = parse_qs(urlparse(request.url).query)
    date = str(query.get("date", [""])[0]).strip()
    pair = str(query.get("pair", [""])[0]).strip().upper()
    action = str(query.get("action", ["ALL"])[0]).strip().upper()
    if action not in {"ALL", "BUY", "SELL", "HOLD"}:
        return Response.json({"history": [], "count": 0, "connected": True, "has_next": False, "page": 1, "page_size": 10, "reason": "invalid_action_filter"}, status=400)
    try:
        page = max(1, int(query.get("page", ["1"])[0])); page_size = max(1, min(10, int(query.get("page_size", ["10"])[0])))
    except (TypeError, ValueError):
        page, page_size = 1, 10
    offset = (page - 1) * page_size
    params = [("select", HISTORY_FIELDS), ("order", "cycle_at.desc"), ("limit", str(page_size + 1)), ("offset", str(offset))]
    if date: params.append(("trading_date", f"eq.{date}"))
    if pair: params.append(("pair", f"eq.{pair}"))
    if action != "ALL": params.append(("action", f"eq.{action}"))
    try:
        response = await fetch(f"{url}/rest/v1/paper_history?{urlencode(params)}", to_js({"method": "GET", "headers": {"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"}}))
        code = int(response.status); text = await response.text()
        if code < 200 or code >= 300:
            return Response.json({"history": [], "count": 0, "connected": False, "has_next": False, "page": page, "page_size": page_size, "reason": f"http_{code}", "detail": text[:300]}, status=502)
        rows = json.loads(text) if text else []
        rows = rows if isinstance(rows, list) else []
        has_next = len(rows) > page_size
        return Response.json({"history": rows[:page_size], "count": min(len(rows), page_size), "connected": True, "has_next": has_next, "page": page, "page_size": page_size, "date": date or None, "pair": pair or None, "action": action})
    except Exception as exc:
        return Response.json({"history": [], "count": 0, "connected": False, "has_next": False, "page": page, "page_size": page_size, "reason": type(exc).__name__}, status=502)


class Default(WorkerEntrypoint):
    async def _auth(self, request, path):
        if path == "/api/auth/login" and request.method == "POST":
            username = str(getattr(self.env, "ADMIN_USERNAME", "") or "").strip(); password = str(getattr(self.env, "ADMIN_PASSWORD", "") or ""); secret = str(getattr(self.env, "JWT_SECRET_KEY", "") or "").strip()
            if not username or not password or len(secret) < 32: return Response.json({"detail": "Dashboard authentication is not configured"}, status=503)
            try: body = await request.json()
            except Exception: return Response.json({"detail": "Invalid JSON request body"}, status=400)
            supplied_user = str(body.get("username", "")); supplied_password = str(body.get("password", ""))
            supplied = hmac.new(secret.encode(), supplied_password.encode(), hashlib.sha256).digest(); expected = hmac.new(secret.encode(), password.encode(), hashlib.sha256).digest()
            if supplied_user != username or not hmac.compare_digest(supplied, expected): return Response.json({"detail": "Incorrect username or password"}, status=401)
            access = cf_worker._make_token({"env": self.env}, username); refresh = _make_refresh_token(self.env, username)
            return Response.json({"access_token": access, "refresh_token": refresh, "token_type": "bearer", "expires_in": 1800, "refresh_expires_in": 7 * 24 * 60 * 60, "username": username})
        if path == "/api/auth/refresh" and request.method == "POST":
            try: body = await request.json()
            except Exception: return Response.json({"detail": "Invalid JSON request body"}, status=400)
            payload = cf_worker._verify_token({"env": self.env}, str(body.get("refresh_token", ""))); username = str(getattr(self.env, "ADMIN_USERNAME", "") or "").strip()
            if not payload or payload.get("type") != "refresh" or payload.get("sub") != username: return Response.json({"detail": "Invalid or expired refresh token"}, status=401)
            return Response.json({"access_token": cf_worker._make_token({"env": self.env}, username), "token_type": "bearer", "expires_in": 1800})
        if path == "/api/auth/verify" and request.method == "GET":
            payload = await _verify_access(self.env, request)
            if not payload: return Response.json({"detail": "Invalid or expired token"}, status=401)
            return Response.json({"username": payload.get("sub"), "is_authenticated": True})
        if path == "/api/auth/logout" and request.method == "POST":
            if not await _verify_access(self.env, request): return Response.json({"detail": "Invalid or expired token"}, status=401)
            return Response.json({"message": "Logged out successfully", "status": "success"})
        return None

    async def _state_routes(self, request, path):
        protected = path.startswith("/api/dashboard/") or path.startswith("/api/bot/")
        if protected and not await _verify_access(self.env, request): return Response.json({"detail": "Invalid or expired token"}, status=401)
        stub = await _state_stub(self.env)
        if path in ("/api/bot/status", "/api/dashboard/paper/status") and request.method == "GET": return Response.json(_state_response(await stub.get_state()))
        if path in ("/api/bot/start", "/api/dashboard/paper/start") and request.method == "POST":
            pair = _pair(request)
            try:
                state = await stub.enable_paper(pair)
            except Exception as exc:
                failure = _diagnostic_failure(exc, "PAPER_START_ENABLE_FAILED")
                safe_state = await stub.get_state()
                return Response.json({**_state_response(safe_state), "message": "Paper trading could not be started.", "detail": failure["message"], "diagnostics": _start_diagnostics(self.env, pair, safe_state, failure)}, status=502)
            try:
                cycle = await run_paper_cycle(self.env, stub, pair, state_response=_state_response)
            except Exception as exc:
                failure = _diagnostic_failure(exc)
                safe_state = await stub.get_state()
                return Response.json({**_state_response(safe_state), "message": "Paper trading started but the first cycle crashed.", "detail": failure["message"], "diagnostics": _start_diagnostics(self.env, pair, safe_state, failure)}, status=502)
            if cycle.get("ok"):
                return Response.json({**_state_response(cycle["state"]), "message": "Paper trading started and first cycle completed.", "cycle": cycle, "diagnostics": _start_diagnostics(self.env, pair, cycle.get("state"))})
            failed_state = cycle.get("state") or state
            failure = _diagnostic_failure(cycle.get("error") or cycle.get("reason") or "paper_cycle_failed")
            return Response.json({**_state_response(failed_state), "message": "Paper trading enabled but first cycle failed.", "detail": failure["message"], "diagnostics": _start_diagnostics(self.env, pair, failed_state, failure), "cycle": {"ok": False, "cycle_id": cycle.get("cycle_id"), "reason": cycle.get("reason")}}, status=502)
        if path in ("/api/bot/stop", "/api/dashboard/paper/stop") and request.method == "POST":
            state = await stub.stop(); return Response.json({**_state_response(state), "message": "Paper trading stopped. Real trading remains locked."})
        if path in ("/api/bot/cycle", "/api/dashboard/paper/cycle") and request.method == "POST":
            cycle = await run_paper_cycle(self.env, stub, _pair(request), state_response=_state_response); return Response.json(cycle, status=200 if cycle.get("ok") else 409)
        if path == "/api/dashboard/analyze" and request.method == "POST":
            if not (await stub.get_state()).get("enabled"): return Response.json({"detail": "Paper trading is OFF. Start the bot first.", "bot_enabled": False}, status=409)
            cycle = await run_paper_cycle(self.env, stub, _pair(request), state_response=_state_response); return Response.json(cycle, status=200 if cycle.get("ok") else 409)
        if path in ("/api/bot/reset", "/api/dashboard/paper/reset") and request.method == "POST":
            await stub.reset()
            db_reset = await _supabase_rpc(self.env, "reset_paper_ledger")
            if not db_reset.get("ok"):
                state = await stub.get_state()
                return Response.json({**_state_response(state), "message": "Paper state reset, but Supabase ledger reset failed.", "reset": {"ok": False, "database": db_reset}}, status=502)
            state = await stub.reset()
            return Response.json({**_state_response(state), "message": "Paper trading state and Supabase ledger reset.", "reset": {"ok": True, "database": db_reset.get("result")}})
        if path == "/api/dashboard/paper/settings" and request.method == "POST":
            try: body = await request.json()
            except Exception: return Response.json({"detail": "Invalid JSON body"}, status=400)
            if "max_open_positions" in body:
                try: value = int(body.get("max_open_positions"))
                except Exception: return Response.json({"detail": "max_open_positions must be an integer from 1 to 3"}, status=400)
                if value < 1 or value > 3: return Response.json({"detail": "max_open_positions must be an integer from 1 to 3"}, status=400)
                await stub.set_position_limit(value)
            risk_patch = body.get("risk_settings")
            if isinstance(risk_patch, dict): await stub.set_risk_settings(risk_patch)
            state = await stub.get_state()
            return Response.json({**_state_response(state), "message": "Paper trading risk settings updated."})
        if path == "/api/dashboard/paper/risk" and request.method == "GET": return Response.json({"risk_settings": await stub.get_risk_settings()})
        if path == "/api/dashboard/history" and request.method == "GET": return await _history(self.env, request)
        if path == "/api/dashboard/status" and request.method == "GET":
            state = await stub.get_state(); query = parse_qs(urlparse(request.url).query); deep = str(query.get("deep", ["0"])[0]).lower() in {"1", "true", "yes"}
            configured = _supabase_configured(self.env)
            supabase = await _supabase_health(self.env) if deep else {"connected": None, "reason": "health_probe_deferred"}
            result = _state_response(state)
            result.update({"daily_pnl": float(state.get("daily_pnl", 0.0)), "daily_trades": int(state.get("daily_trades", 0)), "total_trades": int(state.get("total_trades", 0)), "active_positions": int(state.get("active_positions", 0)), "database": {"configured": configured, **supabase}, "market_data": {"source": "INDODAX public market data", "available": None, "fresh": None, "stale": None, "age_seconds": None, "probe": "market_overview"}, "system_health": {"database": {"connected": supabase.get("connected")}, "market_data": {"fresh": None, "stale": None, "age_seconds": None, "probe": "market_overview"}, "mode": "paper", "engine": {"running": bool(state.get("cycle_running")), "enabled": bool(state.get("enabled"))}}})
            return Response.json(result)
        if path == "/api/dashboard/positions" and request.method == "GET":
            state = await stub.get_state(); return Response.json({"positions": state.get("positions", []), "active_positions": int(state.get("active_positions", 0)), "max_open_positions": int(state.get("max_open_positions", 3)), "currency": "IDR", "currency_symbol": "Rp"})
        if path == "/api/dashboard/performance" and request.method == "GET":
            state = await stub.get_state(); history = list(state.get("trade_history") or []); closed = [x for x in history if x.get("action") == "SELL"]; pnls = [float(x.get("pnl") or 0) for x in closed]; wins = [x for x in pnls if x > 0]; losses = [x for x in pnls if x < 0]; gross_profit = sum(wins); gross_loss = abs(sum(losses)); fees = sum(float(x.get("fee") or 0) + float(x.get("entry_fee") or 0) for x in closed)
            return Response.json({"performance": {"total_pnl": float(state.get("total_pnl", 0)), "daily_pnl": float(state.get("daily_pnl", 0)), "closed_trades": len(closed), "win_rate": len(wins) / len(closed) if closed else 0.0, "wins": len(wins), "losses": len(losses), "average_win": gross_profit / len(wins) if wins else 0.0, "average_loss": sum(losses) / len(losses) if losses else 0.0, "profit_factor": gross_profit / gross_loss if gross_loss > 0 else None, "gross_profit": gross_profit, "gross_loss": -gross_loss, "fees": fees, "open_positions": len(state.get("positions") or []), "currency": "IDR", "currency_symbol": "Rp"}})
        if path == "/api/dashboard/recent-decision" and request.method == "GET":
            state = await stub.get_state(); return Response.json({"decision": state.get("last_decision")})
        if path == "/api/dashboard/agents" and request.method == "GET":
            enabled = bool((await stub.get_state()).get("enabled")); status = "armed" if enabled else "idle"
            return Response.json({"agents": [{"name": n, "status": status, "description": "Paper execution pipeline; AI agents run through the configured AI engine or safe fallback."} for n in ["Sentiment Agent", "Technical Agent", "Decision Agent", "Forecast Agent", "Reflector Agent"]]})
        return None

    async def scheduled(self, controller, env, ctx):
        stub = await _state_stub(env); state = await stub.get_state()
        if state.get("enabled"):
            try: await run_paper_cycle(env, stub, state.get("paper_pair") or "btc_idr", state_response=_state_response)
            except Exception as exc: await stub.finish_cycle(f"scheduled_cycle_error: {exc}")

    async def fetch(self, request):
        path = urlparse(request.url).path
        try:
            if path == "/api/system/health" and request.method == "GET":
                config = _runtime_config(self.env)
                return Response.json({"ok": True, "runtime": RUNTIME_BUILD, "mode": "paper", "real_trading_locked": True, "config": config, "timestamp": int(time.time())})
            auth = await self._auth(request, path)
            if auth is not None: return auth
            state = await self._state_routes(request, path)
            if state is not None: return state
            return await asgi.fetch(cf_worker.app, request, self.env)
        except Exception as exc:
            print(f"[worker:fetch] path={path} type={type(exc).__name__}: {exc}")
            return Response.json({"detail": "Worker request failed", "error_type": type(exc).__name__, "path": path, "runtime": RUNTIME_BUILD}, status=500)


__all__ = ["Default", "PaperTradingState"]