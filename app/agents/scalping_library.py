from dataclasses import dataclass
from math import floor


@dataclass(frozen=True)
class ValidatedSignal:
    symbol: str
    entry_price: float
    tp_price: float
    sl_price: float
    quantity: float
    allocation_percent: float
    compound_multiplier: float


class ScalpingLibraryAgent:
    """Validates Forecast output and applies risk/compounding rules. Never places orders."""
    def __init__(self, risk_per_trade=0.5, daily_loss_limit=3.0, min_confidence=0.62, compounding_enabled=True):
        self.risk_per_trade = risk_per_trade
        self.daily_loss_limit = daily_loss_limit
        self.min_confidence = min_confidence
        self.compounding_enabled = compounding_enabled

    def validate(self, forecast, allocation_percent, equity, daily_pnl, has_open_position):
        if forecast is None or forecast.action != "buy" or forecast.confidence < self.min_confidence:
            return None
        if allocation_percent <= 0 or equity <= 0 or has_open_position:
            return None
        if daily_pnl <= -(equity * self.daily_loss_limit / 100):
            return None
        stop_distance = forecast.price - forecast.suggested_sl
        if stop_distance <= 0:
            return None
        risk_budget = equity * self.risk_per_trade / 100
        allocation_cash = equity * allocation_percent / 100
        qty = min(risk_budget / stop_distance, allocation_cash / forecast.price)
        if qty <= 0:
            return None
        profit_pct = max(0.0, daily_pnl / equity * 100)
        multiplier = 1.0
        if self.compounding_enabled:
            multiplier = min(1.25, 1.0 + floor(profit_pct / 5.0) * 0.05)
        qty = min(qty * multiplier, allocation_cash / forecast.price)
        return ValidatedSignal(forecast.symbol, forecast.price, forecast.suggested_tp, forecast.suggested_sl, qty, allocation_percent, multiplier)
