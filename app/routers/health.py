from __future__ import annotations

import asyncio
import logging

import psycopg
from fastapi import APIRouter

from ..config import settings
from ..freqtrade_runtime import runtime

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


def _safe_error(exc: Exception) -> str:
    message = str(exc).replace("\n", " ").strip()
    for secret in (settings.supabase_db_url, settings.supabase_service_role_key, settings.supabase_anon_key, settings.indodax_api_key, settings.indodax_api_secret):
        if secret:
            message = message.replace(secret, "[redacted]")
    return f"{type(exc).__name__}: {message[:300]}"


@router.get("/health")
async def health():
    return {
        "ok": True,
        "service": "fastapi",
        "engine": "freqtrade-embedded",
        "engine_runtime": runtime.status(),
        "exchange": settings.exchange_name,
        "mode": settings.trading_mode,
        "live_ready": settings.live_ready,
    }


async def _database_check() -> dict:
    if not settings.supabase_db_url:
        return {"ok": False, "error": "DATABASE_URL/SUPABASE_DB_URL is not configured"}
    try:
        async with await psycopg.AsyncConnection.connect(settings.supabase_db_url, connect_timeout=8) as conn:
            async with conn.cursor() as cur:
                await cur.execute("select current_database(), current_schema()")
                row = await cur.fetchone()
        return {"ok": True, "database": row[0], "schema": row[1]}
    except Exception as exc:
        logger.exception("Supabase PostgreSQL dependency check failed")
        return {"ok": False, "error": _safe_error(exc)}


def _indodax_public_check() -> dict:
    try:
        import ccxt

        exchange = ccxt.indodax({"enableRateLimit": True})
        markets = exchange.load_markets()
        pairs = [item.strip() for item in settings.trading_pairs.split(",") if item.strip()]
        symbol = pairs[0] if pairs else "BTC/IDR"
        if symbol not in markets:
            return {"ok": False, "exchange": "indodax", "error": f"symbol_not_found: {symbol}"}
        ticker = exchange.fetch_ticker(symbol)
        orderbook = exchange.fetch_order_book(symbol, limit=5)
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=settings.timeframe, limit=2)
        bid = ticker.get("bid")
        ask = ticker.get("ask")
        spread_bps = None
        if bid and ask and bid > 0:
            spread_bps = ((ask - bid) / bid) * 10000
        return {
            "ok": True,
            "exchange": "indodax",
            "symbol": symbol,
            "markets_loaded": len(markets),
            "last_price": ticker.get("last"),
            "bid": bid,
            "ask": ask,
            "spread_bps": spread_bps,
            "orderbook_levels": len(orderbook.get("bids", [])) + len(orderbook.get("asks", [])),
            "ohlcv_candles": len(ohlcv),
        }
    except Exception as exc:
        logger.exception("Indodax CCXT public compatibility check failed")
        return {"ok": False, "exchange": "indodax", "error": _safe_error(exc)}


async def _indodax_check() -> dict:
    if settings.exchange_name.lower() != "indodax":
        return {"ok": False, "error": f"Expected EXCHANGE_NAME=indodax, got {settings.exchange_name}"}
    return await asyncio.to_thread(_indodax_public_check)


@router.get("/health/dependencies")
async def dependency_health():
    database, indodax = await asyncio.gather(_database_check(), _indodax_check())
    return {
        "ok": database["ok"] and indodax["ok"],
        "fastapi": True,
        "supabase_postgres": database,
        "indodax_ccxt_market_data": indodax,
        "freqtrade": {
            "embedded": True,
            "paper_mode": not settings.live_ready,
            "runtime": runtime.status(),
        },
    }
