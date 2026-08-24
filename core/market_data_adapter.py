"""Market Data Adapter - one interface for all supported exchanges."""

import logging
import time
import random
import math
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MarketDataResponse:
    success: bool
    symbol: str
    current_price: Optional[float]
    ohlcv: Optional[List[Dict[str, Any]]]
    volume_24h: Optional[float]
    high_24h: Optional[float]
    low_24h: Optional[float]
    timestamp: datetime
    error: Optional[str] = None
    source: str = "unknown"


class MarketDataAdapter:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.exchange_type = str(self.config.get("exchange_type", "paper")).lower()
        self.enable_retry = self.config.get("enable_retry", True)
        self.max_retries = int(self.config.get("max_retries", 3))
        self.retry_delay = float(self.config.get("retry_delay", 1.0))
        self._alpaca_client = None
        self._indodax_client = None
        logger.info("MarketDataAdapter initialized with exchange_type=%s", self.exchange_type)

    def configure(self, config: Dict[str, Any]) -> None:
        """Apply runtime exchange configuration without restarting the process."""
        self.config = dict(config or {})
        self.exchange_type = str(self.config.get("exchange_type", "paper")).lower()
        self._alpaca_client = None
        self._indodax_client = None
        logger.info("MarketDataAdapter reconfigured: %s", self.exchange_type)

    def get_market_data(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> MarketDataResponse:
        symbol = symbol.upper()
        for attempt in range(self.max_retries if self.enable_retry else 1):
            try:
                response = self._fetch_market_data(symbol, timeframe, limit)
                if response.success:
                    return response
                logger.warning("Attempt %d failed for %s: %s", attempt + 1, symbol, response.error)
            except Exception as exc:
                logger.exception("Market-data attempt failed: %s", exc)
            if attempt + 1 < (self.max_retries if self.enable_retry else 1):
                time.sleep(self.retry_delay * (attempt + 1))
        return self._create_error_response(symbol, f"Failed to fetch market data after {self.max_retries if self.enable_retry else 1} attempt(s)")

    def _fetch_market_data(self, symbol: str, timeframe: str, limit: int) -> MarketDataResponse:
        if self.exchange_type == "paper":
            return self._fetch_from_paper(symbol, timeframe, limit)
        if self.exchange_type == "alpaca":
            return self._fetch_from_alpaca(symbol, timeframe, limit)
        if self.exchange_type == "indodax":
            return self._fetch_from_indodax(symbol, timeframe, limit)
        return self._create_error_response(symbol, f"Unknown exchange type: {self.exchange_type}")

    def _fetch_from_indodax(self, symbol: str, timeframe: str, limit: int) -> MarketDataResponse:
        try:
            from exchange_integration.indodax_bridge import IndodaxBridge
            if self._indodax_client is None:
                self._indodax_client = IndodaxBridge(self.config.get("indodax", {}))
            price = self._indodax_client.get_current_price(symbol)
            if price is None or price <= 0:
                return self._create_error_response(symbol, "Invalid price from Indodax")
            ohlcv = self._indodax_client.get_historical_data(symbol, timeframe, limit)
            recent = ohlcv[-24:] if len(ohlcv) >= 24 else ohlcv
            high_24h = max((c["high"] for c in recent), default=price)
            low_24h = min((c["low"] for c in recent), default=price)
            volume_24h = sum(c["volume"] for c in recent)
            change_percent = ((price - recent[0]["open"]) / recent[0]["open"] * 100) if recent and recent[0]["open"] else 0.0
            return MarketDataResponse(True, symbol, price, ohlcv, volume_24h, high_24h, low_24h, datetime.now(timezone.utc), source="indodax")
        except Exception as exc:
            return self._create_error_response(symbol, f"Indodax error: {exc}")

    def _fetch_from_paper(self, symbol: str, timeframe: str, limit: int) -> MarketDataResponse:
        try:
            from exchange_integration.paper_trading import PaperTrading
            paper = PaperTrading()
            price = paper.get_price(symbol)
            if price is None or price <= 0:
                return self._create_error_response(symbol, "Invalid price from paper trading")
            ohlcv = self._generate_synthetic_ohlcv(symbol, price, timeframe, limit)
            return MarketDataResponse(True, symbol, price, ohlcv, 1000000.0, price * 1.02, price * 0.98, datetime.now(timezone.utc), source="paper")
        except Exception as exc:
            return self._create_error_response(symbol, f"Paper trading error: {exc}")

    def _fetch_from_alpaca(self, symbol: str, timeframe: str, limit: int) -> MarketDataResponse:
        try:
            from exchange_integration.alpaca_bridge import AlpacaBridge
            if self._alpaca_client is None:
                self._alpaca_client = AlpacaBridge(self.config.get("alpaca", {}))
            price = self._alpaca_client.get_current_price(symbol)
            if price is None or price <= 0:
                return self._create_error_response(symbol, "Invalid price from Alpaca")
            ohlcv = self._alpaca_client.get_historical_data(symbol, timeframe, limit) or []
            recent = ohlcv[-24:] if len(ohlcv) >= 24 else ohlcv
            return MarketDataResponse(True, symbol, price, ohlcv, sum(c.get("volume", 0) for c in recent), max((c.get("high", price) for c in recent), default=price), min((c.get("low", price) for c in recent), default=price), datetime.now(timezone.utc), source="alpaca")
        except Exception as exc:
            return self._create_error_response(symbol, f"Alpaca error: {exc}")

    def _generate_synthetic_ohlcv(self, symbol: str, current_price: float, timeframe: str, limit: int) -> List[Dict[str, Any]]:
        duration_minutes = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}.get(timeframe, 60)
        ohlcv, now, base_price = [], datetime.now(timezone.utc), current_price
        for i in range(limit):
            change = random.gauss(0, 0.002)
            open_price, close_price = base_price * (1 + change * 0.5), base_price * (1 + change)
            high_price = max(open_price, close_price) * (1 + abs(random.gauss(0, 0.001)))
            low_price = min(open_price, close_price) * (1 - abs(random.gauss(0, 0.001)))
            ohlcv.append({"timestamp": now - timedelta(minutes=(limit - i) * duration_minutes), "open": round(open_price, 8), "high": round(high_price, 8), "low": round(low_price, 8), "close": round(close_price, 8), "volume": round(1000 + 500 * (1 + math.sin(i / 10)), 2)})
            base_price = close_price
        return ohlcv

    def _create_error_response(self, symbol: str, error: str) -> MarketDataResponse:
        return MarketDataResponse(False, symbol, None, None, None, None, None, datetime.now(timezone.utc), error, "error")

    def get_fear_greed_index(self) -> Optional[float]:
        try:
            import requests
            response = requests.get("https://api.alternative.me/fng/", params={"limit": 1}, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get("data"):
                    return float(data["data"][0].get("value", 50))
        except Exception as exc:
            logger.debug("Fear & Greed API error: %s", exc)
        return None


_market_data_adapter = None

def get_market_data_adapter(config: Optional[Dict] = None) -> MarketDataAdapter:
    global _market_data_adapter
    if _market_data_adapter is None:
        _market_data_adapter = MarketDataAdapter(config)
    elif config:
        _market_data_adapter.configure(config)
    return _market_data_adapter
