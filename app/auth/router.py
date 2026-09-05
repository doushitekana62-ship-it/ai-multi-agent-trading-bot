from fastapi import APIRouter, Depends
from app.auth.security import require_user
from app.config import settings
from app.supabase_client import execute_data, execute_one, get_supabase

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
def me(user: dict = Depends(require_user)):
    db = get_supabase()
    existing = execute_one(db.table("users_settings").select("id").eq("id", user["id"]))
    if not existing:
        execute_data(
            db.table("users_settings").insert({
                "id": user["id"],
                "risk_per_trade": settings.default_risk_per_trade,
                "daily_loss_limit_percent": settings.daily_loss_limit_percent,
                "compounding_enabled": True,
                "paper_initial_balance": settings.paper_initial_balance,
            }),
            [],
        )
    account = execute_one(
        db.table("trading_accounts").select("id").eq("user_id", user["id"]).eq("mode", "paper")
    )
    if not account:
        initial = settings.paper_initial_balance
        execute_data(
            db.table("trading_accounts").insert({
                "user_id": user["id"],
                "mode": "paper",
                "initial_balance": initial,
                "cash_balance": initial,
                "daily_start_balance": initial,
            }),
            [],
        )
    return {"id": user["id"], "email": user["email"]}
