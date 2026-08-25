import base64
import hashlib
import hmac
import json
import time
from urllib.parse import urlparse

import asgi
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from workers import WorkerEntrypoint
from js import TextEncoder, crypto, fetch
from pyodide.ffi import to_js


app = FastAPI(title="AI Multi-Agent Trading Bot Cloudflare API", version="1.0.0")


class LoginRequest(BaseModel):
    username: str
    password: str


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _secret(env) -> str:
    secret = str(getattr(env, "JWT_SECRET_KEY", "") or "")
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be at least 32 characters")
    return secret


async def _hmac_sha256(secret: str, message: str) -> bytes:
    encoder = TextEncoder.new()
    key_data = encoder.encode(secret)
    message_data = encoder.encode(message)
    key = await crypto.subtle.importKey(
        "raw",
        key_data,
        to_js({"name": "HMAC", "hash": "SHA-256"}),
        False,
        ["sign"],
    )
    result = await crypto.subtle.sign("HMAC", key, message_data)
    return bytes(result.to_py())


async def _password_digest(secret: str, password: str) -> bytes:
    # The password itself is already stored as a protected Worker secret.
    # HMAC prevents a timing-sensitive direct string comparison and avoids
    # bcrypt/native dependencies that are not suitable for Python Workers.
    return await _hmac_sha256(secret, password)


async def _make_token(env, username: str) -> str:
    now = int(time.time())
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url(
        json.dumps(
            {"sub": username, "iat": now, "exp": now + 1800, "type": "access"},
            separators=(",", ":"),
        ).encode()
    )
    signing_input = f"{header}.{payload}"
    signature = await _hmac_sha256(_secret(env), signing_input)
    return f"{signing_input}.{_b64url(signature)}"


async def _verify_token(env, token: str):
    try:
        header, payload, signature = token.split(".", 2)
        if json.loads(_b64url_decode(header)).get("alg") != "HS256":
            return None
        data = json.loads(_b64url_decode(payload))
        if int(data.get("exp", 0)) <= int(time.time()):
            return None
        expected = await _hmac_sha256(_secret(env), f"{header}.{payload}")
        supplied = _b64url_decode(signature)
        if not hmac.compare_digest(expected, supplied):
            return None
        return data
    except Exception:
        return None


def _bearer(request: Request) -> str | None:
    value = request.headers.get("authorization", "")
    if not value.lower().startswith("bearer "):
        return None
    return value[7:].strip() or None


async def _require_user(request: Request):
    env = request.scope["env"]
    token = _bearer(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    payload = await _verify_token(env, token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


async def _supabase_probe(env) -> bool:
    url = str(getattr(env, "SUPABASE_URL", "") or "").rstrip("/")
    key = str(getattr(env, "SUPABASE_SERVICE_ROLE_KEY", "") or "")
    if not url or not key:
        return False
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    try:
        options = to_js(
            {
                "method": "GET",
                "headers": {
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                },
            }
        )
        response = await fetch(f"{url}/rest/v1/", options)
        return int(response.status) < 500
    except Exception:
        return False


@app.get("/")
async def root():
    return {"status": "online", "service": "AI Multi-Agent Trading Bot API", "runtime": "cloudflare-python-worker"}


@app.get("/health")
async def health():
    return {"status": "healthy", "runtime": "cloudflare-python-worker"}


@app.get("/api/health")
async def api_health():
    return {"status": "healthy", "runtime": "cloudflare-python-worker"}


@app.get("/ready")
async def ready(request: Request):
    env = request.scope["env"]
    configured = all(
        bool(str(getattr(env, name, "") or "").strip())
        for name in (
            "SUPABASE_URL",
            "SUPABASE_SERVICE_ROLE_KEY",
            "JWT_SECRET_KEY",
            "ADMIN_USERNAME",
            "ADMIN_PASSWORD",
        )
    )
    supabase = await _supabase_probe(env) if configured else False
    return {
        "status": "ready" if configured and supabase else "degraded",
        "supabase": supabase,
        "secrets_configured": configured,
        "runtime": "cloudflare-python-worker",
    }


@app.get("/api/ready")
async def api_ready(request: Request):
    return await ready(request)


@app.post("/api/auth/login")
async def login(request: Request, body: LoginRequest):
    env = request.scope["env"]
    configured_user = str(getattr(env, "ADMIN_USERNAME", "") or "")
    configured_password = str(getattr(env, "ADMIN_PASSWORD", "") or "")
    if not configured_user or not configured_password:
        raise HTTPException(status_code=503, detail="Dashboard authentication is not configured")

    secret = _secret(env)
    supplied_digest = await _password_digest(secret, body.password)
    expected_digest = await _password_digest(secret, configured_password)
    if body.username != configured_user or not hmac.compare_digest(supplied_digest, expected_digest):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = await _make_token(env, configured_user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 30,
        "username": configured_user,
    }


@app.post("/api/auth/logout")
async def logout(request: Request):
    await _require_user(request)
    return {"message": "Logged out successfully", "status": "success"}


@app.get("/api/auth/verify")
async def verify(request: Request):
    payload = await _require_user(request)
    return {"username": payload["sub"], "is_authenticated": True}


@app.get("/api/bot/status")
async def bot_status(request: Request):
    await _require_user(request)
    return {
        "enabled": False,
        "mode": "paper",
        "runtime": "cloudflare-python-worker",
        "message": "Trading runtime control is not enabled until persistent bot state is connected.",
    }


@app.options("/{path:path}")
async def options(path: str):
    return Response(status_code=204)


@app.get("/{path:path}")
async def frontend(path: str, request: Request):
    # API routes are resolved above. Everything else is served from the
    # React build through the Workers Static Assets binding.
    env = request.scope["env"]
    asset_url = f"https://assets.local/{path}"
    response = await env.ASSETS.fetch(asset_url)
    body = await response.bytes()
    headers = dict(response.headers)
    return Response(content=body, status_code=response.status, headers=headers)


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        return await asgi.fetch(app, request, self.env)
