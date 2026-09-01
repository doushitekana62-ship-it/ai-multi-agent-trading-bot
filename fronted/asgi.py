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

from urllib.parse import parse_qs, urlparse

from workers import Response


async def fetch(app, request, env):
    """Handle the small set of legacy API routes without the ASGI package."""
    # Import lazily so cf_worker can continue importing this compatibility
    # module without creating a circular import at module initialization.
    import cf_worker

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
