from core.adaptive_scalping import AdaptiveScalpingEngine


def test_strong_bullish_confluence_can_enter():
    engine = AdaptiveScalpingEngine()
    signal = engine.evaluate(technical=0.65, sentiment=0.25, forecast=0.45,
                             mimic=0.70, momentum=0.55, volatility=0.02)
    assert signal.action == "BUY"
    assert signal.confidence >= 0.48
    assert signal.position_multiplier > 0


def test_conflicting_signals_hold():
    engine = AdaptiveScalpingEngine()
    signal = engine.evaluate(technical=0.55, sentiment=-0.55, forecast=-0.40,
                             mimic=0.50, momentum=-0.40, volatility=0.02)
    assert signal.action == "HOLD"


def test_high_volatility_requires_more_confirmation():
    engine = AdaptiveScalpingEngine()
    signal = engine.evaluate(technical=0.30, sentiment=0.15, forecast=0.20,
                             mimic=0.30, momentum=0.20, volatility=0.08)
    assert signal.action == "HOLD"
