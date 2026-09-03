"""Deterministic paper-trading risk control plane.

This module owns entry eligibility and dynamic protection. It never generates a
market signal and cannot turn a HOLD into a trade.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite

DEFAULT_RISK_SETTINGS = {
    "enabled": True,
    "stop_loss_mode": "ATR",
    "take_profit_mode": "RISK_REWARD",
    "stop_loss_pct": 0.80,
    "take_profit_pct": 1.60,
    "atr_period": 14,
    "stop_atr_multiplier": 1.50,
    "take_profit_atr_multiplier": 2.50,
    "risk_reward_ratio": 2.0,
    "profit_activation_enabled": True,
    "profit_activation_pct": 1.0,
    "hard_take_profit_enabled": False,
    "trailing_enabled": True,
    "trailing_mode": "ATR",
    "trailing_atr_multiplier": 1.25,
    "trailing_pct": 0.60,
    "break_even_enabled": True,
    "break_even_trigger_r": 1.0,
    "break_even_offset_pct": 0.05,
    "fee_rate": 0.0015,
    "slippage_bps": 5.0,
    "max_hold_minutes": 15,
    "max_position_size": 0.10,
    "max_total_exposure": 0.30,
    "max_daily_loss_pct": 0.03,
    "minimum_confidence": 0.55,
    "minimum_net_edge_pct": 0.45,
}


def settings_with_defaults(value=None):
    out = dict(DEFAULT_RISK_SETTINGS)
    if isinstance(value, dict):
        out.update(value)
    out["stop_loss_mode"] = str(out.get("stop_loss_mode") or "ATR").upper()
    out["take_profit_mode"] = str(out.get("take_profit_mode") or "RISK_REWARD").upper()
    out["trailing_mode"] = str(out.get("trailing_mode") or "ATR").upper()
    float_keys = (
        "stop_loss_pct", "take_profit_pct", "stop_atr_multiplier",
        "take_profit_atr_multiplier", "risk_reward_ratio", "profit_activation_pct",
        "trailing_atr_multiplier", "trailing_pct", "break_even_trigger_r",
        "break_even_offset_pct", "fee_rate", "slippage_bps", "max_position_size",
        "max_total_exposure", "max_daily_loss_pct", "minimum_confidence",
        "minimum_net_edge_pct",
    )
    for key in float_keys:
        try:
            out[key] = float(out[key])
        except (TypeError, ValueError):
            out[key] = DEFAULT_RISK_SETTINGS[key]
    try:
        out["atr_period"] = max(2, min(100, int(out.get("atr_period", 14))))
    except (TypeError, ValueError):
        out["atr_period"] = 14
    try:
        out["max_hold_minutes"] = max(0, int(out.get("max_hold_minutes", 15)))
    except (TypeError, ValueError):
        out["max_hold_minutes"] = 15
    out["fee_rate"] = max(0.0, min(0.02, out["fee_rate"])); out["slippage_bps"] = max(0.0, min(100.0, out["slippage_bps"]))
    out["stop_loss_pct"] = max(0.05, min(20.0, out["stop_loss_pct"])); out["take_profit_pct"] = max(0.05, min(50.0, out["take_profit_pct"]))
    out["stop_atr_multiplier"] = max(0.25, min(10.0, out["stop_atr_multiplier"])); out["take_profit_atr_multiplier"] = max(0.25, min(20.0, out["take_profit_atr_multiplier"]))
    out["risk_reward_ratio"] = max(0.5, min(10.0, out["risk_reward_ratio"])); out["profit_activation_pct"] = max(0.05, min(50.0, out["profit_activation_pct"]))
    out["trailing_atr_multiplier"] = max(0.25, min(10.0, out["trailing_atr_multiplier"])); out["trailing_pct"] = max(0.05, min(20.0, out["trailing_pct"]))
    out["break_even_trigger_r"] = max(0.25, min(10.0, out["break_even_trigger_r"])); out["break_even_offset_pct"] = max(0.0, min(2.0, out["break_even_offset_pct"]))
    out["max_position_size"] = max(0.01, min(0.50, out["max_position_size"])); out["max_total_exposure"] = max(0.01, min(1.0, out["max_total_exposure"]))
    out["max_daily_loss_pct"] = max(0.001, min(0.25, out["max_daily_loss_pct"])); out["minimum_confidence"] = max(0.0, min(1.0, out["minimum_confidence"]))
    out["minimum_net_edge_pct"] = max(0.0, min(10.0, out["minimum_net_edge_pct"]))
    for key in ("enabled", "profit_activation_enabled", "hard_take_profit_enabled", "trailing_enabled", "break_even_enabled"):
        out[key] = bool(out.get(key, DEFAULT_RISK_SETTINGS[key]))
    return out


def _num(value, default=0.0):
    try:
        value = float(value)
        return value if isfinite(value) else default
    except (TypeError, ValueError):
        return default


def _ts(point):
    value = _num(point.get("timestamp") or point.get("date"))
    return value / 1000.0 if value > 1_000_000_000_000 else value


def minute_candles(points, lookback_minutes=180):
    rows = {}
    valid = [p for p in points if isinstance(p, dict) and _ts(p) > 0 and _num(p.get("price")) > 0]
    if not valid:
        return []
    anchor = max(_ts(p) for p in valid); floor = anchor - lookback_minutes * 60
    for point in valid:
        ts = _ts(point)
        if ts < floor or ts > anchor: continue
        price = _num(point.get("price")); bucket = int(ts // 60) * 60
        row = rows.setdefault(bucket, {"timestamp": bucket, "open": price, "high": price, "low": price, "close": price})
        row["high"] = max(row["high"], price); row["low"] = min(row["low"], price); row["close"] = price
    return [rows[key] for key in sorted(rows)]


def atr(points, period=14):
    candles = minute_candles(points, max(180, period * 4))
    if len(candles) < 2: return None
    trs = []; previous_close = None
    for candle in candles:
        high, low, close = candle["high"], candle["low"], candle["close"]
        tr = high - low if previous_close is None else max(high - low, abs(high - previous_close), abs(low - previous_close))
        trs.append(max(0.0, tr)); previous_close = close
    window = trs[-max(2, int(period)):]
    return sum(window) / len(window) if window else None


def initial_levels(entry_price, points, settings=None):
    cfg = settings_with_defaults(settings); entry = _num(entry_price)
    if entry <= 0: return {"stop_loss": None, "take_profit": None, "profit_activation_price": None, "atr": None, "risk_distance": None}
    current_atr = atr(points, cfg["atr_period"])
    if cfg["stop_loss_mode"] == "FIXED_PERCENT": risk_distance = entry * cfg["stop_loss_pct"] / 100.0
    elif current_atr and cfg["stop_loss_mode"] == "ATR": risk_distance = current_atr * cfg["stop_atr_multiplier"]
    else: risk_distance = entry * cfg["stop_loss_pct"] / 100.0
    if cfg["take_profit_mode"] == "FIXED_PERCENT": reward_distance = entry * cfg["take_profit_pct"] / 100.0
    elif cfg["take_profit_mode"] == "ATR" and current_atr: reward_distance = current_atr * cfg["take_profit_atr_multiplier"]
    else: reward_distance = risk_distance * cfg["risk_reward_ratio"]
    return {"stop_loss": max(0.0, entry - risk_distance), "take_profit": entry + reward_distance,
            "profit_activation_price": entry * (1.0 + cfg["profit_activation_pct"] / 100.0) if cfg["profit_activation_enabled"] else None,
            "atr": current_atr, "risk_distance": risk_distance, "reward_distance": reward_distance,
            "risk_reward": reward_distance / risk_distance if risk_distance > 0 else None, "settings": cfg}


def update_protection(position, current_price, points, settings=None):
    cfg = settings_with_defaults(settings); price = _num(current_price); entry = _num(position.get("entry_price"))
    if entry <= 0 or price <= 0: return {"triggered": False, "position": position, "reason": None}
    if "initial_stop_loss" not in position or not position.get("initial_stop_loss"):
        levels = initial_levels(entry, points, cfg); position["initial_stop_loss"] = levels["stop_loss"]; position["initial_take_profit"] = levels["take_profit"]
        position["profit_activation_price"] = levels.get("profit_activation_price"); position["stop_loss"] = levels["stop_loss"]; position["take_profit"] = levels["take_profit"]
        position["atr_at_entry"] = levels["atr"]; position["risk_distance"] = levels["risk_distance"]
    else:
        levels = {"atr": atr(points, cfg["atr_period"]), "risk_distance": _num(position.get("risk_distance"))}
    high_water = max(_num(position.get("high_water_mark"), entry), price); position["high_water_mark"] = high_water
    activation_price = _num(position.get("profit_activation_price")) if cfg["profit_activation_enabled"] else 0.0
    profit_active = bool(position.get("profit_active")) or (activation_price > 0 and high_water >= activation_price); position["profit_active"] = profit_active
    risk_distance = _num(position.get("risk_distance")); stop = _num(position.get("stop_loss"))
    if cfg["break_even_enabled"] and risk_distance > 0 and high_water >= entry + risk_distance * cfg["break_even_trigger_r"]:
        position["break_even_armed"] = True; stop = max(stop, entry * (1.0 + cfg["break_even_offset_pct"] / 100.0)); position["stop_loss"] = stop
    if cfg["trailing_enabled"] and profit_active and high_water > entry:
        if cfg["trailing_mode"] == "PERCENT": trail_distance = high_water * cfg["trailing_pct"] / 100.0
        else:
            trail_atr = levels.get("atr") or _num(position.get("atr_at_entry")); trail_distance = trail_atr * cfg["trailing_atr_multiplier"] if trail_atr else high_water * cfg["trailing_pct"] / 100.0
        if trail_distance > 0: stop = max(stop, high_water - trail_distance); position["stop_loss"] = stop
    if price <= _num(position.get("stop_loss")):
        reason = "BREAK_EVEN" if position.get("break_even_armed") and price >= entry else "TRAILING_STOP" if high_water > entry and _num(position.get("stop_loss")) > _num(position.get("initial_stop_loss")) else "STOP_LOSS"
        return {"triggered": True, "reason": reason, "position": position, "stop_loss": position.get("stop_loss"), "take_profit": position.get("take_profit"), "profit_activation_price": activation_price or None, "profit_active": profit_active, "atr": levels.get("atr")}
    hard_tp = bool(cfg["hard_take_profit_enabled"])
    if not cfg["trailing_enabled"] and not hard_tp: hard_tp = True
    if hard_tp and price >= _num(position.get("take_profit")):
        return {"triggered": True, "reason": "TAKE_PROFIT", "position": position, "stop_loss": position.get("stop_loss"), "take_profit": position.get("take_profit"), "profit_activation_price": activation_price or None, "profit_active": profit_active, "atr": levels.get("atr")}
    if cfg["max_hold_minutes"] > 0:
        try:
            created = datetime.fromisoformat(str(position.get("created_at"))); created = created.replace(tzinfo=timezone.utc) if created.tzinfo is None else created
            if (datetime.now(timezone.utc) - created).total_seconds() / 60.0 >= cfg["max_hold_minutes"]:
                return {"triggered": True, "reason": "TIME_EXIT", "position": position, "stop_loss": position.get("stop_loss"), "take_profit": position.get("take_profit"), "profit_activation_price": activation_price or None, "profit_active": profit_active, "atr": levels.get("atr")}
        except (TypeError, ValueError, OverflowError): pass
    return {"triggered": False, "reason": None, "position": position, "stop_loss": position.get("stop_loss"), "take_profit": position.get("take_profit"), "profit_activation_price": activation_price or None, "profit_active": profit_active, "atr": levels.get("atr")}


def apply_slippage(price, side, slippage_bps):
    price = _num(price); factor = max(0.0, _num(slippage_bps)) / 10000.0
    return price * (1.0 + factor) if str(side).upper() == "BUY" else price * (1.0 - factor)


def evaluate_entry(*, action, confidence, requested_position_size, net_edge_pct, balance, portfolio_value,
                   open_positions, current_exposure, settings=None):
    """Return a complete, auditable hard-gate result for a candidate entry."""
    cfg = settings_with_defaults(settings); action = str(action or "HOLD").upper(); confidence = _num(confidence); requested = _num(requested_position_size)
    balance = max(0.0, _num(balance)); portfolio = max(0.0, _num(portfolio_value)); positions = int(_num(open_positions)); exposure = max(0.0, _num(current_exposure)); edge = _num(net_edge_pct)
    checks = {
        "risk_enabled": bool(cfg["enabled"]), "action_is_entry": action in {"BUY", "STRONG_BUY"},
        "confidence": confidence >= cfg["minimum_confidence"], "net_edge": edge >= cfg["minimum_net_edge_pct"],
        "position_limit": requested > 0 and requested <= cfg["max_position_size"],
        "open_position_limit": positions < 3, "exposure_limit": exposure + requested <= cfg["max_total_exposure"],
        "balance_available": balance > 0 and portfolio > 0,
    }
    approved = all(checks.values()); reason = "RISK_CHECKS_PASSED" if approved else next((name.upper() for name, ok in checks.items() if not ok), "RISK_REJECTED")
    approved_size = min(requested, cfg["max_position_size"], max(0.0, cfg["max_total_exposure"] - exposure)) if approved else 0.0
    return {"approved": approved and approved_size > 0, "action": action, "requested_position_size": requested,
            "approved_position_size": approved_size if approved else 0.0, "confidence": confidence, "net_edge_pct": edge,
            "checks": checks, "reason": reason if approved else f"{reason}:FAILED", "timestamp": datetime.now(timezone.utc).isoformat()}
