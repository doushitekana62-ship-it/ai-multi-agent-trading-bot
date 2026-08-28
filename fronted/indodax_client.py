"""Small Cloudflare-compatible INDODAX public API client.

Only public market endpoints are used here. Private account credentials are
intentionally not accepted by this module.
"""
from __future__ import annotations

import json
from math import isfinite
from urllib.parse import parse_qs

from js import fetch
from pyodide.ffi import to_js

BASE_URL = "https://indodax.com/api"
ALLOWED_PAIRS = {"btc_idr", "eth_idr", "usdt_idr", "xrp_idr", "doge_idr", "sol_idr"}


def clean_pair(value: str | None) -> str:
    value = str(value or "btc_idr").strip().lower().replace("/", "_")
    return value if value in ALLOWED_PAIRS else "btc_idr"


def _num(value, default=0.0):
    try:
        value = float(value)
        return value if isfinite(value) else default
    except (TypeError, ValueError):
        return default


async def _get(path: str):
    try:
        response = await fetch(
            f"{BASE_URL}{path}",
            to_js({
                "method": "GET",
                "headers": {
                    "Accept": "application/json",
                    "Cache-Control": "no-cache",
                    "User-Agent": "ai-trading-dashboard/1.0",
                },
            }),
        )
        status = int(response.status)
        text = await response.text()
        if status < 200 or status >= 300:
            return None, f"http_{status}"
        try:
            return json.loads(text), None
        except Exception:
            return None, "invalid_json"
    except Exception as exc:
        return None, type(exc).__name__


def _recent_move(points):
    prices = [_num(point.get("price")) for point in points]
    prices = [price for price in prices if price > 0]
    if len(prices) < 2 or prices[0] <= 0:
        return None
    return ((prices[-1] - prices[0]) / prices[0]) * 100.0


async def market_overview(pair: str = "btc_idr"):
    pair = clean_pair(pair)
    ticker, ticker_error = await _get(f"/{pair}/ticker")
    if not isinstance(ticker, dict) or not isinstance(ticker.get("ticker"), dict):
        return {
            "available": False,
            "pair": pair,
            "currency": "IDR",
            "currency_symbol": "Rp",
            "error": ticker_error or "ticker_unavailable",
            "source": "INDODAX public API",
        }

    t = ticker["ticker"]
    trades, trades_error = await _get(f"/{pair}/trades")
    raw_trades = trades.get("trades", []) if isinstance(trades, dict) else []
    points = []
    for item in raw_trades[-60:]:
        if not isinstance(item, dict):
            continue
        price = _num(item.get("price"))
        if price <= 0:
            continue
        points.append({
            "price": price,
            "timestamp": int(_num(item.get("date") or item.get("trade_time"))),
            "amount": _num(item.get("amount"), 0.0),
            "side": str(item.get("type") or "").lower(),
        })

    return {
        "available": True,
        "pair": pair,
        "base_currency": pair.split("_")[0].upper(),
        "quote_currency": pair.split("_")[1].upper(),
        "currency": "IDR" if pair.endswith("_idr") else pair.split("_")[1].upper(),
        "currency_symbol": "Rp" if pair.endswith("_idr") else pair.split("_")[1].upper(),
        "last": _num(t.get("last")),
        "buy": _num(t.get("buy")),
        "sell": _num(t.get("sell")),
        "high": _num(t.get("high")),
        "low": _num(t.get("low")),
        "volume": _num(t.get("vol_idr") or t.get("vol")),
        "recent_move": _recent_move(points),
        "recent_move_label": "last 60 public trades",
        "points": points,
        "trades_available": trades_error is None,
        "source": "INDODAX public API",
    }


async def market_insights():
    data, error = await _get("/tickers")
    raw = data.get("tickers", {}) if isinstance(data, dict) else {}
    items = []
    if not isinstance(raw, dict):
        return {"items": [], "source": "INDODAX public API", "available": False, "error": error or "invalid_tickers"}

    for pair, ticker in raw.items():
        if not isinstance(ticker, dict) or not str(pair).endswith("_idr"):
            continue
        last = _num(ticker.get("last"))
        high = _num(ticker.get("high"))
        low = _num(ticker.get("low"))
        volume = _num(ticker.get("vol_idr") or ticker.get("vol"))
        if last <= 0:
            continue
        width = high - low
        range_position = ((last - low) / width * 100.0) if width > 0 else 50.0
        signal = "NEAR 24H HIGH" if range_position >= 80 else "NEAR 24H LOW" if range_position <= 20 else "MID 24H RANGE"
        items.append({
            "pair": str(pair).upper().replace("_", "/"),
            "last": last,
            "volume_idr": volume,
            "high": high,
            "low": low,
            "range_position": round(range_position, 1),
            "signal": signal,
        })

    items.sort(key=lambda item: item["volume_idr"], reverse=True)
    return {
        "items": items[:8],
        "source": "INDODAX public API",
        "available": True,
        "note": "Public ticker watchlist only; it does not place trades.",
    }


def pair_from_query(query_string: str) -> str:
    try:
        return clean_pair(parse_qs(query_string or "").get("pair", ["btc_idr"])[0])
    except Exception:
        return "btc_idr"
