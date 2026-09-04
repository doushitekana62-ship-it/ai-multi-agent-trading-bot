import asyncio
import logging
from datetime import datetime, timezone
from app.agents.forecast_agent import ForecastAgent
from app.agents.scalping_library import ScalpingLibraryAgent
from app.agents.executor_agent import ExecutorAgent
from app.config import settings
from app.indodax.client import IndodaxClient
from app.supabase_client import get_supabase

log = logging.getLogger(__name__)

class TradingScheduler:
    def __init__(self):
        self.market = IndodaxClient()
        self.forecast = ForecastAgent(settings.min_signal_confidence)
        self.running = False

    def _ensure_account(self, db, user_id, mode):
        account = db.table("trading_accounts").select("*").eq("user_id", user_id).eq("mode", mode).maybe_single().execute().data
        if account: return account
        initial = settings.paper_initial_balance if mode == "paper" else 0.0
        return db.table("trading_accounts").insert({"user_id": user_id, "mode": mode, "initial_balance": initial, "cash_balance": initial, "daily_start_balance": initial}).execute().data[0]

    def _daily_pnl(self, db, user_id, mode):
        today = datetime.now(timezone.utc).date().isoformat()
        rows = db.table("positions").select("pnl").eq("user_id", user_id).eq("mode", mode).gte("closed_at", today).execute().data or []
        return sum(float(x.get("pnl") or 0) for x in rows)

    def run_cycle(self):
        db = get_supabase()
        users = db.table("users_settings").select("id,risk_per_trade,compounding_enabled,trading_mode,bot_enabled,daily_loss_limit_percent").execute().data or []
        for user in users:
            if not user.get("bot_enabled", False): continue
            user_id = str(user["id"]); mode = user.get("trading_mode", "paper") if user.get("trading_mode") in {"paper", "live"} else "paper"
            account = self._ensure_account(db, user_id, mode)
            allocations = db.table("allocated_coins").select("symbol,allocation_percent").eq("user_id", user_id).eq("is_active", True).order("symbol").limit(settings.max_allocated_coins).execute().data or []
            for alloc in allocations:
                symbol = str(alloc["symbol"]).lower()
                try:
                    tick = self.market.get_ticker(symbol)
                    if tick["price"] <= 0: continue
                    ticks = db.table("market_ticks").select("price").eq("symbol", symbol).order("created_at", desc=True).limit(60).execute().data or []
                    prices = [float(x["price"]) for x in reversed(ticks)] + [tick["price"]]
                    db.table("market_ticks").insert({"symbol": symbol, "price": tick["price"]}).execute()
                    forecast = self.forecast.analyze(symbol, prices)
                    if not forecast: continue
                    db.table("forecast_signals").insert({"user_id": user_id, "mode": mode, "symbol": symbol, "suggested_tp": forecast.suggested_tp, "suggested_sl": forecast.suggested_sl, "confidence": forecast.confidence, "action": forecast.action, "indicators": forecast.indicators}).execute()
                    open_pos = db.table("positions").select("*").eq("user_id", user_id).eq("mode", mode).eq("symbol", symbol).eq("status", "open").maybe_single().execute().data
                    if open_pos:
                        if tick["price"] >= float(open_pos["tp_price"]): ExecutorAgent(mode).close_position(user_id, open_pos, tick["price"], "tp_hit")
                        elif tick["price"] <= float(open_pos["sl_price"]): ExecutorAgent(mode).close_position(user_id, open_pos, tick["price"], "sl_hit")
                        continue
                    daily_pnl = self._daily_pnl(db, user_id, mode)
                    open_rows = db.table("positions").select("quantity").eq("user_id", user_id).eq("mode", mode).eq("status", "open").execute().data or []
                    equity = float(account["cash_balance"]) + sum(float(p.get("quantity") or 0) * tick["price"] for p in open_rows)
                    library = ScalpingLibraryAgent(float(user.get("risk_per_trade") or settings.default_risk_per_trade), float(user.get("daily_loss_limit_percent") or settings.daily_loss_limit_percent), settings.min_signal_confidence)
                    signal = library.validate(forecast, float(alloc["allocation_percent"]), equity, daily_pnl, False)
                    if signal: ExecutorAgent(mode).open_position(user_id, signal)
                except Exception:
                    log.exception("cycle failed user=%s symbol=%s", user_id, symbol)

    async def start(self):
        self.running = True
        while self.running:
            try: await asyncio.to_thread(self.run_cycle)
            except Exception: log.exception("scheduler cycle failed")
            await asyncio.sleep(settings.scheduler_interval_seconds)

    def stop(self): self.running = False
