from dataclasses import dataclass
from typing import Literal

Mode = Literal["paper", "live"]

@dataclass(frozen=True)
class MarketTick:
    symbol: str
    price: float
    timestamp: float

@dataclass(frozen=True)
class OrderResult:
    order_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    fee: float
    mode: Mode
