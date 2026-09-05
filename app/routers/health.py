from __future__ import annotations

import logging

import httpx
import psycopg
from fastapi import APIRouter

from ..config import settings
from ..freqtrade_runtime import runtime

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


def _safe_error(exc: Exception) -> str:
    message = str(exc).replace("\n", " ").strip()
    for secret in (settings.supabase_db_url, settings.supabase_service_role_key, settings.supabase_anon_key):
        if secret:
            message = message.replace(secret, "[redacted]")
    return f"{type(exc).__name__}: {message[:300]}"


@router.get("/health")
async def health():
    # Keep the platform liveness endpoint dependency-free. Database and
    # exchange diagnostics live under /health/dependencies.
    return {
        "ok": True,
        "service": "fastapi",
        "engine": "freqtrade-embedded",
        "engine_runtime": runtime.status(),
        "exchange": settings.exchange_name,
        "mode": settings.trading_mode,
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


async def _bybit_check() -> dict:
    if settings.exchange_name.lower() != "bybit":
        return {"ok": False, "error": f"Expected EXCHANGE_NAME=bybit, got {settings.exchange_name}"}
    pairs = [item.strip() for item in settings.trading_pairs.split(",") if item.strip()]
    symbol = pairs[0] if pairs else "BTC/USDT"
    params = {"category": "spot", "symbol": symbol.replace("/", "")}
    endpoints = ("https://api.bybit.com", "https://api.bytick.com")
    errors: list[str] = []

    async with httpx.AsyncClient(timeout=8) as client:
        for base_url in endpoints:
            try:
                response = await client.get(f"{base_url}/v5/market/tickers", params=params)
                payload = response.json()
                if response.status_code >= 400:
                    body = response.text.replace("\n", " ").strip()[:300]
                    errors.append(f"{base_url}: HTTP {response.status_code}: {body}")
                    continue
                if payload.get("retCode") not in (0, None):
                    errors.append(f"{base_url}: retCode={payload.get('retCode')} retMsg={payload.get('retMsg')}")
                    continue
                result = payload.get("result", {}).get("list", [])
                if not result:
                    errors.append(f"{base_url}: symbol_not_found")
                    continue
                ticker = result[0]
                return {
                    "ok": True,
                    "exchange": "bybit",
                    "endpoint": base_url,
                    "symbol": symbol,
                    "last_price": ticker.get("lastPrice"),
                    "bid": ticker.get("bid1Price"),
                    "ask": ticker.get("ask1Price"),
                }
            except Exception as exc:
                errors.append(f"{base_url}: {_safe_error(exc)}")

    return {"ok": False, "symbol": symbol, "error": " | ".join(errors)[:900]}


@router.get("/health/dependencies")
async def dependency_health():
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
