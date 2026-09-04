"""Public Indodax market endpoints used by the GitHub Pages dashboard."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

import requests
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()
INDODAX_BASE = "https://indodax.com/api"
PAIRS = {
    "btc_idr", "eth_idr", "usdt_idr", "xrp_idr", "doge_idr", "sol_idr",
    "beat_idr", "hype_idr", "ada_idr", "trx_idr", "shib_idr", "pepe_idr",
}


def _pair(value: str) -> str:
    value = str(value or "btc_idr").strip().lower().replace("/", "_")
    return value if value in PAIRS else "btc_idr"


def _get(path: str) -> Any:
    response = requests.get(f"{INDODAX_BASE}{path}", timeout=8, headers={"Accept": "application/json"})
    response.raise_for_status()
    return response.json()


def _trades(payload: Any) -> list[dict[str, Any]]:
    rows = payload if isinstance(payload, list) else payload.get("trades", []) if isinstance(payload, dict) else []
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            price = float(row.get("price") or 0)
            amount = float(row.get("amount") or 0)
            timestamp = float(row.get("date") or row.get("trade_time") or row.get("timestamp") or 0)
        except (TypeError, ValueError):
            continue
        if price <= 0 or timestamp <= 0:
            continue
        if timestamp > 1_000_000_000_000:
            timestamp /= 1000
        side = str(row.get("type") or row.get("side") or "").lower()
        result.append({
            "tid": str(row.get("tid") or row.get("trade_id") or ""),
            "price": price,
            "timestamp": timestamp,
            "amount": max(0.0, amount),
            "type": side,
            "side": side,
            "source": "INDODAX public market data",
            "observation_type": "TRADE",
        })
    return result[-1440:]


def _pulse(points: list[dict[str, Any]], now: float) -> tuple[list[dict[str, Any]], float | None]:
    current = int(now // 60) * 60
    buckets: dict[int, dict[str, Any]] = {}
    for point in points:
        minute = int(float(point["timestamp"]) // 60) * 60
        if minute < current - 29 * 60 or minute > current:
            continue
        price = float(point["price"])
        bucket = buckets.get(minute)
        if bucket is None:
            bucket = {"minute": minute, "open": price, "high": price, "low": price, "close": price, "samples": 0, "changed": False, "last_direction": "GRAY"}
            buckets[minute] = bucket
        else:
            if price != bucket["close"]:
                bucket["changed"] = True
                bucket["last_direction"] = "GREEN" if price > bucket["close"] else "RED"
            bucket["high"] = max(bucket["high"], price)
            bucket["low"] = min(bucket["low"], price)
            bucket["close"] = price
        bucket["samples"] += 1
    segments = []
    for i in range(30):
        minute = current - (29 - i) * 60
        bucket = buckets.get(minute)
        if not bucket:
            segments.append({"minute": minute, "status": "GRAY", "move": None, "samples": 0, "changed": False})
            continue
        move = ((bucket["close"] - bucket["open"]) / bucket["open"] * 100) if bucket["open"] else 0.0
        status = "GREEN" if move > 0 else "RED" if move < 0 else bucket["last_direction"] if bucket["changed"] else "GRAY"
        segments.append({**bucket, "status": status, "move": move})
    populated = [s for s in segments if s.get("open") and s.get("close")]
    move30 = None
    if populated:
        move30 = (float(populated[-1]["close"]) - float(populated[0]["open"])) / float(populated[0]["open"]) * 100
    return segments, move30


async def _overview(pair: str) -> dict[str, Any]:
    try:
        ticker, trades = await asyncio.gather(asyncio.to_thread(_get, f"/{pair}/ticker"), asyncio.to_thread(_get, f"/{pair}/trades"))
        ticker_data = ticker.get("ticker", {}) if isinstance(ticker, dict) else {}
        if not isinstance(ticker_data, dict):
            raise ValueError("invalid ticker response")
        last = float(ticker_data.get("last") or 0)
        if last <= 0:
            raise ValueError("invalid market price")
        points = _trades(trades)
        now = time.time()
        points.append({"tid": f"ticker:{pair}:{int(now)}", "price": last, "timestamp": now, "amount": 0.0, "type": "ticker", "side": "", "source": "INDODAX public ticker", "observation_type": "TICKER"})
        segments, move30 = _pulse(points, now)
        return {
            "available": True, "pair": pair, "base_currency": pair.split("_")[0].upper(), "quote_currency": pair.split("_")[1].upper(),
            "currency": "IDR", "currency_symbol": "Rp", "last": last,
            "buy": float(ticker_data.get("buy") or 0), "sell": float(ticker_data.get("sell") or 0),
            "high": float(ticker_data.get("high") or 0), "low": float(ticker_data.get("low") or 0),
            "volume": float(ticker_data.get("vol_idr") or ticker_data.get("vol") or 0),
            "recent_move": move30, "points": points, "pulse_segments": segments,
            "source": "INDODAX public market data", "market_data_quality": "TRADE_STREAM_PLUS_TICKER" if len(points) > 1 else "TICKER_FALLBACK",
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"INDODAX market data unavailable: {type(exc).__name__}") from exc


@router.get("/overview")
async def overview(pair: str = Query("btc_idr")):
    return await _overview(_pair(pair))


@router.get("/insights")
async def insights():
    try:
        payload = await asyncio.to_thread(_get, "/tickers")
        raw = payload.get("tickers", {}) if isinstance(payload, dict) else {}
        items = []
        for pair, ticker in raw.items():
            if not pair.endswith("_idr") or not isinstance(ticker, dict):
                continue
            try:
                last = float(ticker.get("last") or 0); high = float(ticker.get("high") or 0); low = float(ticker.get("low") or 0); volume = float(ticker.get("vol_idr") or 0)
            except (TypeError, ValueError):
                continue
            if last <= 0:
                continue
            width = high - low
            position = ((last - low) / width * 100) if width > 0 else 50.0
            signal = "NEAR 24H HIGH" if position >= 80 else "NEAR 24H LOW" if position <= 20 else "MID 24H RANGE"
            items.append({"pair": pair.upper().replace("_", "/"), "last": last, "volume_idr": volume, "high": high, "low": low, "range_position": round(position, 1), "signal": signal, "scalping_supported": pair.lower() in PAIRS})
        items.sort(key=lambda item: item["volume_idr"], reverse=True)
        return {"items": items[:20], "total_idr_pairs": len(items), "scalping_pairs": [item["pair"] for item in items if item["scalping_supported"]], "source": "INDODAX public ticker", "note": "Market-data watchlist only; it does not place trades."}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"INDODAX ticker data unavailable: {type(exc).__name__}") from exc
