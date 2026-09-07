from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from ..auth import current_user
from ..config import settings
from ..freqtrade_runtime import runtime

logger = logging.getLogger(__name__)
router = APIRouter(tags=["trading"])


def _validate_start() -> None:
    if not settings.trading_active:
        raise HTTPException(status_code=409, detail="Trading is inactive by master safety switch")
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
        "mode": settings.effective_mode,
        "live_ready": settings.live_ready,
        "trading_active": settings.trading_active,
        "runtime": runtime.status(),
        "strategy": settings.strategy_name,
        "pairs": [item.strip() for item in settings.trading_pairs.split(",") if item.strip()],
    }


@router.get("/engine/diagnostics")
async def engine_diagnostics(user=Depends(current_user)):
    """Safe diagnostic endpoint for the embedded worker and its local log tail."""
    try:
        return runtime.diagnostics()
    except Exception as exc:
        logger.exception("Engine diagnostics failed")
        raise HTTPException(status_code=500, detail="Unable to read engine diagnostics") from exc


@router.post("/engine/start")
async def engine_start(user=Depends(current_user)):
    _validate_start()
    try:
        result = await asyncio.to_thread(runtime.start)
        logger.info("Engine start requested result=%s", result)
        return result
    except Exception as exc:
        logger.exception("Engine start failed")
        raise HTTPException(status_code=500, detail="Engine start failed") from exc


@router.post("/engine/stop")
async def engine_stop(user=Depends(current_user)):
    try:
        result = await asyncio.to_thread(runtime.stop)
        logger.info("Engine stop requested result=%s", result)
        return result
    except Exception as exc:
        logger.exception("Engine stop failed")
        raise HTTPException(status_code=500, detail="Engine stop failed") from exc
