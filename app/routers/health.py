from __future__ import annotations

import asyncio
import logging
import sqlite3

from fastapi import APIRouter

from ..config import settings
from ..freqtrade_runtime import _writable_sqlite_path, runtime

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


def _safe_error(exc: Exception) -> str:
    message = str(exc).replace("\n", " ").strip()
    for secret in (settings.dashboard_token, settings.indodax_api_key, settings.indodax_api_secret):
        if secret:
            message = message.replace(secret, "[redacted]")
    return f"{type(exc).__name__}: {message[:300]}"


@router.get("/health/live")
async def liveness():
    """Process-level health check that does not depend on Freqtrade."""
    return {
        "ok": True,
        "service": "fastapi",
        "mode": settings.trading_mode,
        "engine_runtime": runtime.status(),
    }


@router.get("/health")
async def health():
    runtime_status = runtime.status()
    engine_ok = runtime_status["running"] and not runtime_status["error"]
    return {
        "ok": engine_ok,
        "service": "fastapi",
        "engine": "freqtrade-embedded",
        "engine_runtime": runtime_status,
        "exchange": settings.exchange_name,
        "mode": settings.trading_mode,
        "live_ready": settings.live_ready,
        "database": "local-sqlite",
        "database_path": settings.freqtrade_db_path,
    }


async def _database_check() -> dict:
    def check() -> dict:
        try:
            path = _writable_sqlite_path()
            with sqlite3.connect(path, timeout=2) as conn:
                conn.execute("select 1")
                tables = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
            return {"ok": True, "path": str(path), "tables": len(tables)}
        except Exception as exc:
            logger.exception("Local SQLite dependency check failed")
            return {"ok": False, "error": _safe_error(exc)}
    return await asyncio.to_thread(check)


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
    runtime_status = runtime.status()
    runtime_ok = runtime_status["running"] and not runtime_status["error"]
    return {
        "ok": database["ok"] and indodax["ok"] and runtime_ok,
        "fastapi": True,
        "local_sqlite": database,
        "indodax_ccxt_market_data": indodax,
        "freqtrade": {
            "embedded": True,
            "paper_mode": not settings.live_ready,
            "runtime": runtime_status,
        },
    }
