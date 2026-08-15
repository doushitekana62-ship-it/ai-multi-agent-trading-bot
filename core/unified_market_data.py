"""
unified_market_data.py - Unified Market Snapshot untuk semua agent

Menyediakan data pasar yang konsisten untuk seluruh pipeline.
Ini adalah SINGLE SOURCE OF TRUTH untuk semua data pasar.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import logging
import math

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


@dataclass
class UnifiedMarketSnapshot:
    """
    Unified Market Snapshot - Sumber data tunggal untuk semua agent.
    
    Semua agent akan menggunakan snapshot ini untuk analisis,
    sehingga tidak ada perbedaan harga/volume/data antar-agent.
    """
    symbol: str
    timestamp: datetime
    timeframe: str  # "1m", "5m", "15m", "1h", "4h", "1d"
    
    # Current price - SINGLE SOURCE OF TRUTH
    current_price: float
    
    # OHLCV data (historical)
    ohlcv_data: List[OHLCV] = field(default_factory=list)
    
    # Derived data
    high_24h: Optional[float] = None
    low_24h: Optional[float] = None
    volume_24h: Optional[float] = None
    change_24h: Optional[float] = None
    change_percent_24h: Optional[float] = None
    
    # Fear & Greed Index (jika tersedia)
    fear_greed_index: Optional[float] = None  # 0-100
    fear_greed_timestamp: Optional[datetime] = None
    
    # Market context
    market_phase: str = "NEUTRAL"  # BULLISH, BEARISH, NEUTRAL, VOLATILE
    volatility: Optional[float] = None
    
    # Metadata
    data_quality_score: float = 1.0  # 0-1, seberapa lengkap data
    missing_fields: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for agent consumption."""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "timeframe": self.timeframe,
            "current_price": self.current_price,
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
            "ohlcv_count": len(self.ohlcv_data),
            "ohlcv": [
                {
                    "timestamp": o.timestamp.isoformat(),
                    "open": o.open,
                    "high": o.high,
                    "low": o.low,
                    "close": o.close,
                    "volume": o.volume
                }
                for o in self.ohlcv_data[-100:]  # Only last 100 points
            ]
        }
    
    def get_price_consistency_check(self) -> Dict[str, Any]:
        """Check price consistency across data sources."""
        return {
            "current_price": self.current_price,
            "last_close": self.ohlcv_data[-1].close if self.ohlcv_data else None,
            "price_match": self.current_price == (self.ohlcv_data[-1].close if self.ohlcv_data else None),
            "data_points": len(self.ohlcv_data),
            "missing_fields": self.missing_fields,
            "quality_score": self.data_quality_score
        }
    
    def get_latest_ohlcv(self) -> Optional[OHLCV]:
        """Get latest OHLCV data point."""
        return self.ohlcv_data[-1] if self.ohlcv_data else None
    
    def get_ohlcv_for_period(self, periods: int = 20) -> List[OHLCV]:
        """Get last N OHLCV data points."""
        return self.ohlcv_data[-periods:] if self.ohlcv_data else []


