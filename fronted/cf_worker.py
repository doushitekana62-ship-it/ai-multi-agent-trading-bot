import base64
import hashlib
import hmac
import json
import time
from urllib.parse import urlparse

import asgi
from workers import WorkerEntrypoint
from js import fetch
from pyodide.ffi import to_js


JSON_HEADERS = [(b"content-type", b"application/json; charset=utf-8")]
PAPER_INITIAL_BALANCE = 10_000_000.0
MAX_OPEN_POSITIONS = 5


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
    signature = _hmac_sha256(_secret(scope), signing_input)
    return f"{signing_input}.{_b64url(signature)}"


def _verify_token(scope, token: str):
    try:
        header, payload, signature = token.split(".", 2)
        if json.loads(_b64url_decode(header)).get("alg") != "HS256":
            return None
        data = json.loads(_b64url_decode(payload))
        if int(data.get("exp", 0)) <= int(time.time()):
            return None
        expected = _hmac_sha256(_secret(scope), f"{header}.{payload}")
        if not hmac.compare_digest(expected, _b64url_decode(signature)):
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
        options = to_js({
            "method": method,
            "headers": {
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Accept": "application/json",
            },
        })
        response = await fetch(f"{url}{path}", options)
        if int(response.status) >= 400:
            return None
        return json.loads(await response.text())
    except Exception:
        return None


async def _supabase_probe(scope) -> bool:
    return (await _supabase_request(scope, "/rest/v1/")) is not None


async def _serve_assets(scope, send):
    env = scope.get("env")
    if env is None or getattr(env, "ASSETS", None) is None:
        return False
    try:
        path = scope.get("path", "/") or "/"
        query = scope.get("query_string", b"").decode("latin-1")
        asset_url = "https://assets.local" + path + (f"?{query}" if query else "")
        response = await env.ASSETS.fetch(asset_url)
        body = await response.bytes()
        headers = [(str(k).lower().encode(), str(v).encode()) for k, v in dict(response.headers).items()]
        await _send(send, int(response.status), headers, body)
        return True
    except Exception:
        return False


async def _dashboard_status(scope):
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
    }


async def _dashboard_positions(scope):
    rows = await _supabase_request(
        scope,
        "/rest/v1/trades?status=eq.OPEN&select=symbol,action,entry_price,price,quantity,pnl,confidence,created_at&order=created_at.desc",
    )
    positions = []
    for row in rows or []:
        positions.append({
            "symbol": row.get("symbol", ""),
            "side": row.get("action", ""),
            "quantity": float(row.get("quantity") or 0),
            "entry_price": float(row.get("entry_price") or row.get("price") or 0),
            "unrealized_pnl": float(row.get("pnl") or 0),
            "currency": "IDR",
        })
    return {"positions": positions, "currency": "IDR", "currency_symbol": "Rp"}


async def _dashboard_performance(scope):
    rows = await _supabase_request(scope, "/rest/v1/trades?select=pnl,status") or []
    closed = [row for row in rows if row.get("status") == "CLOSED"]
    pnl = sum(float(row.get("pnl") or 0) for row in closed)
    wins = sum(1 for row in closed if float(row.get("pnl") or 0) > 0)
    return {
        "performance": {
            "total_pnl": pnl,
            "win_rate": (wins / len(closed)) if closed else 0.0,
            "closed_trades": len(closed),
            "currency": "IDR",
            "currency_symbol": "Rp",
        }
    }


async def _dashboard_recent_decision(scope):
    rows = await _supabase_request(
        scope,
        "/rest/v1/decisions?select=id,symbol,action,confidence,reasoning,agent_votes,created_at&order=created_at.desc&limit=1",
    )
    if not rows:
        return {"decision": None}
    row = rows[0]
    return {"decision": {
        "id": row.get("id"),
        "symbol": row.get("symbol"),
        "action": row.get("action", "HOLD"),
        "confidence": float(row.get("confidence") or 0) / 100.0,
        "reasoning": row.get("reasoning"),
        "votes": row.get("agent_votes") or {},
        "created_at": row.get("created_at"),
    }}


