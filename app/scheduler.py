import asyncio
import logging
from datetime import datetime, timezone, timedelta
from app.agents.forecast_agent import ForecastAgent
from app.agents.scalping_library import ScalpingLibraryAgent
from app.agents.executor_agent import ExecutorAgent
from app.agents.regime_engine import RegimeEngine
from app.agents.signal_engine import SignalEngine
from app.agents.risk_engine import RiskEngine
from app.config import settings
from app.indodax.client import IndodaxClient
from app.indodax.market_data import MarketDataService
from app.supabase_client import execute_data, execute_one, get_supabase

log = logging.getLogger(__name__)


class TradingScheduler:
    def __init__(self):
        self.market = IndodaxClient()
        self.micro = MarketDataService(self.market)
        self.forecast = ForecastAgent(settings.min_signal_confidence)
        self.regime = RegimeEngine()
        self.signal = SignalEngine(settings.signal_min_score, settings.paper_fee_percent, settings.paper_slippage_percent)
        self.risk = RiskEngine(settings.daily_loss_limit_percent, settings.max_drawdown_percent,
                               settings.max_total_open_risk_percent, settings.max_loss_streak, settings.cooldown_minutes)
        self.running = False

    def _ensure_account(self, db, user_id, mode):
        account = execute_one(db.table("trading_accounts").select("*").eq("user_id", user_id).eq("mode", mode))
        if account:
            today = datetime.now(timezone.utc).date().isoformat()
            if str(account.get("daily_start_date")) != today:
                start = float(account.get("cash_balance") or 0)
                peak = max(float(account.get("peak_equity") or 0), start)
                execute_data(db.table("trading_accounts").update({"daily_start_date": today,
                    "daily_start_balance": start, "peak_equity": peak}).eq("id", account["id"]), [])
                account.update({"daily_start_date": today, "daily_start_balance": start, "peak_equity": peak})
            return account
        initial = settings.paper_initial_balance if mode == "paper" else 0.0
        rows = execute_data(db.table("trading_accounts").insert({"user_id": user_id, "mode": mode,
            "initial_balance": initial, "cash_balance": initial, "daily_start_balance": initial,
            "peak_equity": initial}), []) or []
        if rows:
            return rows[0] if isinstance(rows, list) else rows
        account = execute_one(db.table("trading_accounts").select("*").eq("user_id", user_id).eq("mode", mode))
        if not account:
            raise RuntimeError("Trading account could not be initialized")
        return account

    def _daily_pnl(self, db, user_id, mode):
        today = datetime.now(timezone.utc).date().isoformat()
        rows = execute_data(db.table("positions").select("pnl").eq("user_id", user_id).eq("mode", mode)
            .gte("closed_at", today), []) or []
        return sum(float(x.get("pnl") or 0) for x in rows)

    def _loss_streak(self, db, user_id, mode):
        rows = execute_data(db.table("positions").select("pnl,status,closed_at,symbol").eq("user_id", user_id)
            .eq("mode", mode).neq("status", "open").order("closed_at", desc=True).limit(10), []) or []
        streak = 0
        for row in rows:
            if float(row.get("pnl") or 0) < 0: streak += 1
            else: break
        return streak

    def _cooldown_until(self, db, user_id, mode):
        rows = execute_data(db.table("positions").select("closed_at").eq("user_id", user_id).eq("mode", mode)
            .neq("status", "open").lt("pnl", 0).order("closed_at", desc=True).limit(1), []) or []
        if not rows or not rows[0].get("closed_at"): return None
        created = datetime.fromisoformat(str(rows[0]["closed_at"]).replace("Z", "+00:00"))
        until = created + timedelta(minutes=settings.cooldown_minutes)
        return until.isoformat() if until > datetime.now(timezone.utc) else None

    def _pair_quarantined(self, db, user_id, mode, symbol):
        row = execute_one(db.table("pair_quarantine").select("locked_until").eq("user_id", user_id)
            .eq("mode", mode).eq("symbol", symbol))
        if not row or not row.get("locked_until"): return False
        try:
            return datetime.fromisoformat(str(row["locked_until"]).replace("Z", "+00:00")) > datetime.now(timezone.utc)
        except (TypeError, ValueError):
            return True

    @staticmethod
    def _ticker_map(tickers):
        return {str(k).replace("_", "").lower(): v for k, v in (tickers or {}).items()}

    @staticmethod
    def _btc_return(db):
        rows = execute_data(db.table("market_ticks").select("price").eq("symbol", "btcidr")
            .order("created_at", desc=True).limit(2), []) or []
        if len(rows) < 2 or float(rows[1]["price"]) <= 0: return 0.0
        return (float(rows[0]["price"]) / float(rows[1]["price"]) - 1) * 100

    @staticmethod
    def _support_resistance_score(prices):
        if len(prices) < 10: return 0.5
        low, high, price = min(prices[-30:]), max(prices[-30:]), prices[-1]
        if high <= low: return 0.5
        position = (price - low) / (high - low)
        return 0.7 if position >= 0.65 else (0.35 if position <= 0.2 else 0.5)

    def _health(self, db, user_id, mode, state, error=None):
        try:
            execute_data(db.table("bot_health").upsert({"user_id": user_id, "mode": mode, "state": state,
                "market_data_healthy": error is None, "db_healthy": True,
                "last_cycle_at": datetime.now(timezone.utc).isoformat(), "last_error": error},
                on_conflict="user_id,mode"), [])
        except Exception:
            log.exception("health update failed user=%s mode=%s", user_id, mode)

    def _record_decision(self, db, user_id, mode, symbol, decision):
        execute_data(db.table("signal_decisions").insert({"user_id": user_id, "mode": mode, "symbol": symbol,
            "action": decision.action, "score": decision.score, "expected_edge_percent": decision.expected_edge_percent,
            "reasons": decision.reasons, "features": decision.features}), [])

    def run_cycle(self):
        db = get_supabase()
        users = execute_data(db.table("users_settings").select(
            "id,risk_per_trade,compounding_enabled,trading_mode,bot_enabled,daily_loss_limit_percent"), []) or []
        try:
            ticker_map = self._ticker_map(self.market.get_ticker_all())
        except Exception:
            ticker_map = {}
            log.exception("ticker_all failed")

        for user in users:
            if not user.get("bot_enabled", False): continue
            user_id = str(user["id"])
            mode = user.get("trading_mode", "paper") if user.get("trading_mode") in {"paper", "live"} else "paper"
            try:
                account = self._ensure_account(db, user_id, mode)
                self._health(db, user_id, mode, "SCANNING")
                allocations = execute_data(db.table("allocated_coins").select("symbol,allocation_percent")
                    .eq("user_id", user_id).eq("is_active", True).order("symbol").limit(settings.max_allocated_coins), []) or []
                volumes = [float(ticker_map.get(str(a["symbol"]).lower(), {}).get("vol_idr") or 0) for a in allocations]
                max_volume = max(volumes or [1.0])
                btc_lead = self._btc_return(db)
                daily_pnl = self._daily_pnl(db, user_id, mode)
                loss_streak = self._loss_streak(db, user_id, mode)
                cooldown_until = self._cooldown_until(db, user_id, mode)
                open_positions = execute_data(db.table("positions").select("*").eq("user_id", user_id)
                    .eq("mode", mode).eq("status", "open"), []) or []
                prices_by_symbol = {s: float(ticker_map.get(s, {}).get("last") or 0) for s in ticker_map}
                equity = float(account.get("cash_balance") or 0) + sum(
                    float(p["quantity"]) * prices_by_symbol.get(str(p["symbol"]).lower(), float(p["entry_price"])) for p in open_positions)
                peak_equity = max(float(account.get("peak_equity") or account.get("initial_balance") or equity), equity)
                if peak_equity > float(account.get("peak_equity") or 0):
                    execute_data(db.table("trading_accounts").update({"peak_equity": peak_equity}).eq("id", account["id"]), [])
                open_risk = sum(max(0.0, (float(p["entry_price"]) - float(p["sl_price"])) * float(p["quantity"])) /
                                max(equity, 1) * 100 for p in open_positions)
                risk_base = self.risk.evaluate(daily_pnl, float(account.get("daily_start_balance") or 0), equity,
                    peak_equity, open_risk, loss_streak, cooldown_until)

                for alloc in allocations:
                    symbol = str(alloc["symbol"]).lower()
                    try:
                        ticker = ticker_map.get(symbol) or self.market.get_ticker(symbol)
                        price = float(ticker.get("last") or ticker.get("price") or 0)
                        if price <= 0: continue
                        execute_data(db.table("market_ticks").insert({"symbol": symbol, "price": price}), [])
                        ticks = execute_data(db.table("market_ticks").select("price,created_at").eq("symbol", symbol)
                            .order("created_at", desc=True).limit(240), []) or []
                        prices = [float(x["price"]) for x in reversed(ticks)]
                        if len(prices) < 30: continue
                        snapshot = self.micro.snapshot(symbol, {"price": price, "buy": ticker.get("buy", 0), "sell": ticker.get("sell", 0)})
                        execute_data(db.table("market_snapshots").insert({"user_id": user_id, "mode": mode, "symbol": symbol,
                            "price": price, "bid": snapshot.bid, "ask": snapshot.ask, "spread_percent": snapshot.spread_percent,
                            "bid_depth": snapshot.bid_depth, "ask_depth": snapshot.ask_depth, "book_imbalance": snapshot.book_imbalance,
                            "data_quality": 1.0}), [])
                        forecast = self.forecast.analyze(symbol, prices)
                        regime = self.regime.classify(prices, 0)
                        liquidity = min(1.0, float(ticker.get("vol_idr") or 0) / max_volume)
                        decision = self.signal.evaluate(forecast, regime, snapshot.spread_percent, snapshot.book_imbalance,
                            btc_lead, liquidity, self._support_resistance_score(prices), 1.0,
                            cooldown=bool(cooldown_until), exposure_available=risk_base.allowed)
                        self._record_decision(db, user_id, mode, symbol, decision)
                        if forecast:
                            execute_data(db.table("forecast_signals").insert({"user_id": user_id, "mode": mode, "symbol": symbol,
                                "suggested_tp": forecast.suggested_tp, "suggested_sl": forecast.suggested_sl,
                                "confidence": forecast.confidence, "action": forecast.action,
                                "indicators": {**forecast.indicators, "regime": regime.name if regime else None,
                                    "signal_score": decision.score, "expected_edge_percent": decision.expected_edge_percent}}), [])
                        open_pos = next((p for p in open_positions if str(p["symbol"]).lower() == symbol), None)
                        if open_pos:
                            if price >= float(open_pos["tp_price"]): ExecutorAgent(mode).close_position(user_id, open_pos, price, "tp_hit")
                            elif price <= float(open_pos["sl_price"]): ExecutorAgent(mode).close_position(user_id, open_pos, price, "sl_hit")
                            continue
                        if decision.action != "OPEN" or not risk_base.allowed or self._pair_quarantined(db, user_id, mode, symbol): continue
                        library = ScalpingLibraryAgent(float(user.get("risk_per_trade") or settings.default_risk_per_trade),
                            float(user.get("daily_loss_limit_percent") or settings.daily_loss_limit_percent),
                            settings.min_signal_confidence, bool(user.get("compounding_enabled", True)))
                        signal = library.validate(forecast, float(alloc["allocation_percent"]), equity, daily_pnl, False)
                        if signal:
                            quantity = signal.quantity * risk_base.risk_multiplier
                            projected_risk = max(0.0, (signal.entry_price - signal.sl_price) * quantity) / max(equity, 1) * 100
                            if open_risk + projected_risk > settings.max_total_open_risk_percent: continue
                            adjusted = signal.__class__(signal.symbol, snapshot.ask or signal.entry_price, signal.tp_price,
                                signal.sl_price, quantity, signal.allocation_percent, signal.compound_multiplier)
                            ExecutorAgent(mode).open_position(user_id, adjusted)
                            open_risk += projected_risk
                    except Exception as exc:
                        log.exception("cycle failed user=%s symbol=%s", user_id, symbol)
                        self._health(db, user_id, mode, "SAFE_MODE", str(exc))
            except Exception as exc:
                log.exception("cycle failed user=%s", user_id)
                self._health(db, user_id, mode, "SAFE_MODE", str(exc))

    async def start(self):
        self.running = True
        delay = settings.scheduler_interval_seconds
        while self.running:
            try:
                await asyncio.to_thread(self.run_cycle)
                delay = settings.scheduler_interval_seconds
            except Exception:
                log.exception("scheduler cycle failed")
                delay = min(max(delay * 2, settings.scheduler_interval_seconds), 60)
            await asyncio.sleep(delay)

    def stop(self):
        self.running = False
