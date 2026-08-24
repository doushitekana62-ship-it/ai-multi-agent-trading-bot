from core.scalping_controller import ScalpingController


def test_bullish_micro_setup_can_buy():
    engine = ScalpingController()
    setup = engine.evaluate(
        technical=0.70,
        sentiment=0.20,
        forecast=0.45,
        mimic=0.65,
        decision=0.40,
        volatility=0.012,
        data_quality=1.0,
        prices=[100.0, 100.2, 100.5, 100.9, 101.2, 101.5, 101.8, 102.2],
        volumes=[100, 102, 101, 105, 110, 145],
    )
    assert setup.action == "BUY"
    assert setup.confirmations >= 3
    assert setup.confidence >= 0.55
    assert setup.position_multiplier > 0


def test_conflict_stays_hold():
    engine = ScalpingController()
    setup = engine.evaluate(
        technical=0.55,
        sentiment=-0.55,
        forecast=-0.40,
        mimic=0.50,
        decision=-0.30,
        volatility=0.012,
        prices=[100, 100.1, 100.0, 100.1, 100.0, 100.1, 100.0, 100.1],
        volumes=[100, 100, 101, 99, 100, 101],
    )
    assert setup.action == "HOLD"


def test_high_volatility_reduces_size_and_requires_more_confirmation():
    engine = ScalpingController()
    setup = engine.evaluate(
        technical=0.75,
        sentiment=0.30,
        forecast=0.50,
        mimic=0.75,
        decision=0.50,
        volatility=0.08,
        prices=[100, 100.2, 100.5, 101.0, 101.8, 102.5, 103.0, 104.0],
        volumes=[100, 120, 110, 130, 140, 200],
    )
    assert setup.action == "BUY"
    assert setup.position_multiplier <= 0.75
    assert setup.stop_distance_pct <= 0.025


def test_degraded_market_data_stays_hold():
    engine = ScalpingController()
    setup = engine.evaluate(
        technical=0.90,
        sentiment=0.50,
        forecast=0.70,
        mimic=0.80,
        decision=0.60,
        volatility=0.01,
        data_quality=0.30,
        prices=[100, 101, 102, 103],
    )
    assert setup.action == "HOLD"
