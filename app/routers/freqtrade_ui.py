from __future__ import annotations

import asyncio
import base64
import binascii
import json
import secrets
from urllib.parse import parse_qsl, urlencode

import httpx
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from websockets.asyncio.client import connect as ws_connect

from ..config import settings
from ..freqtrade_runtime import runtime

router = APIRouter()

_PROXY_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"]
_HOP_BY_HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade", "host", "content-length", "origin"}
_ENGINE_BOOT_TIMEOUT = 15.0


def _upstream_url(path: str) -> str:
    return f"http://127.0.0.1:{settings.freqtrade_api_port}/api/v1/{path}"


def _forward_headers(request: Request) -> dict[str, str]:
    return {key: value for key, value in request.headers.items() if key.lower() not in _HOP_BY_HOP_HEADERS}


def _basic_header() -> str:
    raw = f"{settings.freqtrade_api_username}:{runtime.api_password}".encode("utf-8")
    return f"Basic {base64.b64encode(raw).decode('ascii')}"


def _login_valid(request: Request) -> bool:
    if not settings.dashboard_token:
        return False
    value = request.headers.get("authorization", "")
    if not value.lower().startswith("basic "):
        return False
    try:
        decoded = base64.b64decode(value[6:].strip()).decode("utf-8")
        username, password = decoded.split(":", 1)
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return False
    return username == settings.freqtrade_api_username and secrets.compare_digest(password, settings.dashboard_token)


def _dashboard_bearer(request: Request) -> bool:
    value = request.headers.get("authorization", "")
    prefix = "Bearer "
    return bool(settings.dashboard_token and value.startswith(prefix) and secrets.compare_digest(value[len(prefix):], settings.dashboard_token))


async def _ensure_api_ready() -> None:
    try:
        # Boot only starts the worker thread and returns quickly. Do not call
        # runtime.start() here because that method synchronously waits for the
        # embedded Freqtrade API and can hold an HTTP request for 30 seconds.
        if not runtime.running:
            await asyncio.to_thread(runtime.boot)
        await runtime.wait_for_api(timeout=_ENGINE_BOOT_TIMEOUT)
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc


@router.api_route("/api/v1/ping", methods=["GET", "HEAD"])
async def freqtrade_ping() -> Response:
    try:
        await _ensure_api_ready()
    except RuntimeError as exc:
        return JSONResponse({"status": "offline", "detail": str(exc), "runtime": runtime.status()}, status_code=503)
    return JSONResponse({"status": "pong"})


@router.api_route("/api/v1/{path:path}", methods=_PROXY_METHODS)
async def freqtrade_api_proxy(path: str, request: Request) -> Response:
    if path == "token/login":
        if not _login_valid(request):
            return JSONResponse({"detail": "Invalid username or dashboard token"}, status_code=401)
        return JSONResponse({"access_token": settings.dashboard_token, "refresh_token": settings.dashboard_token, "token_type": "bearer"})

    if path == "token/refresh":
        if not _dashboard_bearer(request):
            return JSONResponse({"detail": "Invalid dashboard session"}, status_code=401)
        return JSONResponse({"access_token": settings.dashboard_token, "refresh_token": settings.dashboard_token, "token_type": "bearer"})

    try:
        await _ensure_api_ready()
    except RuntimeError as exc:
        return JSONResponse({"detail": str(exc), "runtime": runtime.status()}, status_code=503)

    body = await request.body()
    headers = _forward_headers(request)
    if _dashboard_bearer(request):
        headers["authorization"] = _basic_header()

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            upstream = await client.request(request.method, _upstream_url(path), params=list(request.query_params.multi_items()), headers=headers, content=body)
    except httpx.HTTPError as exc:
        return JSONResponse({"detail": f"Freqtrade API unavailable: {exc}"}, status_code=503)

    response_headers = {key: value for key, value in upstream.headers.items() if key.lower() not in _HOP_BY_HOP_HEADERS}
    return Response(content=upstream.content, status_code=upstream.status_code, headers=response_headers)


def _internal_ws_url(websocket: WebSocket) -> str:
    raw_query = websocket.scope.get("query_string", b"").decode("latin-1")
    params = parse_qsl(raw_query, keep_blank_values=True)
    rewritten = []
    for key, value in params:
        if key == "token":
            rewritten.append((key, runtime.api_password))
        else:
            rewritten.append((key, value))
    query = urlencode(rewritten)
    upstream_url = f"ws://127.0.0.1:{settings.freqtrade_api_port}/api/v1/message/ws"
    return f"{upstream_url}?{query}" if query else upstream_url


@router.websocket("/api/v1/message/ws")
async def freqtrade_websocket_proxy(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        await _ensure_api_ready()
        async with ws_connect(_internal_ws_url(websocket), open_timeout=30, close_timeout=5, additional_headers={"Authorization": _basic_header()}) as upstream:
            async def client_to_upstream() -> None:
                while True:
                    message = await websocket.receive()
                    if message.get("type") == "websocket.disconnect":
                        break
                    if message.get("text") is not None:
                        await upstream.send(message["text"])
                    elif message.get("bytes") is not None:
                        await upstream.send(message["bytes"])

            async def upstream_to_client() -> None:
                async for message in upstream:
                    if isinstance(message, bytes):
                        await websocket.send_bytes(message)
                    else:
                        await websocket.send_text(message)

            forward_client = asyncio.create_task(client_to_upstream())
            forward_server = asyncio.create_task(upstream_to_client())
            done, pending = await asyncio.wait({forward_client, forward_server}, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            for task in done:
                task.result()
    except (WebSocketDisconnect, Exception):
        try:
            await websocket.close()
        except Exception:
            pass
