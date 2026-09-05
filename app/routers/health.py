from __future__ import annotations

import logging

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
