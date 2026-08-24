from types import SimpleNamespace

from integration.scalping_entry_adapter import ScalpingEntryAdapter


def test_hold_can_be_promoted_to_validated_scalping_buy():
    result = SimpleNamespace(
        final_action="HOLD",
        technical=SimpleNamespace(overall_score=0.80),
        sentiment=SimpleNamespace(overall_score=0.30),
        decision=SimpleNamespace(action_score=0.50),
        forecast=SimpleNamespace(forecast_score=0.60, primary_trend="BULLISH"),
        mimic_analysis=SimpleNamespace(net_score=0.70),
        market_scores={},
    )

    prices = [100.0, 100.1, 100.2, 100.3, 100.4, 100.6, 100.8, 101.0]
    volumes = [100, 100, 100, 100, 100, 110, 120, 140]

    candidate = ScalpingEntryAdapter().promote_only_when_hold(
        result,
        prices=prices,
        volumes=volumes,
        volatility=0.01,
        data_quality=1.0,
    )

    assert candidate["original_action"] == "HOLD"
    assert candidate["action"] == "BUY"
    assert candidate["promoted"] is True
    assert candidate["setup"].confirmations >= 3
    assert candidate["setup"].confidence >= 0.55


def test_non_hold_action_is_never_rewritten_by_entry_adapter():
    result = SimpleNamespace(final_action="SELL", market_scores={})

    candidate = ScalpingEntryAdapter().promote_only_when_hold(
        result,
        prices=[100.0] * 8,
        volumes=[100] * 8,
    )

    assert candidate["original_action"] == "SELL"
    assert candidate["action"] == "SELL"
    assert candidate["promoted"] is False
