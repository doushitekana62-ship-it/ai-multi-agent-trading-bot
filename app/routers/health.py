from __future__ import annotations

import logging

import httpx
import psycopg
from fastapi import APIRouter

from ..config import settings
from ..freqtrade_runtime import runtime
from ..supabase_client import SupabaseClient

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    supabase = await SupabaseClient().health()
    runtime_status = runtime.status()
    return {
        "ok": bool(supabase.get("configured")),
        "service": "fastapi",
        "engine": "freqtrade-embedded",
        "engine_runtime": runtime_status,
        "exchange": settings.exchange_name,
        "mode": settings.trading_mode,
        "supabase": supabase,
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
        return {"ok": False, "error": type(exc).__name__}


async def _bybit_check() -> dict:
    if settings.exchange_name.lower() != "bybit":
        return {"ok": False, "error": f"Expected EXCHANGE_NAME=bybit, got {settings.exchange_name}"}
    pairs = [item.strip() for item in settings.trading_pairs.split(",") if item.strip()]
    symbol = pairs[0] if pairs else "BTC/USDT"
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(
                "https://api.bybit.com/v5/market/tickers",
                params={"category": "spot", "symbol": symbol.replace("/", "")},
            )
            response.raise_for_status()
            payload = response.json()
        result = payload.get("result", {}).get("list", [])
        if not result:
            return {"ok": False, "symbol": symbol, "error": "symbol_not_found"}
        ticker = result[0]
        return {
            "ok": True,
            "exchange": "bybit",
            "symbol": symbol,
            "last_price": ticker.get("lastPrice"),
            "bid": ticker.get("bid1Price"),
            "ask": ticker.get("ask1Price"),
        }
    except Exception as exc:
        logger.exception("Bybit market-data dependency check failed")
        return {"ok": False, "symbol": symbol, "error": type(exc).__name__}


@router.get("/health/dependencies")
async def dependency_health():
    """Non-trading smoke test for PostgreSQL and public Bybit market data."""
    database, bybit = await _database_check(), await _bybit_check()
    return {
        "ok": database["ok"] and bybit["ok"],
        "fastapi": True,
        "supabase_postgres": database,
        "bybit_market_data": bybit,
        "freqtrade": {
            "embedded": True,
            "paper_mode": not settings.is_live,
            "runtime": runtime.status(),
        },
    }
