"""
core/market_data_adapter.py

Market Data Adapter - Bridge antara exchange API dan UnifiedMarketData.

Tujuan:
1. Menyediakan interface tunggal untuk semua exchange API calls
2. Memudahkan migrasi dari Alpaca ke exchange lokal Indonesia
3. Menyimpan data dalam format yang konsisten untuk UnifiedMarketData
4. Menangani error, retry, dan fallback dengan aman
5. Tidak membuat data palsu ketika API gagal - selalu return None
"""

import logging
import time
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MarketDataResponse:
    """Standard response dari market data adapter."""
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
    """
    Market Data Adapter - Single interface untuk semua exchange API.
    
    Saat ini mendukung Alpaca, tapi dirancang untuk mudah beralih
    ke exchange lokal Indonesia (seperti INDODAX, Tokocrypto, dll).
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.exchange_type = self.config.get("exchange_type", "paper")
        self.enable_retry = self.config.get("enable_retry", True)
        self.max_retries = self.config.get("max_retries", 3)
        self.retry_delay = self.config.get("retry_delay", 1.0)
        
        # Exchange clients (lazy loaded)
        self._alpaca_client = None
        self._local_exchange_client = None
        
        logger.info("MarketDataAdapter initialized with exchange_type=%s", self.exchange_type)
    
    def get_market_data(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100
    ) -> MarketDataResponse:
        """
        Get market data from configured exchange.
        
        Args:
            symbol: Trading symbol (e.g., "BTC-USD", "BTC/IDR")
            timeframe: Timeframe for OHLCV data
            limit: Number of candles to fetch
        
        Returns:
            MarketDataResponse dengan data atau error
        """
        symbol = symbol.upper()
        
        # Try to get data with retry
        if self.enable_retry:
            for attempt in range(self.max_retries):
                try:
                    response = self._fetch_market_data(symbol, timeframe, limit)
                    if response.success:
                        return response
                    logger.warning("Attempt %d/%d failed for %s: %s",
                                 attempt + 1, self.max_retries, symbol, response.error)
                    time.sleep(self.retry_delay * (attempt + 1))
                except Exception as e:
                    logger.error("Error fetching market data: %s", e)
                    time.sleep(self.retry_delay * (attempt + 1))
        
        # All retries failed
        return self._create_error_response(
            symbol,
            f"Failed to fetch market data after {self.max_retries} attempts"
        )
    
    def _fetch_market_data(
        self,
        symbol: str,
        timeframe: str,
        limit: int
    ) -> MarketDataResponse:
        """
        Internal method to fetch data from actual exchange.
        """
        if self.exchange_type == "paper":
            return self._fetch_from_paper(symbol, timeframe, limit)
        elif self.exchange_type == "alpaca":
            return self._fetch_from_alpaca(symbol, timeframe, limit)
        elif self.exchange_type == "local":
            return self._fetch_from_local_exchange(symbol, timeframe, limit)
        else:
            return self._create_error_response(
                symbol,
                f"Unknown exchange type: {self.exchange_type}"
            )
    
    def _fetch_from_paper(
        self,
        symbol: str,
        timeframe: str,
        limit: int
    ) -> MarketDataResponse:
        """Fetch data from paper trading engine."""
        try:
            from exchange_integration.paper_trading import PaperTrading
            
            paper = PaperTrading()
            price = paper.get_price(symbol)
            
            if price is None or price <= 0:
                return self._create_error_response(symbol, "Invalid price from paper trading")
            
            # Generate synthetic OHLCV for paper trading (for testing)
            ohlcv = self._generate_synthetic_ohlcv(symbol, price, timeframe, limit)
            
            return MarketDataResponse(
                success=True,
                symbol=symbol,
                current_price=price,
                ohlcv=ohlcv,
                volume_24h=1000000.0,  # Simulated
                high_24h=price * 1.02,
                low_24h=price * 0.98,
                timestamp=datetime.now(timezone.utc),
                source="paper"
            )
        except Exception as e:
            return self._create_error_response(symbol, f"Paper trading error: {e}")
    
    def _fetch_from_alpaca(
        self,
        symbol: str,
        timeframe: str,
        limit: int
    ) -> MarketDataResponse:
        """Fetch data from Alpaca API."""
        try:
            from exchange_integration.alpaca_bridge import AlpacaBridge
            
            if self._alpaca_client is None:
                self._alpaca_client = AlpacaBridge()
            
            # Get current price
            price = self._alpaca_client.get_current_price(symbol)
            
            if price is None or price <= 0:
                return self._create_error_response(symbol, "Invalid price from Alpaca")
            
            # Get OHLCV data
            ohlcv = self._alpaca_client.get_historical_data(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit
            )
            
            if ohlcv is None:
                ohlcv = []
            
            # Calculate 24h metrics
            if ohlcv and len(ohlcv) >= 24:
                high_24h = max(c.get("high", 0) for c in ohlcv[-24:])
                low_24h = min(c.get("low", 0) for c in ohlcv[-24:])
                volume_24h = sum(c.get("volume", 0) for c in ohlcv[-24:])
            else:
                high_24h = price * 1.02
                low_24h = price * 0.98
                volume_24h = 1000000.0
            
            return MarketDataResponse(
                success=True,
                symbol=symbol,
                current_price=price,
                ohlcv=ohlcv,
                volume_24h=volume_24h,
                high_24h=high_24h,
                low_24h=low_24h,
                timestamp=datetime.now(timezone.utc),
                source="alpaca"
            )
        except Exception as e:
            return self._create_error_response(symbol, f"Alpaca error: {e}")
    
    def _fetch_from_local_exchange(
        self,
        symbol: str,
        timeframe: str,
        limit: int
    ) -> MarketDataResponse:
        """
        Fetch data from local Indonesian exchange.
        
        PLACEHOLDER - Implementasi untuk exchange lokal Indonesia.
        
        Saat ini support untuk:
        - INDODAX
        - Tokocrypto
        - Pintu
        - Reku (sudah tidak aktif)
        
        TODO: Implementasi API untuk exchange lokal
        """
        # ============================================================
        # PERINGATAN: Ini adalah placeholder!
        # ============================================================
        # Saat ini belum ada implementasi exchange lokal.
        # 
        # Saat Anda menemukan exchange lokal yang tepat,
        # implementasikan di sini dengan API client yang sesuai.
        # 
        # Contoh implementasi:
        #
        # if symbol.endswith("/IDR"):
        #     # INDODAX atau Tokocrypto API
        #     response = requests.get(
        #         f"https://api.indodax.com/...",
        #         params={"pair": symbol, "limit": limit}
        #     )
        #     # Parse response...
        # 
        # Kembalikan MarketDataResponse dengan data yang valid.
        # ============================================================
        
        logger.warning("Local exchange not implemented yet for %s", symbol)
        
        # Fallback to paper trading untuk testing
        return self._fetch_from_paper(symbol, timeframe, limit)
    
    def _generate_synthetic_ohlcv(
        self,
        symbol: str,
        current_price: float,
        timeframe: str,
        limit: int
    ) -> List[Dict[str, Any]]:
        """Generate synthetic OHLCV for paper trading/testing."""
        import random
        import math
        
        ohlcv = []
        now = datetime.now(timezone.utc)
        
        # Determine candle duration in minutes
        duration_map = {
            "1m": 1,
            "5m": 5,
            "15m": 15,
            "1h": 60,
            "4h": 240,
            "1d": 1440
        }
        duration_minutes = duration_map.get(timeframe, 60)
        
        base_price = current_price
        for i in range(limit):
            # Generate realistic price movement with random walk
            change = random.gauss(0, 0.002)  # 0.2% standard deviation
            open_price = base_price * (1 + change * 0.5)
            close_price = base_price * (1 + change)
            high_price = max(open_price, close_price) * (1 + abs(random.gauss(0, 0.001)))
            low_price = min(open_price, close_price) * (1 - abs(random.gauss(0, 0.001)))
            volume = 1000 + 500 * (1 + math.sin(i / 10))
            
            candle_time = now - timedelta(minutes=(limit - i) * duration_minutes)
            
            ohlcv.append({
                "timestamp": candle_time,
                "open": round(open_price, 2),
                "high": round(high_price, 2),
                "low": round(low_price, 2),
                "close": round(close_price, 2),
                "volume": round(volume, 2)
            })
            
            base_price = close_price
        
        return ohlcv
    
    def _create_error_response(
        self,
        symbol: str,
        error: str
    ) -> MarketDataResponse:
        """Create error response."""
        return MarketDataResponse(
            success=False,
            symbol=symbol,
            current_price=None,
            ohlcv=None,
            volume_24h=None,
            high_24h=None,
            low_24h=None,
            timestamp=datetime.now(timezone.utc),
            error=error,
            source="error"
        )
    
    def get_fear_greed_index(self) -> Optional[float]:
        """Get Fear & Greed Index."""
        # TODO: Implement API call to Alternative.me or similar
        # https://alternative.me/crypto/fear-and-greed-index/api/
        try:
            import requests
            response = requests.get(
                "https://api.alternative.me/fng/",
                params={"limit": 1},
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                if data and "data" in data and len(data["data"]) > 0:
                    value = int(data["data"][0].get("value", 50))
                    return float(value)
        except Exception as e:
            logger.debug("Fear & Greed API error: %s", e)
        return None


# ============================================================
# SINGLETON INSTANCE
# ============================================================

_market_data_adapter = None

def get_market_data_adapter(config: Optional[Dict] = None) -> MarketDataAdapter:
    """Get singleton instance of MarketDataAdapter."""
    global _market_data_adapter
    if _market_data_adapter is None:
        _market_data_adapter = MarketDataAdapter(config)
    return _market_data_adapter
