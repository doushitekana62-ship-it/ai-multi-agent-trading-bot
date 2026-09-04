from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from app.auth.security import require_user
from app.config import settings
from app.indodax.client import IndodaxClient
from app.supabase_client import get_supabase

router = APIRouter(prefix="/coins", tags=["coins"])
class Allocation(BaseModel):
    symbol: str
    allocation_percent: float = Field(gt=0, le=100)
class AllocationRequest(BaseModel):
    coins: list[Allocation] = Field(min_length=1, max_length=6)

@router.get("/available")
def available(user: dict = Depends(require_user)):
    pairs = IndodaxClient().get_pairs()
    return [{"symbol": p.get("ticker_id"), "base_coin": p.get("traded_currency"), "quote_coin": p.get("base_currency"), "description": p.get("description", "")} for p in pairs if str(p.get("base_currency", "")).lower() == "idr"]

@router.get("/allocated")
def allocated(user: dict = Depends(require_user)):
    return get_supabase().table("allocated_coins").select("*").eq("user_id", user["id"]).eq("is_active", True).order("symbol").execute().data

@router.post("/allocate")
def allocate(payload: AllocationRequest, user: dict = Depends(require_user)):
    if len(payload.coins) > settings.max_allocated_coins: raise HTTPException(400, "Maximum 6 active coins")
    if sum(c.allocation_percent for c in payload.coins) > 100.000001: raise HTTPException(400, "Allocation total cannot exceed 100%")
    db = get_supabase(); db.table("allocated_coins").update({"is_active": False}).eq("user_id", user["id"]).execute()
    rows = [{"user_id": user["id"], "symbol": c.symbol.lower(), "allocation_percent": c.allocation_percent, "is_active": True} for c in payload.coins]
    db.table("allocated_coins").upsert(rows, on_conflict="user_id,symbol").execute()
    return {"saved": len(rows), "total_percent": sum(c.allocation_percent for c in payload.coins)}
