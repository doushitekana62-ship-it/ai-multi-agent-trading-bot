from datetime import datetime, timezone
import uuid
from app.supabase_client import execute_data, execute_one, get_supabase
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
        account = execute_one(self.db.table("trading_accounts").select("*").eq("user_id", user_id).eq("mode", self.mode))
        if not account: raise RuntimeError("Trading account is not initialized")
        return account

    def open_position(self, user_id, signal):
        existing = execute_one(self.db.table("positions").select("id").eq("user_id", user_id).eq("mode", self.mode)
            .eq("symbol", signal.symbol).eq("status", "open"))
        if existing: return existing
        account = self._account(user_id)
        client_order_id = f"{self.mode[:1]}-{uuid.uuid4().hex[:30]}"
        estimated_cost = signal.entry_price * signal.quantity
        if self.mode == "paper":
            estimated_fee = estimated_cost * PaperGateway().fee_rate
            if float(account.get("cash_balance") or 0) < estimated_cost + estimated_fee:
                raise RuntimeError("Insufficient paper balance")
        rows = execute_data(self.db.table("orders").insert({"user_id": user_id, "mode": self.mode,
            "symbol": signal.symbol, "client_order_id": client_order_id, "side": "buy", "order_type": "market",
            "status": "pending", "requested_price": signal.entry_price, "quantity": signal.quantity}), []) or []
        if not rows: raise RuntimeError("Could not create internal order record")
        order_row = rows[0] if isinstance(rows, list) else rows
        try:
            order = self.gateway.buy(signal.symbol, signal.entry_price, signal.quantity, client_order_id=client_order_id)
            total_cost = order.price * order.quantity + order.fee
            if self.mode == "paper":
                if float(account.get("cash_balance") or 0) < total_cost: raise RuntimeError("Insufficient paper balance after slippage")
                execute_data(self.db.table("trading_accounts").update({"cash_balance": float(account["cash_balance"]) - total_cost}).eq("id", account["id"]), [])
            position_rows = execute_data(self.db.table("positions").insert({"user_id": user_id, "mode": self.mode,
                "symbol": signal.symbol, "entry_price": order.price, "tp_price": signal.tp_price, "sl_price": signal.sl_price,
                "quantity": signal.quantity, "status": "open", "opened_at": datetime.now(timezone.utc).isoformat(),
                "pnl": 0, "fee": order.fee, "order_id": order.order_id}), []) or []
            if not position_rows: raise RuntimeError("Exchange order filled but position record was not created")
            position = position_rows[0] if isinstance(position_rows, list) else position_rows
            execute_data(self.db.table("orders").update({"position_id": position["id"], "exchange_order_id": order.order_id,
                "status": "filled", "executed_price": order.price, "fee": order.fee}).eq("id", order_row["id"]), [])
            execute_data(self.db.table("fills").insert({"order_id": order_row["id"], "user_id": user_id, "mode": self.mode,
                "symbol": signal.symbol, "exchange_trade_id": order.order_id, "price": order.price,
                "quantity": order.quantity, "fee": order.fee}), [])
            execute_data(self.db.table("trade_logs").insert({"user_id": user_id, "position_id": position["id"], "mode": self.mode,
                "action": "open", "detail": {"client_order_id": client_order_id, "order_id": order.order_id,
                "price": order.price, "quantity": order.quantity, "fee": order.fee}}), [])
            return position
        except Exception as exc:
            try: execute_data(self.db.table("orders").update({"status": "rejected"}).eq("id", order_row["id"]), [])
            except Exception: pass
            raise exc

    def close_position(self, user_id, position, price, reason):
        client_order_id = f"{self.mode[:1]}-{uuid.uuid4().hex[:30]}"
        order = self.gateway.sell(position["symbol"], price, float(position["quantity"]), client_order_id=client_order_id)
        gross = (order.price - float(position["entry_price"])) * float(position["quantity"])
        pnl = gross - float(position.get("fee") or 0) - order.fee
        status = {"tp_hit": "closed_tp", "sl_hit": "closed_sl", "manual": "closed_manual"}.get(reason, "closed_manual")
        result = self.db.table("positions").update({"status": status, "closed_at": datetime.now(timezone.utc).isoformat(),
            "exit_price": order.price, "pnl": pnl, "exit_order_id": order.order_id}).eq("id", position["id"]).eq("user_id", user_id)
        result = result.eq("mode", self.mode).eq("status", "open").execute()
        result_data = getattr(result, "data", None) or []
        if not result_data: raise RuntimeError("Position was already closed")
        if self.mode == "paper":
            account = self._account(user_id)
            proceeds = order.price * order.quantity - order.fee
            execute_data(self.db.table("trading_accounts").update({"cash_balance": float(account["cash_balance"]) + proceeds}).eq("id", account["id"]), [])
        execute_data(self.db.table("trade_logs").insert({"user_id": user_id, "position_id": position["id"], "mode": self.mode,
            "action": reason, "detail": {"exit_price": order.price, "pnl": pnl, "fee": order.fee, "client_order_id": client_order_id}}), [])
        return result_data[0]
