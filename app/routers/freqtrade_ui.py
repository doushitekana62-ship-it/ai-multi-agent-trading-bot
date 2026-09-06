from __future__ import annotations

import asyncio

import httpx
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from websockets.asyncio.client import connect as ws_connect

from ..config import settings
from ..freqtrade_runtime import runtime

router = APIRouter()


_PROXY_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"]
_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
    "origin",
}


def _upstream_url(path: str) -> str:
    return f"http://127.0.0.1:{settings.freqtrade_api_port}/api/v1/{path}"


def _forward_headers(request: Request) -> dict[str, str]:
    return {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in _HOP_BY_HOP_HEADERS
    }


async def _ensure_login_api_ready() -> bool:
    """Ensure Freqtrade's native API is booted, but do not start trading."""
    if not runtime.running:
        try:
            runtime.boot()
        except Exception:
            return False

    ping_url = f"http://127.0.0.1:{settings.freqtrade_api_port}/api/v1/ping"
    deadline = asyncio.get_running_loop().time() + 30.0
    async with httpx.AsyncClient(timeout=2.0) as client:
        while asyncio.get_running_loop().time() < deadline:
            if not runtime.running:
                return False
            try:
                response = await client.get(ping_url)
                if response.status_code == 200:
                    return True
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.5)
    return False


@router.api_route("/api/v1/{path:path}", methods=_PROXY_METHODS)
async def freqtrade_api_proxy(path: str, request: Request) -> Response:
    """Bridge the public FastAPI origin to Freqtrade's native REST API."""
    if path == "token/login" and not await _ensure_login_api_ready():
        return Response(
            content='{"detail":"Freqtrade API did not become ready for login"}',
            status_code=503,
            media_type="application/json",
        )

    body = await request.body()
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            upstream = await client.request(
                request.method,
                _upstream_url(path),
                params=list(request.query_params.multi_items()),
                headers=_forward_headers(request),
                content=body,
            )
    except httpx.HTTPError as exc:
        return Response(
            content=f'{{"detail":"Freqtrade API unavailable: {exc}"}}',
            status_code=503,
            media_type="application/json",
        )

    response_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() not in _HOP_BY_HOP_HEADERS
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
    )


@router.websocket("/api/v1/message/ws")
async def freqtrade_websocket_proxy(websocket: WebSocket) -> None:
    """Bridge FreqUI's realtime websocket to the embedded Freqtrade API."""
    await websocket.accept()
    query = websocket.scope.get("query_string", b"").decode("latin-1")
    upstream_url = f"ws://127.0.0.1:{settings.freqtrade_api_port}/api/v1/message/ws"
    if query:
        upstream_url = f"{upstream_url}?{query}"

    try:
        async with ws_connect(upstream_url, open_timeout=10, close_timeout=5) as upstream:
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
            done, pending = await asyncio.wait(
                {forward_client, forward_server},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            for task in done:
                task.result()
    except (WebSocketDisconnect, Exception):
        # FreqUI reconnects automatically after a websocket failure.
        try:
            await websocket.close()
        except Exception:
            pass
