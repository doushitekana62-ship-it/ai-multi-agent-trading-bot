from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from ..auth import current_user
from ..config import settings
from ..freqtrade_runtime import runtime

logger = logging.getLogger(__name__)
router = APIRouter(tags=["trading"])


def _validate_start() -> None:
    if settings.exchange_name != "indodax":
        raise HTTPException(status_code=503, detail="EXCHANGE_NAME must be indodax for this bot")
    if settings.is_live:
        if not settings.live_trading_enabled:
            raise HTTPException(status_code=409, detail="Live trading is safety-locked. Set LIVE_TRADING_ENABLED=true only after compatibility and reconciliation tests pass")
        if not settings.indodax_api_key or not settings.indodax_api_secret:
            raise HTTPException(status_code=503, detail="Indodax API credentials are required for live mode")
    if settings.stake_amount <= 0:
        raise HTTPException(status_code=503, detail="STAKE_AMOUNT must be greater than zero")
    if settings.max_open_trades < 1:
        raise HTTPException(status_code=503, detail="MAX_OPEN_TRADES must be at least 1")
    if settings.process_throttle_secs <= 0:
        raise HTTPException(status_code=503, detail="PROCESS_THROTTLE_SECS must be greater than zero")


@router.get("/engine/status")
async def engine_status(user=Depends(current_user)):
    return {
        "engine": "freqtrade-embedded",
        "exchange": settings.exchange_name,
        "mode": settings.trading_mode,
        "live_ready": settings.live_ready,
        "runtime": runtime.status(),
        "strategy": settings.strategy_name,
        "pairs": [item.strip() for item in settings.trading_pairs.split(",") if item.strip()],
    }


@router.post("/engine/start")
async def engine_start(user=Depends(current_user)):
    _validate_start()
    try:
        result = runtime.start()
        logger.info("Engine start requested result=%s", result)
        return result
    except Exception as exc:
        logger.exception("Engine start failed")
        raise HTTPException(status_code=500, detail="Engine start failed") from exc


@router.post("/engine/stop")
async def engine_stop(user=Depends(current_user)):
    try:
        result = runtime.stop()
        logger.info("Engine stop requested result=%s", result)
        return result
    except Exception as exc:
        logger.exception("Engine stop failed")
        raise HTTPException(status_code=500, detail="Engine stop failed") from exc
