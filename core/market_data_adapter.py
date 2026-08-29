"""Market Data Adapter - one interface for all supported exchanges."""

import logging
import time
from datetime import datetime, timezone
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

    def configure(self, config: Dict[str, Any]) -> None:
        self.config = dict(config or {})
        self.exchange_type = str(self.config.get("exchange_type", "paper")).lower()
        self._alpaca_client = None
        self._indodax_client = None

    def get_market_data(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> MarketDataResponse:
        symbol = symbol.upper()
        attempts = self.max_retries if self.enable_retry else 1
        for attempt in range(attempts):
            try:
                response = self._fetch_market_data(symbol, timeframe, limit)
                if response.success:
                    return response
            except Exception as exc:
                logger.exception("Market-data attempt failed: %s", exc)
            if attempt + 1 < attempts:
                time.sleep(self.retry_delay * (attempt + 1))
        return self._create_error_response(symbol, f"Failed to fetch market data after {attempts} attempt(s)")

    def _fetch_market_data(self, symbol: str, timeframe: str, limit: int) -> MarketDataResponse:
        if self.exchange_type in {"paper", "indodax"}:
            return self._fetch_from_indodax(symbol, timeframe, limit, self.exchange_type)
        if self.exchange_type == "alpaca":
            return self._fetch_from_alpaca(symbol, timeframe, limit)
        return self._create_error_response(symbol, f"Unknown exchange type: {self.exchange_type}")

    def _fetch_from_indodax(self, symbol: str, timeframe: str, limit: int, source: str) -> MarketDataResponse:
        try:
            from exchange_integration.indodax_bridge import IndodaxBridge
            if self._indodax_client is None:
                self._indodax_client = IndodaxBridge(self.config.get("indodax", {}))
            price = self._indodax_client.get_current_price(symbol)
            if price is None or price <= 0:
                return self._create_error_response(symbol, "Invalid price from Indodax")
            ohlcv = self._indodax_client.get_historical_data(symbol, timeframe, limit) or []
            valid = []
            for candle in ohlcv:
                try:
                    ts = float(candle["timestamp"])
                    if ts > 1_000_000_000_000:
                        ts /= 1000.0
                    candle = dict(candle)
                    candle["timestamp"] = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                    if float(candle["open"]) > 0 and float(candle["high"]) > 0 and float(candle["low"]) > 0 and float(candle["close"]) > 0:
                        valid.append(candle)
                except (KeyError, TypeError, ValueError, OverflowError):
                    continue
            valid.sort(key=lambda x: x["timestamp"])
            if not valid:
                return self._create_error_response(symbol, "Indodax returned no valid OHLCV candles")
            last_ts = datetime.fromisoformat(valid[-1]["timestamp"])
            return MarketDataResponse(True, symbol, price, valid,
                sum(float(c.get("volume", 0)) for c in valid[-24:]),
                max((float(c.get("high", price)) for c in valid[-24:]), default=price),
                min((float(c.get("low", price)) for c in valid[-24:]), default=price),
                last_ts, source=source)
        except Exception as exc:
            return self._create_error_response(symbol, f"Indodax market-data error: {exc}")

    def _fetch_from_alpaca(self, symbol: str, timeframe: str, limit: int) -> MarketDataResponse:
        try:
            from exchange_integration.alpaca_bridge import AlpacaBridge
            if self._alpaca_client is None:
                self._alpaca_client = AlpacaBridge(self.config.get("alpaca", {}))
            price = self._alpaca_client.get_current_price(symbol)
            ohlcv = self._alpaca_client.get_historical_data(symbol, timeframe, limit) or []
            recent = ohlcv[-24:] if len(ohlcv) >= 24 else ohlcv
            timestamp = datetime.now(timezone.utc)
            if ohlcv:
                try:
                    ts = float(ohlcv[-1]["timestamp"])
                    if ts > 1_000_000_000_000: ts /= 1000.0
                    timestamp = datetime.fromtimestamp(ts, tz=timezone.utc)
                except (KeyError, TypeError, ValueError, OverflowError):
                    pass
            return MarketDataResponse(True, symbol, price, ohlcv,
                sum(c.get("volume", 0) for c in recent),
                max((c.get("high", price) for c in recent), default=price),
                min((c.get("low", price) for c in recent), default=price),
                timestamp, source="alpaca")
        except Exception as exc:
            return self._create_error_response(symbol, f"Alpaca error: {exc}")

    def _create_error_response(self, symbol: str, error: str) -> MarketDataResponse:
        return MarketDataResponse(False, symbol, None, None, None, None, None, datetime.now(timezone.utc), error, "error")

    def get_fear_greed_index(self) -> Optional[float]:
        try:
            import requests
            response = requests.get("https://api.alternative.me/fng/", params={"limit": 1}, timeout=5)
            response.raise_for_status()
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