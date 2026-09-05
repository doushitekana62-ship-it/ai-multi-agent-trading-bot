from app.agents.forecast_agent import ForecastAgent
from app.agents.regime_engine import RegimeEngine
from app.agents.risk_engine import RiskEngine
from app.agents.scalping_library import ScalpingLibraryAgent
from app.agents.signal_engine import SignalEngine


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


def test_regime_engine_rejects_warmup():
    assert RegimeEngine().classify([100 + i for i in range(10)]) is None


def test_signal_gate_rejects_bad_execution():
    prices = [100 + i * 0.2 for i in range(60)]
    forecast = ForecastAgent(0.5).analyze("btcidr", prices)
    regime = RegimeEngine().classify(prices)
    decision = SignalEngine(min_score=80).evaluate(
        forecast, regime, spread_percent=0.8, book_imbalance=0.9,
        btc_return_percent=0.2, liquidity_score=1.0,
        support_resistance_score=0.8, data_quality=1.0,
    )
    assert decision.action == "NO_TRADE"
    assert "spread" in decision.reasons


def test_risk_engine_scales_after_drawdown():
    decision = RiskEngine().evaluate(
        daily_pnl=0, daily_start_balance=1_000_000,
        equity=980_000, peak_equity=1_000_000,
        open_risk_percent=0.5, loss_streak=0,
    )
    assert decision.allowed
    assert decision.risk_multiplier == 0.75


def test_risk_engine_blocks_loss_streak():
    decision = RiskEngine().evaluate(
        daily_pnl=-10_000, daily_start_balance=1_000_000,
        equity=990_000, peak_equity=1_000_000,
        open_risk_percent=0, loss_streak=3,
    )
    assert not decision.allowed
    assert "loss_streak" in decision.reasons
