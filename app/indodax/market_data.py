from dataclasses import dataclass
import time
from app.indodax.client import IndodaxClient


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    price: float
    bid: float
    ask: float
    spread_percent: float
    bid_depth: float
    ask_depth: float
    book_imbalance: float
    timestamp: float


class MarketDataService:
    """REST fallback microstructure adapter; designed to be replaceable by WS state."""

    def __init__(self, client: IndodaxClient | None = None):
        self.client = client or IndodaxClient()

    def snapshot(self, symbol: str, ticker: dict | None = None) -> MarketSnapshot:
        ticker = ticker or self.client.get_ticker(symbol)
        depth = self.client.get_depth(symbol)
        bids = depth.get("buy", [])
        asks = depth.get("sell", [])
        bid = float(bids[0][0]) if bids else float(ticker.get("price", 0))
        ask = float(asks[0][0]) if asks else float(ticker.get("price", 0))
        bid_depth = sum(float(row[1]) * float(row[0]) for row in bids[:10])
        ask_depth = sum(float(row[1]) * float(row[0]) for row in asks[:10])
        total = bid_depth + ask_depth
        imbalance = (bid_depth - ask_depth) / total if total else 0.0
        mid = (bid + ask) / 2 if bid and ask else float(ticker.get("price", 0))
        spread = (ask - bid) / mid * 100 if mid > 0 else 100.0
        return MarketSnapshot(symbol.lower(), float(ticker.get("price", 0)), bid, ask,
                              spread, bid_depth, ask_depth, imbalance, time.time())
