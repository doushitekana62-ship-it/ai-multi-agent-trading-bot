"""Explicit paper-trading runtime controls for the dashboard."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.core.security import verify_token
from backend.routes import dashboard as dashboard_module
from core.live_paper_cycle import LivePaperCycle
from core.runtime_state import get_engine_status, set_engine_running

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer()

_cycle: Optional[LivePaperCycle] = None
_task: Optional[asyncio.Task] = None
_symbol = "BTC/IDR"
_lock = asyncio.Lock()


def authenticate(credentials: HTTPAuthorizationCredentials):
    payload = verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return payload


def _ensure_cycle() -> LivePaperCycle:
    global _cycle
    if _cycle is None:
        cycle = LivePaperCycle({"paper": {"initial_balance": 10_000_000.0}, "max_open_positions": 5})
        cycle.executor = dashboard_module.executor
        cycle.executor.paper_trading = dashboard_module.paper_trading
        _cycle = cycle
    return _cycle


async def _run_loop(symbol: str) -> None:
    cycle = _ensure_cycle()
    set_engine_running(True, "paper")
    logger.info("Dashboard paper runtime STARTED | symbol=%s", symbol)
    try:
        while True:
            try:
                result = await cycle.cycle(symbol)
                logger.info(
                    "Paper cycle | symbol=%s action=%s executed=%s",
                    symbol, result.get("action"), result.get("executed"),
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Paper cycle failed; runtime remains active")
            await asyncio.sleep(30)
    finally:
        set_engine_running(False, "paper")
        logger.info("Dashboard paper runtime STOPPED")


@router.post("/start")
async def start_paper(
    symbol: str = "BTC/IDR",
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    global _task, _symbol
    authenticate(credentials)
    symbol = symbol.upper().strip() or "BTC/IDR"
    async with _lock:
        if _task is not None and not _task.done():
            return {"running": True, "mode": "paper", "symbol": _symbol, "message": "Paper trading is already running."}
        _symbol = symbol
        _ensure_cycle()
        _task = asyncio.create_task(_run_loop(_symbol), name="paper-trading-runtime")
    return {"running": True, "mode": "paper", "symbol": _symbol, "message": "Paper trading started."}


@router.post("/stop")
async def stop_paper(credentials: HTTPAuthorizationCredentials = Depends(security)):
    global _task
    authenticate(credentials)
    async with _lock:
        task = _task
        _task = None
        if task is not None and not task.done():
            task.cancel()
        set_engine_running(False, "paper")
    return {"running": False, "mode": "paper", "message": "Paper trading stopped."}


@router.get("/status")
async def paper_status(credentials: HTTPAuthorizationCredentials = Depends(security)):
    authenticate(credentials)
    engine = get_engine_status()
    return {
        "running": engine["running"],
        "mode": engine["mode"],
        "symbol": _symbol,
        "runtime_seconds": engine["runtime_seconds"],
        "started_at": engine["started_at"],
        "last_cycle_at": engine["last_cycle_at"],
    }
