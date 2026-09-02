from fronted.risk_engine import initial_levels, settings_with_defaults, update_protection


def points(prices):
    return [{"timestamp": i * 60, "price": price} for i, price in enumerate(prices, start=1)]


def test_profit_activation_is_not_a_hard_profit_ceiling():
    settings = settings_with_defaults({
        "stop_loss_mode": "FIXED_PERCENT",
        "stop_loss_pct": 1.0,
        "take_profit_mode": "FIXED_PERCENT",
        "take_profit_pct": 2.0,
        "profit_activation_enabled": True,
        "profit_activation_pct": 1.0,
        "hard_take_profit_enabled": False,
        "trailing_enabled": True,
        "trailing_mode": "PERCENT",
        "trailing_pct": 0.5,
        "break_even_enabled": False,
    })
    levels = initial_levels(100.0, points([100, 100.2, 100.5]), settings)
    assert levels["profit_activation_price"] == 101.0

    position = {"entry_price": 100.0, "created_at": "2026-09-02T00:00:00+00:00"}
    result = update_protection(position, 101.0, points([100, 100.5, 101.0]), settings)
    assert result["triggered"] is False
    assert position["profit_active"] is True
    assert position["high_water_mark"] == 101.0


def test_profit_activation_allows_momentum_to_run_until_trailing_reversal():
    settings = settings_with_defaults({
        "stop_loss_mode": "FIXED_PERCENT",
        "stop_loss_pct": 1.0,
        "take_profit_mode": "FIXED_PERCENT",
        "take_profit_pct": 2.0,
        "profit_activation_enabled": True,
        "profit_activation_pct": 1.0,
        "hard_take_profit_enabled": False,
        "trailing_enabled": True,
        "trailing_mode": "PERCENT",
        "trailing_pct": 0.5,
        "break_even_enabled": False,
    })
    position = {"entry_price": 100.0, "created_at": "2026-09-02T00:00:00+00:00"}

    update_protection(position, 103.0, points([100, 101, 102, 103]), settings)
    assert position["high_water_mark"] == 103.0
    assert position["stop_loss"] > 100.0

    result = update_protection(position, 102.4, points([100, 101, 103, 102.4]), settings)
    assert result["triggered"] is True
    assert result["reason"] == "TRAILING_STOP"
