from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from ..auth import current_user
from ..config import settings
from ..freqtrade_runtime import runtime

logger = logging.getLogger(__name__)
router = APIRouter(tags=["trading"])


def _ensure_owner(user: dict) -> None:
    user_id = user.get("id")
    if not settings.bot_owner_user_id:
        raise HTTPException(status_code=503, detail="BOT_OWNER_USER_ID is not configured")
    if user_id != settings.bot_owner_user_id:
        raise HTTPException(status_code=403, detail="Bot control is restricted to the owner")


def _validate_start() -> None:
    if not settings.supabase_db_url:
        raise HTTPException(status_code=503, detail="SUPABASE_DB_URL is not configured")
    if settings.is_live and (not settings.indodax_api_key or not settings.indodax_api_secret):
        raise HTTPException(status_code=503, detail="Indodax API credentials are required for live mode")
    if settings.stake_amount <= 0:
        raise HTTPException(status_code=503, detail="STAKE_AMOUNT must be greater than zero")


@router.get("/engine/status")
async def engine_status(user=Depends(current_user)):
    _ensure_owner(user)
    return {
        "engine": "freqtrade-embedded",
        "exchange": settings.exchange_name,
        "mode": settings.trading_mode,
        "runtime": runtime.status(),
        "strategy": settings.strategy_name,
        "pairs": [item.strip() for item in settings.trading_pairs.split(",") if item.strip()],
    }


@router.post("/engine/start")
async def engine_start(user=Depends(current_user)):
    _ensure_owner(user)
    _validate_start()
    try:
        result = runtime.start()
        logger.info("Engine start requested by user=%s result=%s", user.get("id"), result)
        return result
    except Exception as exc:
        logger.exception("Engine start failed")
        raise HTTPException(status_code=500, detail="Engine start failed") from exc


@router.post("/engine/stop")
async def engine_stop(user=Depends(current_user)):
    _ensure_owner(user)
    try:
        result = runtime.stop()
        logger.info("Engine stop requested by user=%s result=%s", user.get("id"), result)
        return result
    except Exception as exc:
        logger.exception("Engine stop failed")
        raise HTTPException(status_code=500, detail="Engine stop failed") from exc
