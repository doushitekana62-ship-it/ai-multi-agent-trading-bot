from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from .config import settings

logger = logging.getLogger(__name__)


class MarketSnapshotCollector:
    def __init__(self, interval_seconds: float = 30.0) -> None:
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self.latest: dict[str, dict] = {}

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="market-snapshot-collector")
        logger.info("Market snapshot collector started interval=%ss", self.interval_seconds)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self._collect_once()
            except Exception:
                logger.exception("Market snapshot collection failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                continue

    @staticmethod
    def _symbols() -> list[str]:
        return [item.strip() for item in settings.trading_pairs.split(",") if item.strip()]

    async def _collect_once(self) -> None:
        import ccxt

        symbols = self._symbols()
        if not symbols:
            return

        def fetch() -> list[dict]:
            exchange = ccxt.indodax({"enableRateLimit": True})
            exchange.load_markets()
            rows: list[dict] = []
            for symbol in symbols:
                if symbol not in exchange.markets:
                    logger.warning("Skipping unavailable Indodax symbol=%s", symbol)
                    continue
                ticker = exchange.fetch_ticker(symbol)
                book = exchange.fetch_order_book(symbol, limit=10)
                bid = ticker.get("bid")
                ask = ticker.get("ask")
                spread_bps = ((ask - bid) / bid * 10000) if bid and ask and bid > 0 else None
                bid_volume = sum(float(level[1]) for level in book.get("bids", [])[:10])
                ask_volume = sum(float(level[1]) for level in book.get("asks", [])[:10])
                total = bid_volume + ask_volume
                imbalance = ((bid_volume - ask_volume) / total) if total else None
                rows.append({
                    "symbol": symbol,
                    "timeframe": settings.timeframe,
                    "captured_at": datetime.now(UTC).isoformat(),
                    "last_price": ticker.get("last"),
                    "bid": bid,
                    "ask": ask,
                    "spread_bps": spread_bps,
                    "volume": ticker.get("baseVolume"),
                    "orderbook_imbalance": imbalance,
                    "data_quality": 1.0 if bid and ask and book.get("bids") and book.get("asks") else 0.5,
                })
            return rows

        rows = await asyncio.to_thread(fetch)
        for row in rows:
            self.latest[row["symbol"]] = row


collector = MarketSnapshotCollector()
