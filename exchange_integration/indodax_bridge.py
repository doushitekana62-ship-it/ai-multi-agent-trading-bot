"""Indodax exchange bridge using CCXT.

Credentials are supplied at runtime by the dashboard; they are never hard-coded.
The bridge supports public market-data calls and authenticated trading calls.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import ccxt

logger = logging.getLogger(__name__)


class IndodaxBridge:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.api_key = self.config.get("api_key")
        self.secret = self.config.get("secret")
        self.enable_trading = bool(self.config.get("enable_trading", False))
        self._exchange = None
        self._configure()

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        value = symbol.strip().upper().replace("_", "-")
        if "/" in value:
            return value
        if "-" in value:
            base, quote = value.split("-", 1)
            return f"{base}/{quote}"
        # Indodax commonly uses BTC/IDR; default an unqualified asset to IDR.
        return f"{value}/IDR"

    def _configure(self) -> None:
        params: Dict[str, Any] = {"enableRateLimit": True}
        if self.api_key and self.secret:
            params.update({"apiKey": self.api_key, "secret": self.secret})
        self._exchange = ccxt.indodax(params)

    @property
    def exchange(self):
        if self._exchange is None:
            self._configure()
        return self._exchange

    def is_configured(self) -> bool:
        return bool(self.api_key and self.secret)

    def test_connection(self) -> Dict[str, Any]:
        markets = self.exchange.load_markets()
        return {
            "connected": True,
            "authenticated": self.is_configured(),
            "markets": len(markets),
            "exchange": "indodax",
        }

    def get_current_price(self, symbol: str) -> Optional[float]:
        ticker = self.exchange.fetch_ticker(self.normalize_symbol(symbol))
        last = ticker.get("last")
        return float(last) if last is not None else None

    def get_historical_data(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> List[Dict[str, Any]]:
        rows = self.exchange.fetch_ohlcv(self.normalize_symbol(symbol), timeframe=timeframe, limit=limit)
        return [
            {
                "timestamp": row[0],
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            }
            for row in rows
        ]

    def get_account_value(self) -> float:
        self._require_trading()
        balance = self.exchange.fetch_balance()
        total = balance.get("total", {})
        # Dashboard portfolio value is denominated in IDR for Indodax.
        return float(total.get("IDR", 0.0) or 0.0)

    def get_balance(self) -> Dict[str, Any]:
        self._require_trading()
        return self.exchange.fetch_balance()

    def submit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "market",
    ) -> Optional[Dict[str, Any]]:
        self._require_trading()
        normalized = self.normalize_symbol(symbol)
        side = side.lower()
        if side not in {"buy", "sell"}:
            raise ValueError(f"Unsupported order side: {side}")
        if quantity <= 0:
            raise ValueError("Order quantity must be > 0")
        return self.exchange.create_order(normalized, order_type.lower(), side, quantity)

    def _require_trading(self) -> None:
        if not self.is_configured():
            raise RuntimeError("Indodax API credentials are not configured")
        if not self.enable_trading:
            raise RuntimeError("Indodax trading is disabled; enable it explicitly from the dashboard")
