from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

from .config import settings

logger = logging.getLogger(__name__)
INDODAX_WS_URL = "wss://ws3.indodax.com/ws/"
# INDODAX documents a public market-data token for this endpoint. Override it in
# deployment if the venue rotates the token without requiring a code change.
INDODAX_WS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE5NDY2MTg0MTV9.UR1lBM6Eqh0yWz-PVirw1uPCxe60FdchR8eNVdsskeo"


class MarketSnapshotCollector:
    def __init__(self, interval_seconds: float = 30.0) -> None:
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._ws_task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self.latest: dict[str, dict] = {}
        self.ws_healthy = False
        self.ws_last_message_at: str | None = None
        self.ws_reconnects = 0

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="market-snapshot-collector")
        self._ws_task = asyncio.create_task(self._websocket_loop(), name="indodax-market-websocket")
        logger.info("Market snapshot collector started interval=%ss", self.interval_seconds)

    async def stop(self) -> None:
        self._stop.set()
        tasks = [task for task in (self._task, self._ws_task) if task]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._task = None
        self._ws_task = None
        self.ws_healthy = False

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self._collect_once()
            except Exception:
                logger.exception("Market snapshot REST fallback collection failed")
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
                    "source": "rest",
                })
            return rows

        rows = await asyncio.to_thread(fetch)
        for row in rows:
            self.latest[row["symbol"]] = row

    async def _websocket_loop(self) -> None:
        import websockets

        while not self._stop.is_set():
            try:
                async with websockets.asyncio.client.connect(
                    INDODAX_WS_URL,
                    open_timeout=15,
                    close_timeout=5,
                    ping_interval=20,
                    ping_timeout=20,
                    max_size=4 * 1024 * 1024,
                ) as websocket:
                    await websocket.send(json.dumps({"params": {"token": INDODAX_WS_TOKEN}, "id": 1}))
                    for index, symbol in enumerate(self._symbols(), start=2):
                        pair = symbol.replace("/", "").lower()
                        await websocket.send(json.dumps({
                            "method": 1,
                            "params": {"channel": f"market:order-book-{pair}"},
                            "id": index,
                        }))
                    self.ws_healthy = True
                    logger.info("Indodax market websocket connected symbols=%s", self._symbols())
                    async for raw in websocket:
                        if self._stop.is_set():
                            break
                        self.ws_last_message_at = datetime.now(UTC).isoformat()
                        self._consume_ws_message(raw)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.ws_healthy = False
                self.ws_reconnects += 1
                logger.warning("Indodax market websocket disconnected: %s", exc)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=min(30, 2 ** min(self.ws_reconnects, 4)))
                except asyncio.TimeoutError:
                    pass

    def _consume_ws_message(self, raw: str | bytes) -> None:
        try:
            message = json.loads(raw)
            result = message.get("result") or {}
            channel = result.get("channel", "")
            data = (result.get("data") or {}).get("data") or {}
            if not channel.startswith("market:order-book-") or not isinstance(data, dict):
                return
            pair = str(data.get("pair", "")).lower()
            symbol = next((item for item in self._symbols() if item.replace("/", "").lower() == pair), None)
            if not symbol:
                return
            bids = data.get("bid") or []
            asks = data.get("ask") or []
            best_bid = float(bids[0]["price"]) if bids else None
            best_ask = float(asks[0]["price"]) if asks else None
            bid_volume = sum(float(level.get("btc_volume", 0)) for level in bids[:10])
            ask_volume = sum(float(level.get("btc_volume", 0)) for level in asks[:10])
            total = bid_volume + ask_volume
            self.latest[symbol] = {
                "symbol": symbol,
                "timeframe": settings.timeframe,
                "captured_at": self.ws_last_message_at,
                "last_price": best_bid if best_bid is not None else best_ask,
                "bid": best_bid,
                "ask": best_ask,
                "spread_bps": ((best_ask - best_bid) / best_bid * 10000) if best_bid and best_ask else None,
                "volume": None,
                "orderbook_imbalance": ((bid_volume - ask_volume) / total) if total else None,
                "data_quality": 1.0 if bids and asks else 0.5,
                "source": "websocket",
            }
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            logger.debug("Ignoring malformed Indodax market websocket message", exc_info=True)


collector = MarketSnapshotCollector()
