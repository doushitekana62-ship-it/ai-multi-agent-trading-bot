"""Internal paper-trading engine routes.

The Cloudflare Worker owns the persistent user-facing safety gate. This
service is the execution runtime and is intentionally paper-only.
"""

import os
import logging
from dataclasses import asdict, is_dataclass
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, status

from integration.trading_engine import TradingIntegrationEngine

logger = logging.getLogger(__name__)
router = APIRouter()

_engine = TradingIntegrationEngine({
    "mode": "paper",
    "use_unified_data": True,
    "exchange_type": "indodax",
    "execution_allowed": True,
    "execution_gate": {
        "min_confidence": float(os.getenv("ENGINE_MIN_CONFIDENCE", "0.60")),
        "min_risk_reward": float(os.getenv("ENGINE_MIN_RR", "1.50")),
        "max_position_size": float(os.getenv("ENGINE_MAX_POSITION", "0.20")),
    },
    "indodax": {
        "api_key": os.getenv("INDODAX_API_KEY"),
        "secret": os.getenv("INDODAX_API_SECRET"),
        "enable_trading": False,
    },
})


def _engine_key_is_valid(value: str | None) -> bool:
    expected = str(os.getenv("ENGINE_SHARED_SECRET", "") or "").strip()
    supplied = str(value or "").strip()
    return bool(expected) and bool(supplied) and supplied == expected


def _safe(value: Any):
    if is_dataclass(value):
        return _safe(asdict(value))
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


@router.get("/health")
async def engine_health(x_engine_key: str | None = Header(default=None)):
    if not _engine_key_is_valid(x_engine_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid engine key")
    return {
        "status": "healthy",
        "mode": "paper",
        "real_trading_locked": True,
    }


@router.post("/cycle")
async def run_paper_cycle(
    symbol: str = Query("BTC/IDR"),
    x_engine_key: str | None = Header(default=None),
):
    """Run exactly one explicit AI paper-trading cycle.

    This endpoint does not expose a loop, scheduler, or real-order path.
    """
    if not _engine_key_is_valid(x_engine_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid engine key")

    symbol = symbol.strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol cannot be empty")

    try:
        result = await _engine.analyze_and_execute(symbol)
        return _safe({
            "status": result.get("status"),
            "stage": result.get("stage"),
            "symbol": result.get("symbol"),
            "action": result.get("action", "HOLD"),
            "confidence": result.get("confidence", 0.0),
            "position_size": result.get("position_size", 0.0),
            "current_price": result.get("current_price"),
            "stop_loss": result.get("stop_loss"),
            "take_profit": result.get("take_profit"),
            "reason": result.get("reason"),
            "hold_reason": result.get("hold_reason"),
            "paper_summary": result.get("paper_summary"),
        })
    except Exception as exc:
        logger.exception("Paper cycle failed for %s", symbol)
        raise HTTPException(status_code=500, detail=f"Paper cycle failed: {exc}")
