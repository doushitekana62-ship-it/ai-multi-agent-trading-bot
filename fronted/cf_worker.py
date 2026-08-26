import base64
import hashlib
import hmac
import json
import time
from urllib.parse import urlparse

import asgi
from workers import WorkerEntrypoint
from js import TextEncoder, crypto, fetch
from pyodide.ffi import to_js


JSON_HEADERS = [(b"content-type", b"application/json; charset=utf-8")]


def _json_bytes(value):
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _env(scope, name, default=""):
    return str(getattr(scope.get("env"), name, default) or default)


def _secret(scope) -> str:
    secret = _env(scope, "JWT_SECRET_KEY")
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be at least 32 characters")
    return secret


async def _hmac_sha256(secret: str, message: str) -> bytes:
    encoder = TextEncoder.new()
    key_data = encoder.encode(secret)
    message_data = encoder.encode(message)
    key = await crypto.subtle.importKey(
        "raw", key_data, to_js({"name": "HMAC", "hash": "SHA-256"}), False, ["sign"]
    )
    result = await crypto.subtle.sign("HMAC", key, message_data)
    return bytes(result.to_py())


async def _make_token(scope, username: str) -> str:
    now = int(time.time())
    header = _b64url(_json_bytes({"alg": "HS256", "typ": "JWT"}))
    payload = _b64url(_json_bytes({"sub": username, "iat": now, "exp": now + 1800, "type": "access"}))
    signing_input = f"{header}.{payload}"
    signature = await _hmac_sha256(_secret(scope), signing_input)
    return f"{signing_input}.{_b64url(signature)}"


async def _verify_token(scope, token: str):
    try:
        header, payload, signature = token.split(".", 2)
        if json.loads(_b64url_decode(header)).get("alg") != "HS256":
            return None
        data = json.loads(_b64url_decode(payload))
        if int(data.get("exp", 0)) <= int(time.time()):
            return None
        expected = await _hmac_sha256(_secret(scope), f"{header}.{payload}")
        if not hmac.compare_digest(expected, _b64url_decode(signature)):
            return None
        return data
    except Exception:
        return None


def _authorization(scope) -> str:
    for key, value in scope.get("headers", []):
        if key.lower() == b"authorization":
            return value.decode("latin-1")
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
    return await _verify_token(scope, value[7:].strip())


async def _supabase_probe(scope) -> bool:
    url = _env(scope, "SUPABASE_URL").rstrip("/")
    key = _env(scope, "SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return False
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    try:
        options = to_js({"method": "GET", "headers": {"apikey": key, "Authorization": f"Bearer {key}"}})
        response = await fetch(f"{url}/rest/v1/", options)
        return int(response.status) < 500
    except Exception:
        return False


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


async def app(scope, receive, send):
    if scope.get("type") != "http":
        return

    method = scope.get("method", "GET").upper()
    path = scope.get("path", "/")

    if method == "OPTIONS":
        await _send(send, 204, [], b"")
        return

    # The Worker is intentionally API-only. The root and all non-API routes
    # are served by Cloudflare Static Assets/React SPA. Visiting the site
    # never imports or starts the trading engine.
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
        configured_user = _env(scope, "ADMIN_USERNAME")
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
        supplied = await _hmac_sha256(_secret(scope), password)
        expected = await _hmac_sha256(_secret(scope), configured_password)
        if username != configured_user or not hmac.compare_digest(supplied, expected):
            await _json_response(send, 401, {"detail": "Incorrect username or password"})
            return
        token = await _make_token(scope, configured_user)
        await _json_response(send, 200, {
            "access_token": token, "token_type": "bearer", "expires_in": 1800, "username": configured_user
        })
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

    # Safety gate: this endpoint reports the current safe state only. No
    # trading engine is imported, scheduled, or started by the Worker.
    if path == "/api/bot/status" and method == "GET":
        if not await _require_user(scope):
            await _json_response(send, 401, {"detail": "Invalid or expired token"})
            return
        await _json_response(send, 200, {
            "enabled": False,
            "mode": "paper",
            "runtime": "cloudflare-python-worker",
            "cycle_running": False,
            "message": "Trading is disabled. An explicit start trigger is required before any paper cycle can run.",
        })
        return

    await _json_response(send, 404, {"detail": "API route not found"})


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        return await asgi.fetch(app, request, self.env)
