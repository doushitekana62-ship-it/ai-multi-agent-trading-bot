"""
core/unified_market_data.py

Single Source of Truth untuk semua market data.
Freshness adalah hard data-quality property, bukan sekadar dashboard metadata.
"""

import logging
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from core.market_data_adapter import MarketDataAdapter, get_market_data_adapter

logger = logging.getLogger(__name__)
DEFAULT_MAX_AGE_SECONDS = float(os.getenv("MARKET_DATA_MAX_AGE_SECONDS", "90"))


def _normalize_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric > 1_000_000_000_000:
            numeric /= 1000.0
        return datetime.fromtimestamp(numeric, tz=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if text:
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
            except ValueError:
                try:
                    numeric = float(text)
                    if numeric > 1_000_000_000_000:
                        numeric /= 1000.0
                    return datetime.fromtimestamp(numeric, tz=timezone.utc)
                except ValueError:
                    pass
    return datetime.now(timezone.utc)


@dataclass
class OHLCV:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        self.timestamp = _normalize_timestamp(self.timestamp)

    def to_dict(self) -> Dict[str, Any]:
        return {"timestamp": self.timestamp.isoformat(), "open": self.open, "high": self.high, "low": self.low, "close": self.close, "volume": self.volume}

    def is_valid(self) -> bool:
        return self.open > 0 and self.high > 0 and self.low > 0 and self.close > 0 and self.volume >= 0


@dataclass
class UnifiedMarketSnapshot:
    symbol: str
    timestamp: datetime
    timeframe: str
    current_price: float
    ohlcv_data: List[OHLCV] = field(default_factory=list)
    high_24h: Optional[float] = None
    low_24h: Optional[float] = None
    volume_24h: Optional[float] = None
    change_24h: Optional[float] = None
    change_percent_24h: Optional[float] = None
    fear_greed_index: Optional[float] = None
    market_phase: str = "NEUTRAL"
    volatility: Optional[float] = None
    data_quality_score: float = 1.0
    missing_fields: List[str] = field(default_factory=list)
    source: str = "unified_market_data"
    is_fresh: bool = True
    age_seconds: float = 0.0

    def __post_init__(self) -> None:
        self.timestamp = _normalize_timestamp(self.timestamp)

    def refresh_freshness(self, max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS) -> bool:
        self.age_seconds = max(0.0, (datetime.now(timezone.utc) - self.timestamp).total_seconds())
        self.is_fresh = self.age_seconds <= float(max_age_seconds)
        return self.is_fresh

    def to_dict(self) -> Dict[str, Any]:
        self.refresh_freshness()
        return {
            "symbol": self.symbol, "timestamp": self.timestamp.isoformat(), "timeframe": self.timeframe,
            "current_price": self.current_price, "unified_price": self.current_price,
            "high_24h": self.high_24h, "low_24h": self.low_24h, "volume_24h": self.volume_24h,
            "change_24h": self.change_24h, "change_percent_24h": self.change_percent_24h,
            "fear_greed_index": self.fear_greed_index, "market_phase": self.market_phase,
            "volatility": self.volatility, "data_quality_score": self.data_quality_score,
            "missing_fields": self.missing_fields, "source": self.source, "is_fresh": self.is_fresh,
            "age_seconds": self.age_seconds, "ohlcv": [o.to_dict() for o in self.ohlcv_data[-100:]],
            "ohlcv_count": len(self.ohlcv_data)
        }

    def get_price(self) -> float:
        return self.current_price

    def get_ohlcv(self, limit: Optional[int] = None) -> List[OHLCV]:
        return self.ohlcv_data[-limit:] if limit and limit > 0 else self.ohlcv_data

    def is_valid(self) -> bool:
        return self.current_price > 0 and self.data_quality_score >= 0.3 and self.timestamp is not None and self.refresh_freshness()

    def is_stale(self, max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS) -> bool:
        return not self.refresh_freshness(max_age_seconds)


class UnifiedMarketDataProvider:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._cache: Dict[str, UnifiedMarketSnapshot] = {}
        self._cache_timestamp: Dict[str, datetime] = {}
        self._cache_ttl = float(self.config.get("cache_ttl", 30))
        self._snapshot_counter = 0
        self.adapter = get_market_data_adapter(config)
        logger.info("UnifiedMarketDataProvider initialized")

    def refresh_snapshot(self, symbol: str, timeframe: str = "1h", limit: int = 100, force: bool = False) -> Optional[UnifiedMarketSnapshot]:
        symbol = symbol.upper()
        if not force:
            cached = self._get_cached(symbol)
            if cached is not None:
                return cached
        response = self.adapter.get_market_data(symbol, timeframe, limit)
        if not response.success or response.current_price is None:
            logger.error("Failed to refresh snapshot for %s: %s", symbol, response.error)
            return None
        snapshot = self._create_snapshot_from_response(response, timeframe)
        snapshot.refresh_freshness()
        self._cache[symbol] = snapshot
        self._cache_timestamp[symbol] = datetime.now(timezone.utc)
        self._snapshot_counter += 1
        logger.info("Refreshed snapshot for %s: price=%.2f, quality=%.2f, age=%.2fs", symbol, snapshot.current_price, snapshot.data_quality_score, snapshot.age_seconds)
        return snapshot

    def _create_snapshot_from_response(self, response, timeframe: str) -> UnifiedMarketSnapshot:
        ohlcv_list: List[OHLCV] = []
        for item in response.ohlcv or []:
            try:
                ohlcv = OHLCV(timestamp=item.get("timestamp"), open=float(item.get("open", 0)), high=float(item.get("high", 0)), low=float(item.get("low", 0)), close=float(item.get("close", 0)), volume=float(item.get("volume", 0)))
                if ohlcv.is_valid():
                    ohlcv_list.append(ohlcv)
            except (TypeError, ValueError, OverflowError):
                continue
        ohlcv_list.sort(key=lambda c: c.timestamp)
        change_24h = change_percent_24h = volatility = None
        if len(ohlcv_list) > 1:
            first, last = ohlcv_list[0], ohlcv_list[-1]
            if first.close > 0:
                change_24h = last.close - first.close
                change_percent_24h = (change_24h / first.close) * 100
            returns = [(ohlcv_list[i].close - ohlcv_list[i-1].close) / ohlcv_list[i-1].close for i in range(1, len(ohlcv_list)) if ohlcv_list[i-1].close > 0]
            if returns:
                mean = sum(returns) / len(returns)
                volatility = math.sqrt(sum((r - mean) ** 2 for r in returns) / len(returns))
        market_phase = "NEUTRAL"
        if change_percent_24h is not None:
            if change_percent_24h > 2.0: market_phase = "BULLISH"
            elif change_percent_24h < -2.0: market_phase = "BEARISH"
            elif volatility and volatility > 0.03: market_phase = "VOLATILE"
        quality_score = 1.0
        missing_fields: List[str] = []
        if not ohlcv_list:
            missing_fields.append("ohlcv_data"); quality_score -= 0.3
        if response.volume_24h is None or response.volume_24h == 0:
            missing_fields.append("volume_24h"); quality_score -= 0.05
        if len(ohlcv_list) < 30:
            missing_fields.append("short_horizon_30m")
        if len(ohlcv_list) >= 2:
            intervals = [(ohlcv_list[i].timestamp - ohlcv_list[i-1].timestamp).total_seconds() for i in range(1, len(ohlcv_list))]
            if any(interval < 30 or interval > 90 for interval in intervals):
                missing_fields.append("ohlcv_continuity")
        # response.timestamp is the exchange/source timestamp. The adapter currently
        # reports the latest source observation, so freshness is intentionally checked
        # against that timestamp rather than assuming a successful HTTP response is fresh.
        return UnifiedMarketSnapshot(
            symbol=response.symbol, timestamp=response.timestamp, timeframe=timeframe,
            current_price=float(response.current_price), ohlcv_data=ohlcv_list,
            high_24h=response.high_24h, low_24h=response.low_24h, volume_24h=response.volume_24h,
            change_24h=change_24h, change_percent_24h=change_percent_24h,
            market_phase=market_phase, volatility=volatility, data_quality_score=max(0.0, min(1.0, quality_score)),
            missing_fields=missing_fields, source=response.source, is_fresh=True, age_seconds=0.0
        )

    def _get_cached(self, symbol: str) -> Optional[UnifiedMarketSnapshot]:
        snapshot = self._cache.get(symbol.upper())
        if snapshot is not None and snapshot.is_valid() and not snapshot.is_stale(self._cache_ttl):
            return snapshot
        return None

    def get_snapshot(self, symbol: str) -> Optional[UnifiedMarketSnapshot]:
        return self._get_cached(symbol)

    def create_snapshot_from_market_data(self, symbol: str, market_data: Dict[str, Any]) -> UnifiedMarketSnapshot:
        symbol = symbol.upper()
        timestamp = _normalize_timestamp(market_data.get("timestamp", datetime.now(timezone.utc)))
        snapshot = UnifiedMarketSnapshot(
            symbol=symbol, timestamp=timestamp, timeframe=market_data.get("timeframe", "1h"),
            current_price=float(market_data.get("current_price", 0)),
            ohlcv_data=self._parse_ohlcv_from_dict(market_data.get("ohlcv", [])),
            high_24h=market_data.get("high_24h"), low_24h=market_data.get("low_24h"), volume_24h=market_data.get("volume_24h"),
            fear_greed_index=market_data.get("fear_greed_index"), market_phase=market_data.get("market_phase", "NEUTRAL"),
            volatility=market_data.get("volatility"), data_quality_score=market_data.get("data_quality_score", 0.5),
            missing_fields=market_data.get("missing_fields", []), source="market_data_input", is_fresh=True, age_seconds=0.0
        )
        snapshot.refresh_freshness()
        return snapshot

    def _parse_ohlcv_from_dict(self, data: List[Dict]) -> List[OHLCV]:
        ohlcv_list = []
        for item in data or []:
            try:
                ohlcv = OHLCV(timestamp=item.get("timestamp"), open=float(item.get("open", 0)), high=float(item.get("high", 0)), low=float(item.get("low", 0)), close=float(item.get("close", 0)), volume=float(item.get("volume", 0)))
                if ohlcv.is_valid(): ohlcv_list.append(ohlcv)
            except (TypeError, ValueError, OverflowError): continue
        ohlcv_list.sort(key=lambda c: c.timestamp)
        return ohlcv_list

    def clear_cache(self):
        self._cache.clear(); self._cache_timestamp.clear(); logger.info("Cache cleared")

    def get_stats(self) -> Dict[str, Any]:
        return {"cached_symbols": list(self._cache.keys()), "cache_size": len(self._cache), "total_snapshots": self._snapshot_counter, "cache_ttl": self._cache_ttl}


def get_market_data_for_agent(snapshot: UnifiedMarketSnapshot) -> Dict[str, Any]:
    return snapshot.to_dict()


def create_snapshot_from_market_data(provider: UnifiedMarketDataProvider, symbol: str, market_data: Dict[str, Any]) -> UnifiedMarketSnapshot:
    return provider.create_snapshot_from_market_data(symbol, market_data)

_market_data_provider = None

def get_market_data_provider(config: Optional[Dict] = None) -> UnifiedMarketDataProvider:
    global _market_data_provider
    if _market_data_provider is None:
        _market_data_provider = UnifiedMarketDataProvider(config)
    elif config:
        _market_data_provider.config.update(config); _market_data_provider.adapter.configure(config)
    return _market_data_provider
