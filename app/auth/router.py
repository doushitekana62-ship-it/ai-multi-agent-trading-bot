from fastapi import APIRouter, Depends
from app.auth.security import require_user
from app.config import settings
from app.supabase_client import get_supabase

router = APIRouter(prefix="/auth", tags=["auth"])

@router.get("/me")
def me(user: dict = Depends(require_user)):
    db = get_supabase()
    existing = db.table("users_settings").select("id").eq("id", user["id"]).maybe_single().execute().data
    if not existing:
        db.table("users_settings").insert({
            "id": user["id"], "risk_per_trade": settings.default_risk_per_trade,
            "daily_loss_limit_percent": settings.daily_loss_limit_percent,
            "compounding_enabled": True, "paper_initial_balance": settings.paper_initial_balance,
        }).execute()
    account = db.table("trading_accounts").select("id").eq("user_id", user["id"]).eq("mode", "paper").maybe_single().execute().data
    if not account:
        initial = settings.paper_initial_balance
        db.table("trading_accounts").insert({"user_id": user["id"], "mode": "paper", "initial_balance": initial, "cash_balance": initial, "daily_start_balance": initial}).execute()
    return {"id": user["id"], "email": user["email"]}
