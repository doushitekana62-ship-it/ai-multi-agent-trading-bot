from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.auth.security import require_user
from app.config import settings
from app.supabase_client import execute_data, execute_one, get_supabase

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _setting(db, user_id):
    row = execute_one(db.table("users_settings").select("*").eq("id", user_id))
    if not row:
        row = {
            "id": user_id,
            "trading_mode": "paper",
            "bot_enabled": False,
            "risk_per_trade": settings.default_risk_per_trade,
            "daily_loss_limit_percent": settings.daily_loss_limit_percent,
        }
        execute_data(db.table("users_settings").upsert(row, on_conflict="id"), [])
    return row


@router.get("/summary")
def summary(mode: str | None = None, user: dict = Depends(require_user)):
    db = get_supabase()
    user_settings = _setting(db, user["id"])
    selected_mode = mode if mode in {"paper", "live"} else user_settings.get("trading_mode", "paper")
    positions = execute_data(
        db.table("positions")
        .select("*")
        .eq("user_id", user["id"])
        .eq("mode", selected_mode)
        .order("opened_at", desc=True)
        .limit(100),
        [],
    ) or []
    today = datetime.now(timezone.utc).date().isoformat()
    closed = [p for p in positions if p.get("closed_at") and str(p["closed_at"])[:10] == today]
    pnl = sum(float(p.get("pnl") or 0) for p in closed)
    account = execute_one(
        db.table("trading_accounts").select("*").eq("user_id", user["id"]).eq("mode", selected_mode)
    )
    signals = execute_data(
        db.table("forecast_signals")
        .select("*")
        .eq("user_id", user["id"])
        .eq("mode", selected_mode)
        .order("created_at", desc=True)
        .limit(5),
        [],
    ) or []
    start_balance = float((account or {}).get("daily_start_balance") or 1)
    return {
        "mode": selected_mode,
        "bot_enabled": bool(user_settings.get("bot_enabled", False)),
        "balance": float((account or {}).get("cash_balance") or 0),
        "today_pnl": pnl,
        "today_pnl_percent": (pnl / start_balance) * 100,
        "open_positions": [p for p in positions if p.get("status") == "open"],
        "transactions": closed[:5],
        "signals": signals,
        "settings": {
            "risk_per_trade": float(user_settings.get("risk_per_trade") or settings.default_risk_per_trade),
            "daily_loss_limit_percent": float(
                user_settings.get("daily_loss_limit_percent") or settings.daily_loss_limit_percent
            ),
        },
    }


class ModeRequest(BaseModel):
    mode: str


@router.post("/mode")
def set_mode(payload: ModeRequest, user: dict = Depends(require_user)):
    if payload.mode not in {"paper", "live"}:
        raise HTTPException(400, "Invalid mode")
    if payload.mode == "live" and not (settings.indodax_api_key and settings.indodax_secret_key):
        raise HTTPException(503, "Live trading credentials are not configured")

    db = get_supabase()
    _setting(db, user["id"])
    execute_data(
        db.table("users_settings").update({"trading_mode": payload.mode}).eq("id", user["id"]),
        [],
    )
    if payload.mode == "paper" and not execute_one(
        db.table("trading_accounts").select("id").eq("user_id", user["id"]).eq("mode", "paper")
    ):
        initial = settings.paper_initial_balance
        execute_data(
            db.table("trading_accounts").insert(
                {
                    "user_id": user["id"],
                    "mode": "paper",
                    "initial_balance": initial,
                    "cash_balance": initial,
                    "daily_start_balance": initial,
                }
            ),
            [],
        )
    return {"mode": payload.mode}


@router.post("/bot/toggle")
def toggle_bot(user: dict = Depends(require_user)):
    db = get_supabase()
    current = _setting(db, user["id"])
    active = not bool(current.get("bot_enabled", False))
    execute_data(db.table("users_settings").update({"bot_enabled": active}).eq("id", user["id"]), [])
    return {"active": active}