async def _dashboard_agents(scope):
    return {"agents": [
        {"name": "Sentiment Agent", "status": "idle", "description": "Waiting for explicit bot start."},
        {"name": "Technical Agent", "status": "idle", "description": "Waiting for explicit bot start."},
        {"name": "Decision Agent", "status": "idle", "description": "Waiting for explicit bot start."},
        {"name": "Forecast Agent", "status": "idle", "description": "Waiting for explicit bot start."},
        {"name": "Reflector Agent", "status": "idle", "description": "Waiting for explicit bot start."},
    ]}


async def app(scope, receive, send):
    if scope.get("type") != "http":
        return

    method = scope.get("method", "GET").upper()
    path = scope.get("path", "/")

    if method == "OPTIONS":
        await _send(send, 204, [], b"")
        return

    # Non-API routes are always static assets. Visiting or refreshing the site
    # never imports, schedules, or starts the trading engine.
    if not path.startswith("/api/"):
        if await _serve_assets(scope, send):
            return
        await _json_response(send, 404, {"detail": "Not found"})
        return

    if method == "GET" and path == "/api/health":
        await _json_response(send, 200, {"status": "healthy", "runtime": "cloudflare-python-worker"})
        return

    if method == "GET" and path == "/api/ready":
        configured = all(_env(scope, name).strip() for name in (
            "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "JWT_SECRET_KEY", "ADMIN_USERNAME", "ADMIN_PASSWORD"
        ))
        supabase = await _supabase_probe(scope) if configured else False
        await _json_response(send, 200, {
            "status": "ready" if configured and supabase else "degraded",
            "supabase": supabase,
            "secrets_configured": configured,
            "runtime": "cloudflare-python-worker",
        })
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
        token = _make_token(scope, configured_user)
        await _json_response(send, 200, {"access_token": token, "token_type": "bearer", "expires_in": 1800, "username": configured_user})
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

    # Read-only dashboard API. All endpoints are authenticated and cannot
    # start a cycle. This fixes dashboard 404s without creating hidden work.
    dashboard_routes = {
        "/api/dashboard/status": _dashboard_status,
        "/api/dashboard/positions": _dashboard_positions,
        "/api/dashboard/performance": _dashboard_performance,
        "/api/dashboard/recent-decision": _dashboard_recent_decision,
        "/api/dashboard/agents": _dashboard_agents,
    }
    if method == "GET" and path in dashboard_routes:
        if not await _require_user(scope):
            await _json_response(send, 401, {"detail": "Invalid or expired token"})
            return
        payload = await dashboard_routes[path](scope)
        await _json_response(send, 200, payload)
        return

    if path == "/api/dashboard/analyze" and method == "POST":
        if not await _require_user(scope):
            await _json_response(send, 401, {"detail": "Invalid or expired token"})
            return
        await _json_response(send, 409, {
            "detail": "AI analysis is disabled while BOT is OFF. An explicit start trigger is required.",
            "bot_enabled": False,
            "cycle_running": False,
        })
        return

    # Safety gate: bot status is always OFF in this validation phase.
    if path == "/api/bot/status" and method == "GET":
        if not await _require_user(scope):
            await _json_response(send, 401, {"detail": "Invalid or expired token"})
            return
        await _json_response(send, 200, {
            "enabled": False,
            "mode": "paper",
            "runtime": "cloudflare-python-worker",
            "cycle_running": False,
            "cycles_today": 0,
            "last_cycle_at": None,
            "message": "Trading is disabled. An explicit start trigger is required before any paper cycle can run.",
        })
        return

    # Start/stop endpoints are deliberately not wired to the trading engine yet.
    # Returning 409 prevents accidental activation while keeping the safety gate explicit.
    if path in {"/api/bot/start", "/api/bot/stop"} and method == "POST":
        if not await _require_user(scope):
            await _json_response(send, 401, {"detail": "Invalid or expired token"})
            return
        await _json_response(send, 409, {
            "detail": "Bot control is locked until the persistent safety gate is implemented.",
            "enabled": False,
            "cycle_running": False,
        })
        return

    await _json_response(send, 404, {"detail": "API route not found"})


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        return await asgi.fetch(app, request, self.env)
