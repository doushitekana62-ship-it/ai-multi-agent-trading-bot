"""
core/unified_market_data.py - MODIFIED

Single Source of Truth untuk semua market data.
Sekarang terintegrasi dengan MarketDataAdapter.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

from core.market_data_adapter import MarketDataAdapter, get_market_data_adapter

logger = logging.getLogger(__name__)


@dataclass
class OHLCV:
    """OHLCV data point."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume
        }
    
    def is_valid(self) -> bool:
        return (
            self.open > 0 and
            self.high > 0 and
            self.low > 0 and
            self.close > 0 and
            self.volume >= 0
        )


@dataclass
class UnifiedMarketSnapshot:
    """
    UNIFIED MARKET SNAPSHOT - Single Source of Truth.
    
    Semua agent dan komponen menggunakan snapshot ini.
    """
    symbol: str
    timestamp: datetime
    timeframe: str
    
    # Current price
    current_price: float
    
    # OHLCV data
    ohlcv_data: List[OHLCV] = field(default_factory=list)
    
    # Derived metrics
    high_24h: Optional[float] = None
    low_24h: Optional[float] = None
    volume_24h: Optional[float] = None
    change_24h: Optional[float] = None
    change_percent_24h: Optional[float] = None
    
    # Sentiment data
    fear_greed_index: Optional[float] = None
    
    # Market context
    market_phase: str = "NEUTRAL"
    volatility: Optional[float] = None
    
    # Data quality
    data_quality_score: float = 1.0
    missing_fields: List[str] = field(default_factory=list)
    source: str = "unified_market_data"
    is_fresh: bool = True
    age_seconds: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict untuk kompatibilitas dengan agents existing."""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "timeframe": self.timeframe,
            "current_price": self.current_price,
            "unified_price": self.current_price,  # Explicit marker
            "high_24h": self.high_24h,
            "low_24h": self.low_24h,
            "volume_24h": self.volume_24h,
            "change_24h": self.change_24h,
            "change_percent_24h": self.change_percent_24h,
            "fear_greed_index": self.fear_greed_index,
            "market_phase": self.market_phase,
            "volatility": self.volatility,
            "data_quality_score": self.data_quality_score,
            "missing_fields": self.missing_fields,
            "source": self.source,
            "is_fresh": self.is_fresh,
            "ohlcv": [o.to_dict() for o in self.ohlcv_data[-100:]],
            "ohlcv_count": len(self.ohlcv_data)
        }
    
    def get_price(self) -> float:
        """Get unified price."""
        return self.current_price
    
    def get_ohlcv(self, limit: Optional[int] = None) -> List[OHLCV]:
        """Get OHLCV data."""
        if limit and limit > 0:
            return self.ohlcv_data[-limit:]
        return self.ohlcv_data
    
    def is_valid(self) -> bool:
        """Check if snapshot is valid."""
        return (
            self.current_price > 0 and
            self.data_quality_score >= 0.3 and
            self.timestamp is not None and
            self.is_fresh
        )
    
    def is_stale(self, max_age_seconds: int = 60) -> bool:
        """Check if snapshot is stale."""
        age = (datetime.now(timezone.utc) - self.timestamp).total_seconds()
        self.age_seconds = age
        return age > max_age_seconds


class UnifiedMarketDataProvider:
    """
    PROVIDER - Single access point untuk semua market data.
    
    Terintegrasi dengan MarketDataAdapter untuk fetching data.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._cache: Dict[str, UnifiedMarketSnapshot] = {}
        self._cache_timestamp: Dict[str, datetime] = {}
        self._cache_ttl = self.config.get("cache_ttl", 30)
        self._snapshot_counter = 0
        
        # Market Data Adapter
        self.adapter = get_market_data_adapter(config)
        
        logger.info("UnifiedMarketDataProvider initialized")
    
    def refresh_snapshot(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
        force: bool = False
    ) -> Optional[UnifiedMarketSnapshot]:
        """
        Refresh snapshot from exchange.
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe for OHLCV
            limit: Number of candles
            force: Force refresh even if cache is valid
        
        Returns:
            UnifiedMarketSnapshot atau None jika gagal
        """
        symbol = symbol.upper()
        
        # Check cache
        if not force:
            cached = self._get_cached(symbol)
            if cached is not None and not cached.is_stale(self._cache_ttl):
                logger.debug("Using cached snapshot for %s", symbol)
                return cached
        
        # Fetch from adapter
        response = self.adapter.get_market_data(symbol, timeframe, limit)
        
        if not response.success or response.current_price is None:
            logger.error("Failed to refresh snapshot for %s: %s",
                        symbol, response.error)
            return None
        
        # Create snapshot from response
        snapshot = self._create_snapshot_from_response(response, timeframe)
        
        # Cache
        self._cache[symbol] = snapshot
        self._cache_timestamp[symbol] = snapshot.timestamp
        
        logger.info("Refreshed snapshot for %s: price=%.2f, quality=%.2f",
                   symbol, snapshot.current_price, snapshot.data_quality_score)
        
        return snapshot
    
    def _create_snapshot_from_response(
        self,
        response,
        timeframe: str
    ) -> UnifiedMarketSnapshot:
        """Create snapshot from MarketDataResponse."""
        self._snapshot_counter += 1
        
        # Parse OHLCV
        ohlcv_list = []
        if response.ohlcv:
            for item in response.ohlcv:
                try:
                    if isinstance(item, dict):
                        ohlcv = OHLCV(
                            timestamp=item.get("timestamp", datetime.now(timezone.utc)),
                            open=float(item.get("open", 0)),
                            high=float(item.get("high", 0)),
                            low=float(item.get("low", 0)),
                            close=float(item.get("close", 0)),
                            volume=float(item.get("volume", 0))
                        )
                        if ohlcv.is_valid():
                            ohlcv_list.append(ohlcv)
                except (TypeError, ValueError) as e:
                    logger.warning("Error parsing OHLCV: %s", e)
        
        # Calculate metrics
        change_24h = None
        change_percent_24h = None
        volatility = None
        
        if len(ohlcv_list) > 1:
            last = ohlcv_list[-1]
            first = ohlcv_list[0]
            if first.close > 0:
                change_24h = last.close - first.close
                change_percent_24h = (change_24h / first.close) * 100
            
            returns = []
            for i in range(1, len(ohlcv_list)):
                if ohlcv_list[i-1].close > 0:
                    ret = (ohlcv_list[i].close - ohlcv_list[i-1].close) / ohlcv_list[i-1].close
                    returns.append(ret)
            if returns:
                mean = sum(returns) / len(returns)
                variance = sum((r - mean) ** 2 for r in returns) / len(returns)
                volatility = math.sqrt(variance)
        
        # Market phase
        market_phase = "NEUTRAL"
        if change_percent_24h is not None:
            if change_percent_24h > 2.0:
                market_phase = "BULLISH"
            elif change_percent_24h < -2.0:
                market_phase = "BEARISH"
            elif volatility and volatility > 0.03:
                market_phase = "VOLATILE"
        
        # Quality score
        quality_score = 1.0
        missing_fields = []
        
        if not ohlcv_list:
            missing_fields.append("ohlcv_data")
            quality_score -= 0.3
        
        if response.volume_24h is None or response.volume_24h == 0:
            missing_fields.append("volume_24h")
            quality_score -= 0.05
        
        quality_score = max(0.0, min(1.0, quality_score))
        
        return UnifiedMarketSnapshot(
            symbol=response.symbol,
            timestamp=response.timestamp,
            timeframe=timeframe,
            current_price=float(response.current_price),
            ohlcv_data=ohlcv_list,
            high_24h=response.high_24h,
            low_24h=response.low_24h,
            volume_24h=response.volume_24h,
            change_24h=change_24h,
            change_percent_24h=change_percent_24h,
            market_phase=market_phase,
            volatility=volatility,
            data_quality_score=quality_score,
            missing_fields=missing_fields,
            source=response.source,
            is_fresh=True,
            age_seconds=0.0
        )
    
    def _get_cached(self, symbol: str) -> Optional[UnifiedMarketSnapshot]:
        """Get cached snapshot if valid."""
        symbol = symbol.upper()
        if symbol in self._cache:
            snapshot = self._cache[symbol]
            if snapshot.is_valid() and not snapshot.is_stale(self._cache_ttl):
                return snapshot
        return None
    
    def get_snapshot(self, symbol: str) -> Optional[UnifiedMarketSnapshot]:
        """Get snapshot from cache."""
        return self._get_cached(symbol)
    
    def create_snapshot_from_market_data(
        self,
        symbol: str,
        market_data: Dict[str, Any]
    ) -> UnifiedMarketSnapshot:
        """
        Create snapshot from existing market_data dict.
        
        INI ADALAH ADAPTER - Untuk kompatibilitas dengan code existing.
        """
        symbol = symbol.upper()
        
        return UnifiedMarketSnapshot(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            timeframe=market_data.get("timeframe", "1h"),
            current_price=float(market_data.get("current_price", 0)),
            ohlcv_data=self._parse_ohlcv_from_dict(market_data.get("ohlcv", [])),
            high_24h=market_data.get("high_24h"),
            low_24h=market_data.get("low_24h"),
            volume_24h=market_data.get("volume_24h"),
            fear_greed_index=market_data.get("fear_greed_index"),
            market_phase=market_data.get("market_phase", "NEUTRAL"),
            volatility=market_data.get("volatility"),
            data_quality_score=market_data.get("data_quality_score", 0.5),
            missing_fields=market_data.get("missing_fields", []),
            source="legacy_market_data",
            is_fresh=True,
            age_seconds=0.0
        )
    
    def _parse_ohlcv_from_dict(self, data: List[Dict]) -> List[OHLCV]:
        """Parse OHLCV from dict list."""
        ohlcv_list = []
        for item in data or []:
            try:
                ohlcv = OHLCV(
                    timestamp=item.get("timestamp", datetime.now(timezone.utc)),
                    open=float(item.get("open", 0)),
                    high=float(item.get("high", 0)),
                    low=float(item.get("low", 0)),
                    close=float(item.get("close", 0)),
                    volume=float(item.get("volume", 0))
                )
                if ohlcv.is_valid():
                    ohlcv_list.append(ohlcv)
            except (TypeError, ValueError):
                continue
        return ohlcv_list
    
    def clear_cache(self):
        """Clear all cache."""
        self._cache.clear()
        self._cache_timestamp.clear()
        logger.info("Cache cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get provider statistics."""
        return {
            "cached_symbols": list(self._cache.keys()),
            "cache_size": len(self._cache),
            "total_snapshots": self._snapshot_counter,
            "cache_ttl": self._cache_ttl
        }


# ============================================================
# COMPATIBILITY LAYER - Untuk kompatibilitas dengan code existing
# ============================================================

def get_market_data_for_agent(snapshot: UnifiedMarketSnapshot) -> Dict[str, Any]:
    """Convert snapshot ke format yang kompatibel dengan agents existing."""
    return snapshot.to_dict()


def create_snapshot_from_market_data(
    provider: UnifiedMarketDataProvider,
    symbol: str,
    market_data: Dict[str, Any]
) -> UnifiedMarketSnapshot:
    """Create snapshot dari market_data existing."""
    return provider.create_snapshot_from_market_data(symbol, market_data)


# ============================================================
# SINGLETON INSTANCE
# ============================================================

_market_data_provider = None

def get_market_data_provider(config: Optional[Dict] = None) -> UnifiedMarketDataProvider:
    """Get singleton instance of UnifiedMarketDataProvider."""
    global _market_data_provider
    if _market_data_provider is None:
        _market_data_provider = UnifiedMarketDataProvider(config)
    return _market_data_provider


# Global instance untuk backward compatibility
market_data_provider = get_market_data_provider()
