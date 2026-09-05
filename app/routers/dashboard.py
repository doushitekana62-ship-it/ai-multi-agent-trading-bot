from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from ..auth import current_token, current_user, supabase
from ..config import settings
from ..freqtrade_runtime import runtime

logger = logging.getLogger(__name__)
router = APIRouter(tags=["dashboard"])


@router.get("/me")
async def me(user=Depends(current_user)):
    return {"user": user}


@router.get("/dashboard")
async def dashboard(user=Depends(current_user), token: str = Depends(current_token)):
    result = {
        "engine": {
            "name": "freqtrade-embedded",
            "exchange": settings.exchange_name,
            "mode": settings.trading_mode,
            "runtime": runtime.status(),
            "strategy": settings.strategy_name,
        },
        "positions": [],
        "orders": [],
        "signals": [],
        "risk_events": [],
        "health": "ok",
    }

    queries = {
        "positions": {"select": "*", "order": "opened_at.desc", "limit": "20"},
        "orders": {"select": "*", "order": "created_at.desc", "limit": "20"},
        "signals": {"select": "*", "order": "created_at.desc", "limit": "20"},
        "risk_events": {"select": "*", "order": "created_at.desc", "limit": "20"},
    }
    for key, params in queries.items():
        try:
            result[key] = await supabase.select(key if key != "signals" else "signal_decisions", token, params)
        except Exception:
            logger.exception("Dashboard query failed table=%s user=%s", key, user.get("id"))

    return result
