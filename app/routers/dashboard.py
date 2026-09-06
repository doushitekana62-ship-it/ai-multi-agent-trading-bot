from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime

from fastapi import APIRouter, Depends

from ..auth import current_user
from ..config import settings
from ..freqtrade_runtime import _writable_sqlite_path, runtime
from ..runtime_monitor import monitor

logger = logging.getLogger(__name__)
router = APIRouter(tags=["dashboard"])


def _jsonable(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _rows(table: str, limit: int = 20) -> list[dict]:
    try:
        path = _writable_sqlite_path()
        with sqlite3.connect(path, timeout=2) as conn:
            conn.row_factory = sqlite3.Row
            columns = {row[1] for row in conn.execute(f"pragma table_info({table})")}
            if not columns:
                return []
            if table == "trades" and "open_date" in columns:
                order_col = "open_date"
            elif table == "orders" and "order_date" in columns:
                order_col = "order_date"
            elif "id" in columns:
                order_col = "id"
            else:
                order_col = next(iter(columns))
            selected = ", ".join(sorted(columns))
            query = f"select {selected} from {table} order by {order_col} desc limit ?"
            return [
                {key: _jsonable(value) for key, value in dict(row).items()}
                for row in conn.execute(query, (limit,))
            ]
    except (sqlite3.Error, OSError, RuntimeError):
        logger.exception("Local Freqtrade database query failed table=%s", table)
        return []


@router.get("/me")
async def me(user=Depends(current_user)):
    return {"user": user}


@router.get("/dashboard")
async def dashboard(user=Depends(current_user)):
    trades = _rows("trades")
    orders = _rows("orders")
    runtime_status = runtime.status()
    return {
        "engine": {
            "name": "freqtrade-embedded",
            "exchange": settings.exchange_name,
            "mode": settings.trading_mode,
            "runtime": runtime_status,
            "strategy": settings.strategy_name,
            "database": "local-sqlite",
        },
        "positions": [trade for trade in trades if trade.get("is_open")],
        "trades": trades,
        "orders": orders,
        "signals": [],
        "risk_events": [],
        "health": {
            "state": monitor.health.get("state"),
            "runtime_ok": runtime_status["running"] and not runtime_status["error"],
            "market_data_healthy": monitor.health.get("market_data_healthy"),
            "database_healthy": monitor.health.get("db_healthy"),
            "last_error": monitor.health.get("last_error"),
            "updated_at": monitor.health.get("updated_at"),
        },
    }
