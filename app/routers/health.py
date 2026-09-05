from fastapi import APIRouter
from ..freqtrade_client import FreqtradeClient
from ..supabase_client import SupabaseClient

router = APIRouter(tags=["health"])

@router.get("/health")
async def health():
    ft = FreqtradeClient()
    try:
        freqtrade = await ft.ping()
    except Exception as exc:
        freqtrade = {"status": "unreachable", "error": str(exc)}
    try:
        supabase = await SupabaseClient().health()
    except Exception as exc:
        supabase = {"configured": True, "status": "unreachable", "error": str(exc)}
    return {"status": "ok", "freqtrade": freqtrade, "supabase": supabase}
