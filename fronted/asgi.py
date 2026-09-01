"""Small Cloudflare compatibility router for market/health fall-through routes.

The production Worker entrypoint owns authenticated dashboard routes. This
module only handles the lightweight public market endpoints and static fall-
throughs, without invoking the legacy ASGI runtime helper.
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


def _clean_pair(value):
    allowed = {"btc_idr", "eth_idr", "usdt_idr", "xrp_idr", "doge_idr", "sol_idr", "beat_idr", "hype_idr", "ada_idr", "trx_idr", "shib_idr", "pepe_idr"}
    pair = (value or "btc_idr").strip().lower().replace("/", "_")
    return pair if pair in allowed else "btc_idr"


async def _light_market_overview(pair):
    """Return only ticker data; trade history is collected by paper observation.

    The old route downloaded and parsed up to 1,440 trades on every dashboard
    poll. That is unnecessary for the live UI and is expensive in Python
    Workers, especially on the 10 ms Free CPU budget.
    """
    pair = _clean_pair(pair)
    ticker = await _fresh_public_indodax(f"/{pair}/ticker")
    if not ticker or not isinstance(ticker.get("ticker"), dict):
        return {"available": False, "pair": pair, "currency": "IDR", "currency_symbol": "Rp", "source": "INDODAX public market data"}
    t = ticker["ticker"]
    last = float(t.get("last") or 0)
    now = int(time.time())
    point = {
        "tid": f"ticker:{pair}:{now}:{last}",
        "price": last,
        "timestamp": now,
        "amount": 0.0,
        "type": "ticker",
        "side": "",
        "source": "INDODAX public ticker",
        "observation_type": "TICKER",
    } if last > 0 else None
    return {
        "available": last > 0,
        "pair": pair,
        "base_currency": pair.split("_")[0].upper(),
        "quote_currency": pair.split("_")[1].upper(),
        "currency": "IDR" if pair.endswith("_idr") else pair.split("_")[1].upper(),
        "currency_symbol": "Rp" if pair.endswith("_idr") else pair.split("_")[1].upper(),
        "last": last,
        "buy": float(t.get("buy") or 0),
        "sell": float(t.get("sell") or 0),
        "high": float(t.get("high") or 0),
        "low": float(t.get("low") or 0),
        "volume": float(t.get("vol_idr") or t.get("vol") or 0),
        "recent_move": None,
        "recent_move_label": "INDODAX public ticker observations",
        "points": [point] if point else [],
        "source": "INDODAX public market data",
        "market_data_quality": "TICKER_POLL",
    }


import cf_worker as _cf_worker


async def fetch(app, request, env):
    """Handle lightweight legacy market/health routes."""
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
            for name in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "JWT_SECRET_KEY", "ADMIN_USERNAME", "ADMIN_PASSWORD")
        )
        supabase = await _cf_worker._supabase_probe(scope) if configured else False
        return Response.json({"status": "ready" if configured and supabase else "degraded", "supabase": bool(supabase), "secrets_configured": configured, "runtime": "cloudflare-python-worker"})

    if request.method == "GET" and path in {"/api/market/overview", "/api/market/data"}:
        return Response.json(await _light_market_overview(pair))

    if request.method == "GET" and path == "/api/market/insights":
        return Response.json(await _cf_worker._market_insights(scope))

    return Response.json({"detail": "API route not found"}, status=404)


entrypoint = None

__all__ = ["fetch", "entrypoint"]