class UnifiedMarketDataProvider:
    """
    Provider untuk Unified Market Snapshot.
    Memastikan semua agent menggunakan data yang sama.
    """
    
    def __init__(self, cache_ttl: int = 30):
        """
        Initialize provider.
        
        Args:
            cache_ttl: Cache TTL in seconds (default 30)
        """
        self._cache: Dict[str, UnifiedMarketSnapshot] = {}
        self._cache_timestamp: Dict[str, datetime] = {}
        self._cache_ttl = cache_ttl
        self._snapshot_counter = 0
        
        logger.info("UnifiedMarketDataProvider initialized with TTL=%ds", cache_ttl)
    
    def create_snapshot(
        self,
        symbol: str,
        current_price: float,
        ohlcv_data: Optional[List[Dict[str, Any]]] = None,
        timeframe: str = "1h",
        fear_greed_index: Optional[float] = None,
        volume_24h: Optional[float] = None,
        high_24h: Optional[float] = None,
        low_24h: Optional[float] = None,
        force_refresh: bool = False
    ) -> UnifiedMarketSnapshot:
        """
        Create unified market snapshot.
        
        Args:
            symbol: Trading symbol
            current_price: Current price (SINGLE SOURCE OF TRUTH)
            ohlcv_data: List of OHLCV data points
            timeframe: Timeframe for analysis
            fear_greed_index: Fear & Greed Index (0-100)
            volume_24h: 24h volume
            high_24h: 24h high
            low_24h: 24h low
            force_refresh: Force refresh even if cache is valid
        
        Returns:
            UnifiedMarketSnapshot
        """
        self._snapshot_counter += 1
        timestamp = datetime.now(timezone.utc)
        
        # Check cache first
        if not force_refresh:
            cached = self.get_snapshot(symbol)
            if cached is not None:
                logger.debug("Using cached snapshot for %s", symbol)
                return cached
        
        # Parse OHLCV data
        parsed_ohlcv = []
        missing_fields = []
        data_quality_score = 1.0
        
        if ohlcv_data:
            for item in ohlcv_data:
                try:
                    if isinstance(item, dict):
                        ohlcv = OHLCV(
                            timestamp=item.get("timestamp", timestamp),
                            open=float(item.get("open", 0)),
                            high=float(item.get("high", 0)),
                            low=float(item.get("low", 0)),
                            close=float(item.get("close", 0)),
                            volume=float(item.get("volume", 0))
                        )
                        parsed_ohlcv.append(ohlcv)
                    elif hasattr(item, "open"):
                        ohlcv = OHLCV(
                            timestamp=getattr(item, "timestamp", timestamp),
                            open=float(getattr(item, "open", 0)),
                            high=float(getattr(item, "high", 0)),
                            low=float(getattr(item, "low", 0)),
                            close=float(getattr(item, "close", 0)),
                            volume=float(getattr(item, "volume", 0))
                        )
                        parsed_ohlcv.append(ohlcv)
                except (TypeError, ValueError) as e:
                    logger.warning("Error parsing OHLCV data: %s", e)
                    data_quality_score -= 0.05
        
        # Check missing fields
        if not parsed_ohlcv:
            missing_fields.append("ohlcv_data")
            data_quality_score -= 0.3
        
        if fear_greed_index is None or fear_greed_index == 0:
            missing_fields.append("fear_greed_index")
            data_quality_score -= 0.1
        
        if volume_24h is None or volume_24h == 0:
            missing_fields.append("volume_24h")
            data_quality_score -= 0.05
        
        # Calculate derived metrics
        change_24h = None
        change_percent_24h = None
        volatility = None
        
        if len(parsed_ohlcv) > 1:
            # 24h change (using last day data)
            last_24h = parsed_ohlcv[-1]
            first_24h = parsed_ohlcv[0]
            if first_24h.close > 0:
                change_24h = last_24h.close - first_24h.close
                change_percent_24h = (change_24h / first_24h.close) * 100
            
            # Volatility (using standard deviation of returns)
            returns = []
            for i in range(1, len(parsed_ohlcv)):
                if parsed_ohlcv[i-1].close > 0:
                    ret = (parsed_ohlcv[i].close - parsed_ohlcv[i-1].close) / parsed_ohlcv[i-1].close
                    returns.append(ret)
            if returns:
                mean = sum(returns) / len(returns)
                variance = sum((r - mean) ** 2 for r in returns) / len(returns)
                volatility = math.sqrt(variance)
        
        # Determine market phase
        market_phase = "NEUTRAL"
        if change_percent_24h is not None:
            if change_percent_24h > 2.0:
                market_phase = "BULLISH"
            elif change_percent_24h < -2.0:
                market_phase = "BEARISH"
            elif volatility and volatility > 0.03:
                market_phase = "VOLATILE"
        
        # Calculate volume if 24h volume not provided
        if volume_24h is None or volume_24h == 0:
            if parsed_ohlcv:
                volume_24h = sum(o.volume for o in parsed_ohlcv[-24:])  # Last 24 bars
        
        # Clamp quality score
        data_quality_score = max(0.0, min(1.0, data_quality_score))
        
        # If data quality is too low, warn
        if data_quality_score < 0.5:
            logger.warning("Low data quality for %s: %.2f, missing: %s", 
                          symbol, data_quality_score, missing_fields)
        
        snapshot = UnifiedMarketSnapshot(
            symbol=symbol.upper(),
            timestamp=timestamp,
            timeframe=timeframe,
            current_price=float(current_price),
            ohlcv_data=parsed_ohlcv,
            high_24h=high_24h or (parsed_ohlcv[-1].high if parsed_ohlcv else None),
            low_24h=low_24h or (parsed_ohlcv[-1].low if parsed_ohlcv else None),
            volume_24h=volume_24h,
            change_24h=change_24h,
            change_percent_24h=change_percent_24h,
            fear_greed_index=fear_greed_index,
            market_phase=market_phase,
            volatility=volatility,
            data_quality_score=data_quality_score,
            missing_fields=missing_fields
        )
        
        # Cache the snapshot
        self._cache[symbol] = snapshot
        self._cache_timestamp[symbol] = timestamp
        
        logger.info("Created unified snapshot #%d for %s: price=%.2f, quality=%.2f, missing=%s",
                   self._snapshot_counter, symbol, current_price, data_quality_score, missing_fields)
        
        return snapshot
    
    def get_snapshot(self, symbol: str) -> Optional[UnifiedMarketSnapshot]:
        """Get cached snapshot if still valid."""
        symbol = symbol.upper()
        if symbol in self._cache:
            cached_time = self._cache_timestamp.get(symbol)
            if cached_time:
                age = (datetime.now(timezone.utc) - cached_time).total_seconds()
                if age < self._cache_ttl:
                    return self._cache[symbol]
        return None
    
    def update_price(self, symbol: str, new_price: float) -> Optional[UnifiedMarketSnapshot]:
        """
        Update price in existing snapshot without recreating everything.
        
        Args:
            symbol: Trading symbol
            new_price: New current price
        
        Returns:
            Updated snapshot or None if not in cache
        """
        symbol = symbol.upper()
        if symbol in self._cache:
            snapshot = self._cache[symbol]
            snapshot.current_price = float(new_price)
            snapshot.timestamp = datetime.now(timezone.utc)
            self._cache_timestamp[symbol] = snapshot.timestamp
            logger.debug("Updated price for %s: %.2f", symbol, new_price)
            return snapshot
        return None
    
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


