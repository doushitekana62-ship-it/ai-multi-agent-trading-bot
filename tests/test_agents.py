from app.agents.forecast_agent import ForecastAgent
from app.agents.scalping_library import ScalpingLibraryAgent

def test_forecast_levels_are_ordered():
    prices = [100 + i * 0.1 for i in range(30)]
    f = ForecastAgent(0.5).analyze("btcidr", prices)
    assert f is not None
    assert f.suggested_tp > f.price > f.suggested_sl
    assert 0 <= f.confidence <= 1

def test_daily_loss_limit_blocks_new_trade():
    prices = [100 + i * 0.1 for i in range(30)]
    f = ForecastAgent(0.5).analyze("btcidr", prices)
    signal = ScalpingLibraryAgent(0.5, 3, 0.5).validate(f, 20, 1_000_000, -40_000, False)
    assert signal is None
