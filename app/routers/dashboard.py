from __future__ import annotations

import json
import logging
import sqlite3
from datetime import date, datetime

from fastapi import APIRouter, Depends

from ..auth import current_user
from ..config import settings
from ..freqtrade_runtime import runtime

logger = logging.getLogger(__name__)
router = APIRouter(tags=["dashboard"])


def _jsonable(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _rows(table: str, limit: int = 20) -> list[dict]:
    try:
        with sqlite3.connect(settings.freqtrade_db_path, timeout=2) as conn:
            conn.row_factory = sqlite3.Row
            columns = {row[1] for row in conn.execute(f"pragma table_info({table})")}
            if not columns:
                return []
            order_col = "open_date" if table == "trades" and "open_date" in columns else "order_date"
            if table == "orders" and "order_date" not in columns:
                order_col = "id" if "id" in columns else next(iter(columns))
            selected = ", ".join(sorted(columns))
            query = f"select {selected} from {table} order by {order_col} desc limit ?"
            return [{key: _jsonable(value) for key, value in dict(row).items()} for row in conn.execute(query, (limit,))]
    except (sqlite3.Error, OSError):
        logger.exception("Local Freqtrade database query failed table=%s", table)
        return []


@router.get("/me")
async def me(user=Depends(current_user)):
    return {"user": user}


@router.get("/dashboard")
async def dashboard(user=Depends(current_user)):
    trades = _rows("trades")
    orders = _rows("orders")
    return {
        "engine": {
            "name": "freqtrade-embedded",
            "exchange": settings.exchange_name,
            "mode": settings.trading_mode,
            "runtime": runtime.status(),
            "strategy": settings.strategy_name,
            "database": "local-sqlite",
        },
        "positions": [trade for trade in trades if trade.get("is_open")],
        "trades": trades,
        "orders": orders,
        "signals": [],
        "risk_events": [],
        "health": "ok",
    }
