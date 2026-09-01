"""Legacy API compatibility adapter for the Cloudflare Python Worker.

The production Worker handles its authoritative API routes directly. This
module exists only for the small legacy market/health routes that fall through
from ``worker_entry_api.py``. It deliberately does not call the runtime ASGI
``fetch(app, request, env)`` helper; the supported Workers ASGI integration is
an entrypoint pattern, and the old direct helper was an unnecessary runtime
failure point for this custom router.

Static assets are served by the Cloudflare Assets binding and do not require
this adapter.
"""
from __future__ import annotations

import json
import time
from urllib.parse import parse_qs, urlparse

from js import fetch as js_fetch
from pyodide.ffi import to_js
from workers import Response


async def _fresh_public_indodax(path):
    """Bypass edge cache so every dashboard poll sees the current ticker."""
    try:
        separator = "&" if "?" in path else "?"
        url = f"https://indodax.com/api{path}{separator}_live={int(time.time() * 1000)}"
        response = await js_fetch(
            url,
            to_js(
                {
                    "method": "GET",
                    "cache": "no-store",
                    "headers": {
                        "Accept": "application/json",
                        "Cache-Control": "no-cache",
                        "Pragma": "no-cache",
                    },
                }
            ),
        )
        if int(response.status) >= 400:
            return None
        return json.loads(await response.text())
    except Exception:
        return None


async def fetch(app, request, env):
    """Handle the small set of legacy API routes without the ASGI package."""
    # Import lazily so cf_worker can continue importing this module without a
    # circular import at module initialization.
    import cf_worker

    # Keep all market consumers on the same uncached INDODAX source after the
    # first live market request in a Worker isolate.
    cf_worker._public_indodax = _fresh_public_indodax

    parsed = urlparse(request.url)
    path = parsed.path
    query = parse_qs(parsed.query)
    pair = query.get("pair", ["btc_idr"])[0]
    scope = {"env": env, "query_string": f"pair={pair}".encode("latin-1")}

    if request.method == "OPTIONS":
        return Response("", status=204)

    if request.method == "GET" and path == "/api/health":
        return Response.json({"status": "healthy", "runtime": "cloudflare-python-worker"})

    if request.method == "GET" and path == "/api/ready":
        configured = all(
            str(getattr(env, name, "") or "").strip()
            for name in (
                "SUPABASE_URL",
                "SUPABASE_SERVICE_ROLE_KEY",
                "JWT_SECRET_KEY",
                "ADMIN_USERNAME",
                "ADMIN_PASSWORD",
            )
        )
        supabase = await cf_worker._supabase_probe(scope) if configured else False
        return Response.json(
            {
                "status": "ready" if configured and supabase else "degraded",
                "supabase": bool(supabase),
                "secrets_configured": configured,
                "runtime": "cloudflare-python-worker",
            }
        )

    if request.method == "GET" and path in {"/api/market/overview", "/api/market/data"}:
        data = await cf_worker._market_overview(scope)
        return Response.json(data)

    if request.method == "GET" and path == "/api/market/insights":
        data = await cf_worker._market_insights(scope)
        return Response.json(data)

    return Response.json({"detail": "API route not found"}, status=404)


entrypoint = None

__all__ = ["fetch", "entrypoint"]
