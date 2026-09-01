from fronted.risk_engine import initial_levels, settings_with_defaults, update_protection


def points(prices):
    return [{"timestamp": i * 60, "price": price} for i, price in enumerate(prices, start=1)]


def test_balanced_profile_uses_atr_and_two_risk_reward():
    settings = settings_with_defaults({"stop_loss_mode": "ATR", "take_profit_mode": "RISK_REWARD", "stop_atr_multiplier": 1.5, "risk_reward_ratio": 2.0})
    levels = initial_levels(100.0, points([100, 101, 99, 102, 100, 103, 101, 104, 102, 105, 103, 106, 104, 107]), settings)
    assert levels["stop_loss"] < 100 < levels["take_profit"]
    assert levels["risk_reward"] == 2.0


def test_take_profit_is_triggered():
    settings = settings_with_defaults({"stop_loss_mode": "FIXED_PERCENT", "stop_loss_pct": 1.0, "take_profit_mode": "FIXED_PERCENT", "take_profit_pct": 2.0, "trailing_enabled": False})
    position = {"entry_price": 100.0, "created_at": "2026-09-01T00:00:00+00:00"}
    update_protection(position, 100.0, points([100, 100.2, 100.1]), settings)
    result = update_protection(position, 102.0, points([100, 100.2, 102.0]), settings)
    assert result["triggered"] is True
    assert result["reason"] == "TAKE_PROFIT"


def test_trailing_stop_locks_profit():
    settings = settings_with_defaults({"stop_loss_mode": "FIXED_PERCENT", "stop_loss_pct": 2.0, "take_profit_mode": "FIXED_PERCENT", "take_profit_pct": 10.0, "trailing_enabled": True, "trailing_mode": "PERCENT", "trailing_pct": 1.0, "break_even_enabled": True, "break_even_trigger_r": 1.0})
    position = {"entry_price": 100.0, "created_at": "2026-09-01T00:00:00+00:00"}
    update_protection(position, 103.0, points([100, 101, 102, 103]), settings)
    assert position["stop_loss"] > 100.0
    result = update_protection(position, position["stop_loss"], points([100, 101, 102, position["stop_loss"]]), settings)
    assert result["triggered"] is True
    assert result["reason"] in {"TRAILING_STOP", "BREAK_EVEN"}
