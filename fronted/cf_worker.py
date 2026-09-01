import base64
import hashlib
import hmac
import json
import time
from urllib.parse import urlparse, parse_qs

import asgi
from workers import WorkerEntrypoint
from js import fetch
from pyodide.ffi import to_js

JSON_HEADERS = [(b"content-type", b"application/json; charset=utf-8")]
PAPER_INITIAL_BALANCE = 10_000_000.0
MAX_OPEN_POSITIONS = 3
INDODAX_PUBLIC_BASE = "https://indodax.com/api"
SCALPING_PAIRS = {
    "btc_idr", "eth_idr", "usdt_idr", "xrp_idr", "doge_idr", "sol_idr",
    "beat_idr", "hype_idr", "ada_idr", "trx_idr", "shib_idr", "pepe_idr",
}


def _json_bytes(value):
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _env(scope, name, default=""):
    return str(getattr(scope.get("env"), name, default) or default)


def _secret(scope) -> str:
    secret = _env(scope, "JWT_SECRET_KEY").strip()
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be at least 32 characters")
    return secret


def _hmac_sha256(secret: str, message: str) -> bytes:
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest()


def _make_token(scope, username: str) -> str:
    now = int(time.time())
    header = _b64url(_json_bytes({"alg": "HS256", "typ": "JWT"}))
    payload = _b64url(_json_bytes({"sub": username, "iat": now, "exp": now + 1800, "type": "access"}))
    signing_input = f"{header}.{payload}"
    return f"{signing_input}.{_b64url(_hmac_sha256(_secret(scope), signing_input))}"


def _verify_token(scope, token: str):
    try:
        header, payload, signature = token.split(".", 2)
        if json.loads(_b64url_decode(header)).get("alg") != "HS256":
            return None
        data = json.loads(_b64url_decode(payload))
        if int(data.get("exp", 0)) <= int(time.time()):
            return None
        if not hmac.compare_digest(_hmac_sha256(_secret(scope), f"{header}.{payload}"), _b64url_decode(signature)):
            return None
        return data
    except Exception:
        return None


def _authorization(scope) -> str:
    for key, value in scope.get("headers", []):
        key_text = key.decode("latin-1") if isinstance(key, (bytes, bytearray)) else str(key)
        if key_text.lower() == "authorization":
            return value.decode("latin-1") if isinstance(value, (bytes, bytearray)) else str(value)
    return ""


async def _read_body(receive):
    chunks = []
    while True:
        message = await receive()
        if message.get("type") != "http.request":
            break
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


async def _send(send, status, headers, body):
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _json_response(send, status, payload):
    await _send(send, status, JSON_HEADERS, _json_bytes(payload))


async def _require_user(scope):
    value = _authorization(scope)
    if not value.lower().startswith("bearer "):
        return None
    return _verify_token(scope, value[7:].strip())


