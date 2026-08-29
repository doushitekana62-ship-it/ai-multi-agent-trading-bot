"""
core/unified_market_data.py - MODIFIED

Single Source of Truth untuk semua market data.
Sekarang terintegrasi dengan MarketDataAdapter.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from core.market_data_adapter import MarketDataAdapter, get_market_data_adapter

logger = logging.getLogger(__name__)

def _normalize_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None: return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric > 1_000_000_000_000: numeric /= 1000.0
        return datetime.fromtimestamp(numeric, tz=timezone.utc)
    if isinstance(value, str):
        text=value.strip()
        if not text: return datetime.now(timezone.utc)
        try:
            parsed=datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None: parsed=parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            try:
                numeric=float(text); numeric=numeric/1000.0 if numeric>1_000_000_000_000 else numeric
                return datetime.fromtimestamp(numeric,tz=timezone.utc)
            except ValueError: pass
    return datetime.now(timezone.utc)

@dataclass
class OHLCV:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    def __post_init__(self): self.timestamp=_normalize_timestamp(self.timestamp)
    def to_dict(self):
        return {"timestamp":self.timestamp.isoformat(),"open":self.open,"high":self.high,"low":self.low,"close":self.close,"volume":self.volume}
    def is_valid(self): return self.open>0 and self.high>0 and self.low>0 and self.close>0 and self.volume>=0

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
    def __post_init__(self): self.timestamp=_normalize_timestamp(self.timestamp)
    def to_dict(self):
        return {"symbol":self.symbol,"timestamp":self.timestamp.isoformat(),"timeframe":self.timeframe,"current_price":self.current_price,"unified_price":self.current_price,"high_24h":self.high_24h,"low_24h":self.low_24h,"volume_24h":self.volume_24h,"change_24h":self.change_24h,"change_percent_24h":self.change_percent_24h,"fear_greed_index":self.fear_greed_index,"market_phase":self.market_phase,"volatility":self.volatility,"data_quality_score":self.data_quality_score,"missing_fields":self.missing_fields,"source":self.source,"is_fresh":self.is_fresh,"ohlcv":[o.to_dict() for o in self.ohlcv_data[-100:]],"ohlcv_count":len(self.ohlcv_data)}
    def get_price(self): return self.current_price
    def get_ohlcv(self, limit=None): return self.ohlcv_data[-limit:] if limit and limit>0 else self.ohlcv_data
    def is_valid(self): return self.current_price>0 and self.data_quality_score>=0.3 and self.timestamp is not None and self.is_fresh
    def is_stale(self,max_age_seconds=60):
        self.age_seconds=(datetime.now(timezone.utc)-self.timestamp).total_seconds()
        return self.age_seconds>max_age_seconds

class UnifiedMarketDataProvider:
    def __init__(self,config=None):
        self.config=config or {}; self._cache={}; self._cache_timestamp={}; self._cache_ttl=self.config.get("cache_ttl",30); self._snapshot_counter=0; self.adapter=get_market_data_adapter(config); logger.info("UnifiedMarketDataProvider initialized")
    def refresh_snapshot(self,symbol,timeframe="1h",limit=100,force=False):
        symbol=symbol.upper()
        if not force:
            cached=self._get_cached(symbol)
            if cached is not None and not cached.is_stale(self._cache_ttl): return cached
        response=self.adapter.get_market_data(symbol,timeframe,limit)
        if not response.success or response.current_price is None: return None
        snapshot=self._create_snapshot_from_response(response,timeframe); self._cache[symbol]=snapshot; self._cache_timestamp[symbol]=snapshot.timestamp; self._snapshot_counter+=1; return snapshot
    def _create_snapshot_from_response(self,response,timeframe):
        candles=[]
        for item in response.ohlcv or []:
            try:
                candle=OHLCV(timestamp=item.get("timestamp"),open=float(item.get("open",0)),high=float(item.get("high",0)),low=float(item.get("low",0)),close=float(item.get("close",0)),volume=float(item.get("volume",0)))
                if candle.is_valid(): candles.append(candle)
            except (TypeError,ValueError,OverflowError): continue
        candles.sort(key=lambda x:x.timestamp)
        missing=[]
        if not candles: missing.append("ohlcv_data")
        if response.volume_24h is None or response.volume_24h==0: missing.append("volume_24h")
        quality=1.0-(0.3 if not candles else 0.0)-(0.05 if "volume_24h" in missing else 0.0)
        if len(candles)<30: missing.append("short_horizon_30m")
        if len(candles)>=2:
            intervals=[(candles[i].timestamp-candles[i-1].timestamp).total_seconds() for i in range(1,len(candles))]
            if any(i<30 or i>90 for i in intervals): missing.append("ohlcv_continuity")
        return UnifiedMarketSnapshot(symbol=response.symbol,timestamp=response.timestamp,timeframe=timeframe,current_price=float(response.current_price),ohlcv_data=candles,high_24h=response.high_24h,low_24h=response.low_24h,volume_24h=response.volume_24h,change_24h=(candles[-1].close-candles[0].close if len(candles)>1 else None),change_percent_24h=((candles[-1].close/candles[0].close-1)*100 if len(candles)>1 and candles[0].close>0 else None),market_phase="NEUTRAL",volatility=self._volatility(candles),data_quality_score=max(0.0,min(1.0,quality)),missing_fields=missing,source=response.source,is_fresh=True,age_seconds=0.0)
    @staticmethod
    def _volatility(candles):
        if len(candles)<2:return None
        returns=[candles[i].close/candles[i-1].close-1 for i in range(1,len(candles)) if candles[i-1].close>0]
        if not returns:return None
        mean=sum(returns)/len(returns); return math.sqrt(sum((r-mean)**2 for r in returns)/len(returns))
    def _get_cached(self,symbol):
        snapshot=self._cache.get(symbol.upper())
        if snapshot and snapshot.is_valid() and not snapshot.is_stale(self._cache_ttl): return snapshot
        return None
    def get_snapshot(self,symbol): return self._get_cached(symbol)
    def create_snapshot_from_market_data(self,symbol,market_data):
        return UnifiedMarketSnapshot(symbol=symbol.upper(),timestamp=market_data.get("timestamp",datetime.now(timezone.utc)),timeframe=market_data.get("timeframe","1h"),current_price=float(market_data.get("current_price",0)),ohlcv_data=self._parse_ohlcv_from_dict(market_data.get("ohlcv",[])),high_24h=market_data.get("high_24h"),low_24h=market_data.get("low_24h"),volume_24h=market_data.get("volume_24h"),fear_greed_index=market_data.get("fear_greed_index"),market_phase=market_data.get("market_phase","NEUTRAL"),volatility=market_data.get("volatility"),data_quality_score=market_data.get("data_quality_score",0.5),missing_fields=market_data.get("missing_fields",[]),source="legacy_market_data",is_fresh=True,age_seconds=0.0)
    def _parse_ohlcv_from_dict(self,data):
        out=[]
        for item in data or []:
            try:
                candle=OHLCV(timestamp=item.get("timestamp"),open=float(item.get("open",0)),high=float(item.get("high",0)),low=float(item.get("low",0)),close=float(item.get("close",0)),volume=float(item.get("volume",0)))
                if candle.is_valid():out.append(candle)
            except (TypeError,ValueError,OverflowError):continue
        return out
    def clear_cache(self): self._cache.clear(); self._cache_timestamp.clear()
    def get_stats(self): return {"cached_symbols":list(self._cache.keys()),"cache_size":len(self._cache),"total_snapshots":self._snapshot_counter,"cache_ttl":self._cache_ttl}

def get_market_data_for_agent(snapshot): return snapshot.to_dict()
def create_snapshot_from_market_data(provider,symbol,market_data): return provider.create_snapshot_from_market_data(symbol,market_data)
_market_data_provider=None
def get_market_data_provider(config=None):
    global _market_data_provider
    if _market_data_provider is None:_market_data_provider=UnifiedMarketDataProvider(config)
    elif config:_market_data_provider.config.update(config);_market_data_provider.adapter.configure(config)
    return _market_data_provider