# Global instance for easy import
market_data_provider = UnifiedMarketDataProvider()


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":
    import json
    
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 70)
    print("UNIFIED MARKET DATA PROVIDER TEST")
    print("=" * 70)
    
    provider = UnifiedMarketDataProvider()
    
    # Create sample OHLCV data
    base_price = 62760.21
    sample_ohlcv = []
    for i in range(100):
        price = base_price * (1 + 0.001 * math.sin(i / 10) + 0.0005 * math.cos(i / 5))
        sample_ohlcv.append({
            "timestamp": datetime.now(timezone.utc),
            "open": price * 0.999,
            "high": price * 1.002,
            "low": price * 0.998,
            "close": price,
            "volume": 1000 + 500 * (1 + math.sin(i / 20))
        })
    
    # Create snapshot
    snapshot = provider.create_snapshot(
        symbol="BTC-USD",
        current_price=base_price,
        ohlcv_data=sample_ohlcv,
        timeframe="1h",
        fear_greed_index=45,
        volume_24h=15000000,
        high_24h=base_price * 1.03,
        low_24h=base_price * 0.97
    )
    
    print("\n--- SNAPSHOT CREATED ---")
    print(f"Symbol: {snapshot.symbol}")
    print(f"Price: ${snapshot.current_price:.2f}")
    print(f"Market Phase: {snapshot.market_phase}")
    print(f"Volatility: {snapshot.volatility:.4f}")
    print(f"Data Quality: {snapshot.data_quality_score:.2%}")
    print(f"Missing Fields: {snapshot.missing_fields}")
    print(f"OHLCV Count: {len(snapshot.ohlcv_data)}")
    
    print("\n--- SNAPSHOT TO DICT ---")
    snapshot_dict = snapshot.to_dict()
    print(json.dumps(snapshot_dict, indent=2, default=str)[:1000] + "...")
    
    print("\n--- PROVIDER STATS ---")
    print(json.dumps(provider.get_stats(), indent=2))
    
    print("\n" + "=" * 70)
    print("TEST COMPLETED")
    print("=" * 70)