async def _supabase_request(scope, path, method="GET"):
    url = _env(scope, "SUPABASE_URL").rstrip("/")
    key = _env(scope, "SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    try:
        response = await fetch(
            f"{url}{path}",
            to_js({"method": method, "headers": {"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"}}),
        )
        if int(response.status) >= 400:
            return None
        return json.loads(await response.text())
    except Exception:
        return None


async def _supabase_probe(scope):
    return (await _supabase_request(scope, "/rest/v1/")) is not None


async def _public_indodax(path):
    try:
        response = await fetch(f"{INDODAX_PUBLIC_BASE}{path}", to_js({"method": "GET", "headers": {"Accept": "application/json"}}))
        if int(response.status) >= 400:
            return None
        return json.loads(await response.text())
    except Exception:
        return None


def _query_value(scope, name, default=""):
    raw = scope.get("query_string", b"")
    query = raw.decode("latin-1") if isinstance(raw, (bytes, bytearray)) else str(raw or "")
    return parse_qs(query).get(name, [default])[0]


def _clean_pair(value):
    value = (value or "btc_idr").strip().lower().replace("/", "_")
    return value if value in SCALPING_PAIRS else "btc_idr"


def _recent_trade_move(points):
    values = [float(p["price"]) for p in points if float(p.get("price", 0) or 0) > 0]
    if len(values) < 2 or values[0] == 0:
        return None
    return ((values[-1] - values[0]) / values[0]) * 100.0


def _normalize_public_trades(payload):
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("trades") or payload.get("data") or []
    else:
        rows = []
    points = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        try:
            price = float(item.get("price") or 0)
            amount = float(item.get("amount") or 0)
            timestamp = float(item.get("date") or item.get("trade_time") or item.get("timestamp") or 0)
            if price <= 0 or timestamp <= 0:
                continue
            trade_type = str(item.get("type") or item.get("side") or "").lower()
            points.append({"tid": str(item.get("tid") or item.get("trade_id") or ""), "price": price, "timestamp": timestamp, "amount": amount, "type": trade_type, "side": trade_type, "source": "INDODAX public market data"})
        except (TypeError, ValueError):
            continue
    return points


async def _market_overview(scope):
    pair = _clean_pair(_query_value(scope, "pair", "btc_idr"))
    ticker = await _public_indodax(f"/{pair}/ticker")
    trades = await _public_indodax(f"/{pair}/trades")
    if not ticker or not isinstance(ticker.get("ticker"), dict):
        return {"available": False, "pair": pair, "currency": "IDR", "currency_symbol": "Rp", "source": "INDODAX public market data"}
    t = ticker["ticker"]
    trade_points = _normalize_public_trades(trades)[-1440:]
    last_price = float(t.get("last") or 0)
    ticker_timestamp = int(time.time())
    ticker_point = {
        "tid": f"ticker:{pair}:{ticker_timestamp}:{last_price}",
        "price": last_price,
        "timestamp": ticker_timestamp,
        "amount": 0.0,
        "type": "ticker",
        "side": "",
        "source": "INDODAX public ticker",
        "observation_type": "TICKER",
    } if last_price > 0 else None
    points = [*trade_points, ticker_point] if ticker_point else trade_points
    return {
        "available": True,
        "pair": pair,
        "base_currency": pair.split("_")[0].upper(),
        "quote_currency": pair.split("_")[1].upper(),
        "currency": "IDR" if pair.endswith("_idr") else pair.split("_")[1].upper(),
        "currency_symbol": "Rp" if pair.endswith("_idr") else pair.split("_")[1].upper(),
        "last": float(t.get("last") or 0),
        "buy": float(t.get("buy") or 0),
        "sell": float(t.get("sell") or 0),
        "high": float(t.get("high") or 0),
        "low": float(t.get("low") or 0),
        "volume": float(t.get("vol_idr") or t.get("vol") or 0),
        "recent_move": _recent_trade_move(points),
        "recent_move_label": "INDODAX public observations",
        "points": points,
        "source": "INDODAX public market data",
        "market_data_quality": "TRADE_STREAM_PLUS_TICKER" if trade_points else "TICKER_FALLBACK",
    }


async def _market_insights(scope):
    data = await _public_indodax("/tickers")
    raw = data.get("tickers", {}) if isinstance(data, dict) else {}
    items = []
    for pair, ticker in raw.items():
        if not pair.endswith("_idr") or not isinstance(ticker, dict):
            continue
        try:
            last = float(ticker.get("last") or 0)
            high = float(ticker.get("high") or 0)
            low = float(ticker.get("low") or 0)
            volume = float(ticker.get("vol_idr") or 0)
            if last <= 0:
                continue
            width = high - low
            pos = ((last - low) / width * 100.0) if width > 0 else 50.0
            signal = "NEAR 24H HIGH" if pos >= 80 else "NEAR 24H LOW" if pos <= 20 else "MID 24H RANGE"
            items.append({"pair": pair.upper().replace("_", "/"), "last": last, "volume_idr": volume, "high": high, "low": low, "range_position": round(pos, 1), "signal": signal, "scalping_supported": pair.lower() in SCALPING_PAIRS})
        except (TypeError, ValueError, ZeroDivisionError):
            continue
    items.sort(key=lambda x: x["volume_idr"], reverse=True)
    return {"items": items[:20], "total_idr_pairs": len(items), "scalping_pairs": [item["pair"] for item in items if item["scalping_supported"]], "source": "INDODAX public ticker", "note": "Market-data watchlist only; it does not place trades."}


async def _serve_assets(scope, send):
    env = scope.get("env")
    if env is None or getattr(env, "ASSETS", None) is None:
        return False
    try:
        path = scope.get("path", "/") or "/"
        raw_query = scope.get("query_string", b"")
        query = raw_query.decode("latin-1") if isinstance(raw_query, (bytes, bytearray)) else str(raw_query or "")
        response = await env.ASSETS.fetch("https://assets.local" + path + (f"?{query}" if query else ""))
        body = await response.bytes()
        headers = [(str(k).lower().encode(), str(v).encode()) for k, v in dict(response.headers).items()]
        await _send(send, int(response.status), headers, body)
        return True
    except Exception:
        return False


def _as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


async def _dashboard_status(scope):
    configured = bool(_env(scope, "SUPABASE_URL").strip() and _env(scope, "SUPABASE_SERVICE_ROLE_KEY").strip())
    connected = await _supabase_probe(scope) if configured else False
    decisions = await _supabase_request(scope, "/rest/v1/decisions?select=action,created_at&order=created_at.desc&limit=500") or []
    buys = sum(1 for row in decisions if str(row.get("action", "")).upper() == "BUY")
    sells = sum(1 for row in decisions if str(row.get("action", "")).upper() == "SELL")
    holds = sum(1 for row in decisions if str(row.get("action", "")).upper() == "HOLD")
    return {
        "portfolio_value": PAPER_INITIAL_BALANCE,
        "balance": PAPER_INITIAL_BALANCE,
        "daily_pnl": 0.0,
        "daily_trades": 0,
        "active_positions": 0,
        "max_open_positions": MAX_OPEN_POSITIONS,
        "total_trades": 0,
        "currency": "IDR",
        "currency_symbol": "Rp",
        "mode": "paper",
        "bot_enabled": False,
        "cycle_running": False,
        "cycles_today": 0,
        "last_cycle_at": None,
        "runtime_hours": 0.0,
        "decision_counts": {"BUY": buys, "SELL": sells, "HOLD": holds},
        "database": {"configured": configured, "connected": connected, "status": "connected" if connected else ("not_configured" if not configured else "unreachable")},
        "market_data": {"source": "INDODAX public market data", "available": True},
        "safety": {"mode": "paper", "real_trading_locked": True, "bot_enabled": False},
    }


async def _dashboard_positions(scope):
    rows = await _supabase_request(scope, "/rest/v1/trades?status=eq.OPEN&select=symbol,action,entry_price,price,quantity,pnl,confidence,created_at&order=created_at.desc")
    positions = []
    for row in rows or []:
        positions.append({"symbol": row.get("symbol", ""), "side": row.get("action", ""), "quantity": _as_float(row.get("quantity")), "entry_price": _as_float(row.get("entry_price") or row.get("price")), "unrealized_pnl": _as_float(row.get("pnl")), "currency": "IDR"})
    return {"positions": positions, "currency": "IDR", "currency_symbol": "Rp"}


async def _dashboard_performance(scope):
    rows = await _supabase_request(scope, "/rest/v1/trades?select=pnl,status") or []
    closed = [row for row in rows if row.get("status") == "CLOSED"]
    pnl = sum(_as_float(row.get("pnl")) for row in closed)
    wins = sum(1 for row in closed if _as_float(row.get("pnl")) > 0)
    return {"performance": {"total_pnl": pnl, "win_rate": (wins / len(closed)) if closed else 0.0, "closed_trades": len(closed), "currency": "IDR", "currency_symbol": "Rp"}}


_DECISION_FIELDS = "id,symbol,action,raw_action,candidate_action,confidence,reasoning,agent_votes,market_scores,confidence_components,consensus_action,consensus_score,position_size,stop_loss,take_profit,engine_source,engine_warning,cycle_status,cycle_id,session_id,cycle_number,market_timestamp,market_source,move_1m_pct,move_5m_pct,move_15m_pct,move_30m_pct,pulse_status,current_pulse_status,pulse_net_move_30m_pct,pulse_segments,agent_details,hold_analysis,execution_gate,market_snapshot,persistence_status,library_version,library_alerts,candle_analysis,knowledge_topics,market_regime,current_pulse_status,data_quality_status,candidate_action,execution_status,risk_rejection_reason,consecutive_hold_count,no_edge_count,agent_run_count,created_at"


async def _dashboard_recent_decision(scope):
    rows = await _supabase_request(scope, f"/rest/v1/decisions?select={_DECISION_FIELDS}&order=created_at.desc&limit=1")
    if not rows:
        return {"decision": None}
    row = rows[0]
    return {"decision": row}


async def _dashboard_history(scope):
    limit = max(1, min(100, int(_as_float(_query_value(scope, "limit", "30"), 30))))
    rows = await _supabase_request(scope, f"/rest/v1/paper_history?select={_DECISION_FIELDS}&order=created_at.desc&limit={limit}") or []
    return {"history": rows, "count": len(rows), "market_source": "INDODAX public market data"}


async def _dashboard_agents(scope):
    rows = await _supabase_request(scope, f"/rest/v1/decisions?select=cycle_id,cycle_number,market_timestamp,market_source,pulse_status,current_pulse_status,move_1m_pct,move_5m_pct,move_15m_pct,move_30m_pct,candidate_action,action,confidence,execution_status,execution_gate,agent_details&order=created_at.desc&limit=1") or []
    if not rows:
        return {"agents": [], "message": "No agent cycle has been persisted yet."}
    row = rows[0]
    details = row.get("agent_details") or {}
    agents = []
    for name, detail in details.items():
        if not isinstance(detail, dict):
            detail = {"value": detail}
        agents.append({
            "name": name,
            "status": detail.get("status", "UNKNOWN"),
            "direction": detail.get("direction", "NEUTRAL"),
            "score": detail.get("score"),
            "confidence": detail.get("confidence"),
            "timeframe": detail.get("timeframe"),
            "data_timestamp": detail.get("data_timestamp") or row.get("market_timestamp"),
            "data_age_seconds": detail.get("data_age_seconds"),
            "summary": detail.get("summary", ""),
            "evidence": detail.get("evidence") or [],
            "recommendations": detail.get("recommendations") or [],
            "warnings": detail.get("warnings") or [],
            "raw": detail.get("raw") or detail,
        })
    return {"cycle_id": row.get("cycle_id"), "cycle_number": row.get("cycle_number"), "market_timestamp": row.get("market_timestamp"), "market_source": row.get("market_source"), "pulse_status": row.get("pulse_status"), "current_pulse_status": row.get("current_pulse_status"), "moves": {"1m": row.get("move_1m_pct"), "5m": row.get("move_5m_pct"), "15m": row.get("move_15m_pct"), "30m": row.get("move_30m_pct")}, "candidate_action": row.get("candidate_action"), "action": row.get("action"), "confidence": row.get("confidence"), "execution_status": row.get("execution_status"), "execution_gate": row.get("execution_gate"), "agents": agents}


async def app(scope, receive, send):
    if scope.get("type") != "http":
        return
    method = scope.get("method", "GET").upper()
    path = scope.get("path", "/")
    if method == "OPTIONS":
        await _send(send, 204, [], b"")
        return
    if not path.startswith("/api/"):
        if await _serve_assets(scope, send):
            return
        await _json_response(send, 404, {"detail": "Not found"})
        return
    if method == "GET" and path == "/api/health":
        await _json_response(send, 200, {"status": "healthy", "runtime": "cloudflare-python-worker"})
        return
    if method == "GET" and path == "/api/ready":
        configured = all(_env(scope, name).strip() for name in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "JWT_SECRET_KEY", "ADMIN_USERNAME", "ADMIN_PASSWORD"))
        supabase = await _supabase_probe(scope) if configured else False
        await _json_response(send, 200, {"status": "ready" if configured and supabase else "degraded", "supabase": supabase, "secrets_configured": configured, "runtime": "cloudflare-python-worker"})
        return
    if path == "/api/auth/login" and method == "POST":
        configured_user = _env(scope, "ADMIN_USERNAME").strip()
        configured_password = _env(scope, "ADMIN_PASSWORD")
        if not configured_user or not configured_password:
            await _json_response(send, 503, {"detail": "Dashboard authentication is not configured"})
            return
        try:
            body = json.loads((await _read_body(receive)).decode("utf-8"))
            username = str(body.get("username", ""))
            password = str(body.get("password", ""))
        except Exception:
            await _json_response(send, 400, {"detail": "Invalid JSON request body"})
            return
        try:
            secret = _secret(scope)
            supplied = _hmac_sha256(secret, password)
            expected = _hmac_sha256(secret, configured_password)
        except RuntimeError as exc:
            await _json_response(send, 503, {"detail": str(exc)})
            return
        if username != configured_user or not hmac.compare_digest(supplied, expected):
            await _json_response(send, 401, {"detail": "Incorrect username or password"})
            return
        await _json_response(send, 200, {"access_token": _make_token(scope, configured_user), "token_type": "bearer", "expires_in": 1800, "username": configured_user})
        return
    if path == "/api/auth/logout" and method == "POST":
        if not await _require_user(scope):
            await _json_response(send, 401, {"detail": "Invalid or expired token"})
            return
        await _json_response(send, 200, {"message": "Logged out successfully", "status": "success"})
        return
    if path == "/api/auth/verify" and method == "GET":
        payload = await _require_user(scope)
        if not payload:
            await _json_response(send, 401, {"detail": "Invalid or expired token"})
            return
        await _json_response(send, 200, {"username": payload["sub"], "is_authenticated": True})
        return
    if method == "GET" and path in {"/api/market/overview", "/api/market/data"}:
        if not await _require_user(scope):
            await _json_response(send, 401, {"detail": "Invalid or expired token"})
            return
        await _json_response(send, 200, await _market_overview(scope))
        return
    if method == "GET" and path == "/api/market/insights":
        if not await _require_user(scope):
            await _json_response(send, 401, {"detail": "Invalid or expired token"})
            return
        await _json_response(send, 200, await _market_insights(scope))
        return
    dashboard_routes = {
        "/api/dashboard/status": _dashboard_status,
        "/api/dashboard/positions": _dashboard_positions,
        "/api/dashboard/performance": _dashboard_performance,
        "/api/dashboard/recent-decision": _dashboard_recent_decision,
        "/api/dashboard/history": _dashboard_history,
        "/api/dashboard/agents": _dashboard_agents,
    }
    if method == "GET" and path in dashboard_routes:
        if not await _require_user(scope):
            await _json_response(send, 401, {"detail": "Invalid or expired token"})
            return
        await _json_response(send, 200, await dashboard_routes[path](scope))
        return
    if path == "/api/dashboard/analyze" and method == "POST":
        if not await _require_user(scope):
            await _json_response(send, 401, {"detail": "Invalid or expired token"})
            return
        await _json_response(send, 409, {"detail": "AI analysis is disabled while BOT is OFF. An explicit start trigger is required.", "bot_enabled": False, "cycle_running": False})
        return
    if path == "/api/bot/status" and method == "GET":
        if not await _require_user(scope):
            await _json_response(send, 401, {"detail": "Invalid or expired token"})
            return
        await _json_response(send, 200, {"enabled": False, "mode": "paper", "runtime": "cloudflare-python-worker", "cycle_running": False, "cycles_today": 0, "last_cycle_at": None, "message": "Trading is disabled. An explicit start trigger is required before any paper cycle can run."})
        return
    if path in {"/api/bot/start", "/api/bot/stop"} and method == "POST":
        if not await _require_user(scope):
            await _json_response(send, 401, {"detail": "Invalid or expired token"})
            return
        await _json_response(send, 409, {"detail": "Bot control is provided by worker_entry.py.", "enabled": False, "cycle_running": False})
        return
    await _json_response(send, 404, {"detail": "API route not found"})


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        return await asgi.fetch(app, request, self.env)
