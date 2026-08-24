"""Order execution and position management."""

import logging
from datetime import datetime
from typing import Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum

from exchange_integration.alpaca_bridge import AlpacaBridge
from exchange_integration.paper_trading import PaperTrading
from exchange_integration.indodax_bridge import IndodaxBridge

logger = logging.getLogger(__name__)

class OrderStatus(Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

@dataclass
class Order:
    order_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    status: str
    created_at: datetime
    filled_at: Optional[datetime]
    filled_quantity: float
    filled_price: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    metadata: Dict[str, Any]

class Executor:
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.exchange_mode = str(self.config.get("exchange_mode", "paper")).lower()
        self.paper_trading = PaperTrading(self.config.get("paper", {}))
        self.alpaca_bridge = AlpacaBridge(self.config.get("alpaca", {}))
        self.indodax_bridge: Optional[IndodaxBridge] = None
        self.active_orders: Dict[str, Order] = {}
        self.order_history = []
        self.active_positions: Dict[str, Dict[str, Any]] = {}
        self.max_open_positions = int(self.config.get("max_open_positions", 5))
        self.daily_loss_limit = float(self.config.get("daily_loss_limit", 0.05))
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.order_id_counter = 0

    def configure_exchange(self, exchange_mode: str, credentials: Optional[Dict[str, Any]] = None) -> None:
        self.exchange_mode = exchange_mode.lower()
        credentials = credentials or {}
        if self.exchange_mode == "indodax":
            self.indodax_bridge = IndodaxBridge({
                "api_key": credentials.get("api_key"),
                "secret": credentials.get("api_secret") or credentials.get("secret"),
                "enable_trading": credentials.get("enable_trading", False),
            })
        logger.info("Executor exchange configured: %s", self.exchange_mode)

    def execute(self, symbol: str, action: str, confidence: float, position_size: float,
                stop_loss: Optional[float] = None, take_profit: Optional[float] = None) -> Optional[Order]:
        action = action.upper()
        if action == "HOLD" or not 0 < position_size <= 1:
            return None
        if self.daily_pnl <= -self.daily_loss_limit:
            logger.warning("Daily loss limit reached: %.2f", self.daily_pnl)
            return None
        if len(self.active_positions) >= self.max_open_positions and symbol not in self.active_positions:
            return None
        side = "BUY" if action in {"BUY", "STRONG_BUY"} else "SELL"
        current_price = self._get_current_price(symbol)
        if not current_price or current_price <= 0:
            return None
        if side == "SELL" and symbol in self.active_positions:
            quantity = float(self.active_positions[symbol]["quantity"])
        else:
            quantity = (self._get_portfolio_value() * position_size) / current_price
        if quantity <= 0:
            return None
        order = self._create_order(symbol, side, quantity, current_price, stop_loss, take_profit)
        executed = self._execute_order(order)
        if executed:
            if side == "SELL":
                self._close_position_record(symbol)
            else:
                self._track_position(executed)
            return executed
        return None

    def _create_order(self, symbol, side, quantity, price, stop_loss, take_profit):
        self.order_id_counter += 1
        return Order(f"ORD_{self.order_id_counter:06d}", symbol, side, quantity, price,
                     OrderStatus.PENDING.value, datetime.now(), None, 0.0, 0.0,
                     stop_loss, take_profit, {})

    def _execute_order(self, order: Order) -> Optional[Order]:
        try:
            if self.exchange_mode == "paper":
                result = {"paper": True} if self.paper_trading.execute_order(order.symbol, order.side, order.quantity, order.price) else None
            elif self.exchange_mode == "indodax":
                if not self.indodax_bridge:
                    raise RuntimeError("Indodax is not configured")
                result = self.indodax_bridge.submit_order(order.symbol, order.side, order.quantity, "market")
            elif self.exchange_mode == "alpaca":
                result = self.alpaca_bridge.submit_order(order.symbol, order.side, order.quantity, "market")
            else:
                raise ValueError(f"Unsupported exchange mode: {self.exchange_mode}")
            if result is None:
                order.status = OrderStatus.REJECTED.value
                return None
            order.status = OrderStatus.FILLED.value
            order.filled_at = datetime.now()
            order.filled_quantity = order.quantity
            order.filled_price = order.price
            order.metadata["exchange_result"] = result
            self.order_history.append(order)
            self.daily_trades += 1
            return order
        except Exception as exc:
            order.status = OrderStatus.REJECTED.value
            logger.exception("Order execution failed: %s", exc)
            return None

    def _track_position(self, order: Order) -> None:
        self.active_positions[order.symbol] = {
            "symbol": order.symbol, "side": order.side, "entry_price": order.price,
            "quantity": order.quantity, "stop_loss": order.stop_loss,
            "take_profit": order.take_profit, "entry_time": datetime.now(),
            "order_id": order.order_id, "current_pnl": 0.0,
        }

    def _close_position_record(self, symbol: str) -> None:
        self.active_positions.pop(symbol, None)

    def monitor_positions(self):
        for symbol, position in list(self.active_positions.items()):
            current_price = self._get_current_price(symbol)
            if not current_price:
                continue
            if position["side"] == "BUY":
                position["current_pnl"] = (current_price - position["entry_price"]) / position["entry_price"]
                hit_sl = position["stop_loss"] is not None and current_price <= position["stop_loss"]
                hit_tp = position["take_profit"] is not None and current_price >= position["take_profit"]
            else:
                position["current_pnl"] = (position["entry_price"] - current_price) / position["entry_price"]
                hit_sl = position["stop_loss"] is not None and current_price >= position["stop_loss"]
                hit_tp = position["take_profit"] is not None and current_price <= position["take_profit"]
            if hit_sl or hit_tp:
                self._close_position(symbol, current_price, "STOP_LOSS" if hit_sl else "TAKE_PROFIT")

    def _close_position(self, symbol: str, price: float, reason: str):
        position = self.active_positions.get(symbol)
        if not position:
            return
        close_side = "SELL" if position["side"] == "BUY" else "BUY"
        order = self._create_order(symbol, close_side, position["quantity"], price, None, None)
        if self._execute_order(order):
            pnl = ((price - position["entry_price"]) * position["quantity"] if position["side"] == "BUY"
                   else (position["entry_price"] - price) * position["quantity"])
            self.daily_pnl += pnl / (position["entry_price"] * position["quantity"])
            self._close_position_record(symbol)

    def _get_current_price(self, symbol: str) -> Optional[float]:
        try:
            if self.exchange_mode == "paper":
                return float(self.paper_trading.get_price(symbol))
            if self.exchange_mode == "indodax":
                return self.indodax_bridge.get_current_price(symbol) if self.indodax_bridge else None
            return self.alpaca_bridge.get_current_price(symbol)
        except Exception as exc:
            logger.error("Error getting price: %s", exc)
            return None

    def _get_portfolio_value(self) -> float:
        try:
            if self.exchange_mode == "paper":
                return float(self.paper_trading.get_portfolio_value())
            if self.exchange_mode == "indodax":
                return float(self.indodax_bridge.get_account_value()) if self.indodax_bridge else 0.0
            return float(self.alpaca_bridge.get_account_value())
        except Exception as exc:
            logger.error("Error getting portfolio value: %s", exc)
            return 0.0

    def get_summary(self) -> Dict[str, Any]:
        return {"active_positions": len(self.active_positions), "total_trades": len(self.order_history),
                "daily_pnl": self.daily_pnl, "daily_trades": self.daily_trades,
                "positions": self.active_positions, "exchange_mode": self.exchange_mode}

    def reset_daily(self):
        self.daily_pnl = 0.0
        self.daily_trades = 0
