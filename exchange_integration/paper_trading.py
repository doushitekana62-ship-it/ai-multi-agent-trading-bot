"""Deterministic spot paper-trading engine.

Paper trading uses the same public Indodax market prices that the future live
adapter will use. It never sends a private order. Tests can inject prices with
``set_test_price`` so execution behaviour is deterministic.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class PaperPosition:
    symbol: str
    side: str
    entry_price: float
    quantity: float
    entry_time: datetime
    current_price: float
    unrealized_pnl: float
    realized_pnl: float = 0.0
    entry_fee: float = 0.0


class PaperTrading:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.initial_balance = float(self.config.get("initial_balance", 10_000_000.0))
        self.balance = self.initial_balance
        self.portfolio_value = self.initial_balance
        self.quote_currency = str(self.config.get("quote_currency", "IDR")).upper()
        self.fee_rate = float(self.config.get("fee_rate", 0.0015))
        self.slippage_rate = float(self.config.get("slippage_rate", 0.0002))
        self.price_ttl_seconds = float(self.config.get("price_ttl_seconds", 2.0))
        self.http_timeout = float(self.config.get("http_timeout", 5.0))
        self.positions: Dict[str, PaperPosition] = {}
        self.trade_history: List[Dict[str, Any]] = []
        self.total_pnl = 0.0
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.price_cache: Dict[str, tuple[float, float]] = {}
        self._test_prices: Dict[str, float] = {}
        self._load_data()

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        value = symbol.upper().replace("-", "_").replace("/", "_")
        if "_" not in value and value.endswith("IDR") and len(value) > 3:
            value = f"{value[:-3]}_IDR"
        return value.lower()

    def _ticker_url(self, symbol: str) -> str:
        return f"https://indodax.com/api/{self._normalize_symbol(symbol)}/ticker"

    def set_test_price(self, symbol: str, price: float) -> None:
        if price <= 0:
            raise ValueError("Test price must be positive")
        self._test_prices[symbol.upper()] = float(price)

    def get_price(self, symbol: str) -> Optional[float]:
        key = symbol.upper()
        if key in self._test_prices:
            return self._test_prices[key]
        now = time.time()
        cached = self.price_cache.get(key)
        if cached and now - cached[0] < self.price_ttl_seconds:
            return cached[1]
        try:
            response = requests.get(self._ticker_url(symbol), timeout=self.http_timeout)
            response.raise_for_status()
            payload = response.json()
            ticker = payload.get("ticker", payload)
            price = float(ticker["last"])
            if price <= 0:
                raise ValueError("non-positive market price")
            self.price_cache[key] = (now, price)
            return price
        except Exception as exc:
            logger.error("Market price unavailable for %s: %s", symbol, exc)
            return None

    def execute_order(self, symbol: str, side: str, quantity: float, price: float) -> bool:
        symbol = symbol.upper()
        side = side.upper()
        quantity = float(quantity)
        price = float(price)
        if side not in {"BUY", "SELL"} or quantity <= 0 or price <= 0:
            return False

        if side == "BUY":
            if symbol in self.positions:
                logger.warning("Duplicate paper position rejected: %s", symbol)
                return False
            execution_price = price * (1 + self.slippage_rate)
            gross = quantity * execution_price
            fee = gross * self.fee_rate
            total_cost = gross + fee
            if total_cost > self.balance:
                logger.warning("Insufficient balance for %s", symbol)
                return False
            self.balance -= total_cost
            self.positions[symbol] = PaperPosition(
                symbol, "BUY", execution_price, quantity,
                datetime.now(timezone.utc), execution_price, 0.0,
                entry_fee=fee,
            )
            self._update_portfolio_value()
            self._save_data()
            return True

        position = self.positions.get(symbol)
        if position is None or quantity > position.quantity + 1e-12:
            return False

        original_quantity = position.quantity
        execution_price = price * (1 - self.slippage_rate)
        gross = quantity * execution_price
        exit_fee = gross * self.fee_rate
        allocated_entry_fee = position.entry_fee * (quantity / original_quantity)
        gross_price_pnl = (execution_price - position.entry_price) * quantity
        pnl = gross_price_pnl - allocated_entry_fee - exit_fee

        self.balance += gross - exit_fee
        self.total_pnl += pnl
        self.total_trades += 1
        if pnl > 0:
            self.winning_trades += 1
        elif pnl < 0:
            self.losing_trades += 1

        self.trade_history.append({
            "symbol": symbol,
            "side": "SELL",
            "entry_price": position.entry_price,
            "exit_price": execution_price,
            "quantity": quantity,
            "entry_fee": allocated_entry_fee,
            "exit_fee": exit_fee,
            "fee": allocated_entry_fee + exit_fee,
            "gross_price_pnl": gross_price_pnl,
            "pnl": pnl,
            "pnl_percent": pnl / (position.entry_price * quantity) * 100,
            "entry_time": position.entry_time.isoformat(),
            "exit_time": datetime.now(timezone.utc).isoformat(),
        })

        if quantity >= original_quantity - 1e-12:
            del self.positions[symbol]
        else:
            position.quantity -= quantity
            position.entry_fee -= allocated_entry_fee

        self._update_portfolio_value()
        self._save_data()
        return True

    def _update_portfolio_value(self) -> None:
        positions_value = 0.0
        for symbol, position in self.positions.items():
            current_price = self.get_price(symbol)
            if current_price is None:
                current_price = position.current_price
            position.current_price = current_price
            position.unrealized_pnl = (current_price - position.entry_price) * position.quantity - position.entry_fee
            positions_value += current_price * position.quantity
        self.portfolio_value = self.balance + positions_value

    def get_portfolio_value(self) -> float:
        self._update_portfolio_value()
        return self.portfolio_value

    def get_positions(self) -> List[Dict[str, Any]]:
        return [{
            "symbol": p.symbol, "side": p.side, "entry_price": p.entry_price,
            "current_price": p.current_price, "quantity": p.quantity,
            "unrealized_pnl": p.unrealized_pnl,
            "pnl_percent": p.unrealized_pnl / (p.entry_price * p.quantity) * 100,
        } for p in self.positions.values()]

    def get_performance(self) -> Dict[str, Any]:
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.winning_trades / self.total_trades if self.total_trades else 0.0,
            "total_pnl": self.total_pnl,
            "balance": self.balance,
            "portfolio_value": self.get_portfolio_value(),
            "total_return": (self.portfolio_value - self.initial_balance) / self.initial_balance * 100,
        }

    def close_all_positions(self) -> None:
        for symbol in list(self.positions):
            price = self.get_price(symbol)
            if price is not None:
                self.execute_order(symbol, "SELL", self.positions[symbol].quantity, price)

    def _save_data(self) -> None:
        try:
            os.makedirs("data", exist_ok=True)
            payload = {
                "initial_balance": self.initial_balance,
                "balance": self.balance,
                "total_pnl": self.total_pnl,
                "total_trades": self.total_trades,
                "winning_trades": self.winning_trades,
                "losing_trades": self.losing_trades,
                "trade_history": self.trade_history,
                "positions": [{
                    "symbol": p.symbol,
                    "side": p.side,
                    "entry_price": p.entry_price,
                    "quantity": p.quantity,
                    "entry_fee": p.entry_fee,
                    "entry_time": p.entry_time.isoformat(),
                    "current_price": p.current_price,
                } for p in self.positions.values()],
            }
            with open("data/paper_trading.json", "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
        except Exception as exc:
            logger.error("Unable to save paper state: %s", exc)

    def _load_data(self) -> None:
        try:
            if not os.path.exists("data/paper_trading.json"):
                return
            with open("data/paper_trading.json", encoding="utf-8") as handle:
                data = json.load(handle)
            self.balance = float(data.get("balance", self.initial_balance))
            self.total_pnl = float(data.get("total_pnl", 0.0))
            self.total_trades = int(data.get("total_trades", 0))
            self.winning_trades = int(data.get("winning_trades", 0))
            self.losing_trades = int(data.get("losing_trades", 0))
            self.trade_history = data.get("trade_history", [])
            for item in data.get("positions", []):
                self.positions[item["symbol"]] = PaperPosition(
                    symbol=item["symbol"],
                    side=item.get("side", "BUY"),
                    entry_price=float(item["entry_price"]),
                    quantity=float(item["quantity"]),
                    entry_time=datetime.fromisoformat(item["entry_time"]),
                    current_price=float(item.get("current_price", item["entry_price"])),
                    unrealized_pnl=0.0,
                    entry_fee=float(item.get("entry_fee", 0.0)),
                )
        except Exception as exc:
            logger.warning("Unable to load paper state: %s", exc)
