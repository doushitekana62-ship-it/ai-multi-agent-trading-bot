from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.auth.security import require_user
from app.agents.executor_agent import ExecutorAgent
from app.supabase_client import get_supabase

router = APIRouter(prefix="/positions", tags=["positions"])

@router.get("")
def list_positions(mode: str = "paper", user: dict = Depends(require_user)):
    if mode not in {"paper", "live"}: raise HTTPException(400, "Invalid mode")
    return get_supabase().table("positions").select("*").eq("user_id", user["id"]).eq("mode", mode).order("opened_at", desc=True).limit(100).execute().data

class CloseRequest(BaseModel): price: float

@router.post("/{position_id}/close")
def close_position(position_id: str, payload: CloseRequest, mode: str = "paper", user: dict = Depends(require_user)):
    if mode not in {"paper", "live"}: raise HTTPException(400, "Invalid mode")
    db = get_supabase(); position = db.table("positions").select("*").eq("id", position_id).eq("user_id", user["id"]).eq("mode", mode).eq("status", "open").maybe_single().execute().data
    if not position: raise HTTPException(404, "Open position not found")
    return ExecutorAgent(mode).close_position(user["id"], position, payload.price, "manual")
