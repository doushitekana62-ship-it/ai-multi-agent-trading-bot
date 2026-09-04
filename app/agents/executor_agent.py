from datetime import datetime, timezone
from app.supabase_client import get_supabase
from app.trading.gateway import TradingGateway
from app.trading.paper_gateway import PaperGateway
from app.trading.live_gateway import LiveGateway

class ExecutorAgent:
    """The only agent allowed to call a trading gateway."""
    def __init__(self, mode: str):
        if mode == "paper": self.gateway: TradingGateway = PaperGateway()
        elif mode == "live": self.gateway = LiveGateway()
        else: raise ValueError("mode must be paper or live")
        self.mode, self.db = mode, get_supabase()

    def _account(self, user_id):
        account = self.db.table("trading_accounts").select("*").eq("user_id", user_id).eq("mode", self.mode).maybe_single().execute().data
        if not account: raise RuntimeError("Trading account is not initialized")
        return account

    def open_position(self, user_id, signal):
        account = self._account(user_id)
        order = self.gateway.buy(signal.symbol, signal.entry_price, signal.quantity)
        total_cost = order.price * order.quantity + order.fee
        if self.mode == "paper":
            if float(account["cash_balance"]) < total_cost: raise RuntimeError("Insufficient paper balance")
            self.db.table("trading_accounts").update({"cash_balance": float(account["cash_balance"]) - total_cost}).eq("id", account["id"]).execute()
        row = {"user_id": user_id, "mode": self.mode, "symbol": signal.symbol, "entry_price": order.price,
               "tp_price": signal.tp_price, "sl_price": signal.sl_price, "quantity": signal.quantity,
               "status": "open", "opened_at": datetime.now(timezone.utc).isoformat(), "pnl": 0,
               "fee": order.fee, "order_id": order.order_id}
        position = self.db.table("positions").insert(row).execute().data[0]
        self.db.table("trade_logs").insert({"user_id": user_id, "position_id": position["id"], "mode": self.mode,
                                             "action": "open", "detail": {"order_id": order.order_id, "price": order.price, "quantity": order.quantity, "fee": order.fee}}).execute()
        return position

    def close_position(self, user_id, position, price, reason):
        order = self.gateway.sell(position["symbol"], price, float(position["quantity"]))
        gross = (order.price - float(position["entry_price"])) * float(position["quantity"])
        pnl = gross - float(position.get("fee") or 0) - order.fee
        status = {"tp_hit": "closed_tp", "sl_hit": "closed_sl", "manual": "closed_manual"}.get(reason, "closed_manual")
        result = self.db.table("positions").update({"status": status, "closed_at": datetime.now(timezone.utc).isoformat(),
            "exit_price": order.price, "pnl": pnl, "exit_order_id": order.order_id}).eq("id", position["id"]).eq("user_id", user_id).eq("mode", self.mode).eq("status", "open").execute()
        if not result.data: raise RuntimeError("Position was already closed")
        if self.mode == "paper":
            account = self._account(user_id)
            proceeds = order.price * order.quantity - order.fee
            self.db.table("trading_accounts").update({"cash_balance": float(account["cash_balance"]) + proceeds}).eq("id", account["id"]).execute()
        self.db.table("trade_logs").insert({"user_id": user_id, "position_id": position["id"], "mode": self.mode,
                                             "action": reason, "detail": {"exit_price": order.price, "pnl": pnl, "fee": order.fee}}).execute()
        return result.data[0]
