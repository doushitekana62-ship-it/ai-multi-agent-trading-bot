"""Forecast-driven dynamic take-profit policy for the paper scalping path."""
from __future__ import annotations
from typing import Any, Dict

BASE_TP_PCT = 0.40
MAX_DYNAMIC_TP_PCT = 1.20


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def forecast_exit(position: Dict[str, Any], price: float, forecast: float, m1: float, m3: float, m5: float, volatility: float) -> Dict[str, Any]:
    entry = _num(position.get("entry_price"))
    current = _num(price)
    if entry <= 0 or current <= 0:
        return {"exit_action": "HOLD", "exit_reason": "INVALID_ENTRY"}

    side = str(position.get("side") or position.get("action") or "BUY").upper()
    pnl_pct = ((current / entry) - 1.0) * 100.0 if side == "BUY" else ((entry / current) - 1.0) * 100.0
    forecast = max(-1.0, min(1.0, _num(forecast)))
    m1, m3, m5 = _num(m1), _num(m3), _num(m5)

    # Forecast does not replace the deterministic risk engine. It only chooses
    # how much profit to pursue before the risk engine remains the hard gate.
    continuation = forecast >= 0.25 and m1 > 0 and m3 > 0 and m5 > 0
    extension = max(0.0, min(0.60, forecast * 0.60))
    momentum_bonus = 0.20 if continuation else 0.0
    dynamic_tp = max(BASE_TP_PCT, min(MAX_DYNAMIC_TP_PCT, BASE_TP_PCT + extension + momentum_bonus))
    trail = max(0.10, min(0.30, abs(_num(volatility, 0.001)) * 100.0 * 1.5))

    if pnl_pct >= dynamic_tp:
        return {"exit_action": "SELL", "exit_reason": "DYNAMIC_TP_HIT", "pnl_pct": pnl_pct, "take_profit_pct": dynamic_tp, "base_take_profit_pct": BASE_TP_PCT, "forecast": forecast, "continuation": continuation, "trailing_stop_pct": trail}

    if pnl_pct >= BASE_TP_PCT and not continuation:
        return {"exit_action": "SELL", "exit_reason": "FORECAST_NO_CONTINUATION", "pnl_pct": pnl_pct, "take_profit_pct": dynamic_tp, "base_take_profit_pct": BASE_TP_PCT, "forecast": forecast, "continuation": False, "trailing_stop_pct": trail}

    # A profitable position is allowed to close early when the forecast and
    # immediate momentum reverse. Loss exits remain under deterministic risk.
    if pnl_pct >= 0.10 and forecast <= 0.0 and m1 < 0:
        return {"exit_action": "SELL", "exit_reason": "FORECAST_REVERSAL", "pnl_pct": pnl_pct, "take_profit_pct": dynamic_tp, "base_take_profit_pct": BASE_TP_PCT, "forecast": forecast, "continuation": False, "trailing_stop_pct": trail}

    return {"exit_action": "HOLD", "exit_reason": "FORECAST_CONTINUATION" if continuation else "TP_NOT_REACHED", "pnl_pct": pnl_pct, "take_profit_pct": dynamic_tp, "base_take_profit_pct": BASE_TP_PCT, "forecast": forecast, "continuation": continuation, "trailing_stop_pct": trail}
