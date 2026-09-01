"""Legacy API compatibility adapter for the Cloudflare Python Worker.

The production Worker now handles its authoritative API routes directly.
This module intentionally does not import ``workers.asgi``: that submodule is
not part of the current Workers runtime SDK surface and importing it caused the
production Worker to fail during module initialization.

Only the legacy market/health routes that still fall through from
``worker_entry_api.py`` are handled here. Static assets are served by the
Cloudflare Assets binding and never require this adapter.
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
    # Import lazily so cf_worker can continue importing this compatibility
    # module without creating a circular import at module initialization.
    import cf_worker

    # Patch the shared market-data adapter once this Worker instance is active.
    # This keeps dashboard polling, paper cycles and market insights on the same
    # uncached INDODAX source without modifying the trading/risk pipeline.
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
