from core.dynamic_exit import BASE_TP_PCT, forecast_exit


def position(entry=100.0):
    return {"entry_price": entry, "side": "BUY"}


def test_strong_forecast_extends_take_profit():
    result = forecast_exit(position(), 100.50, 0.80, 0.10, 0.15, 0.20, 0.001)
    assert result["continuation"] is True
    assert result["take_profit_pct"] > BASE_TP_PCT
    assert result["exit_action"] == "HOLD"


def test_dynamic_tp_closes_when_extended_target_is_reached():
    result = forecast_exit(position(), 101.10, 0.80, 0.10, 0.15, 0.20, 0.001)
    assert result["exit_action"] == "SELL"
    assert result["exit_reason"] == "DYNAMIC_TP_HIT"


def test_forecast_reversal_exits_profitable_scalp():
    result = forecast_exit(position(), 100.20, -0.20, -0.05, 0.01, 0.01, 0.001)
    assert result["exit_action"] == "SELL"
    assert result["exit_reason"] == "FORECAST_REVERSAL"


def test_no_profit_does_not_let_forecast_bypass_risk_stop():
    result = forecast_exit(position(), 99.80, -1.0, -0.10, -0.10, -0.10, 0.001)
    assert result["exit_action"] == "HOLD"
