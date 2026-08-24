from types import SimpleNamespace

from integration.scalping_entry_adapter import ScalpingEntryAdapter


def _bullish_hold_result():
    return SimpleNamespace(
        final_action="HOLD",
        technical=SimpleNamespace(overall_score=0.75),
        sentiment=SimpleNamespace(overall_score=0.20),
        decision=SimpleNamespace(action_score=0.55),
        forecast=SimpleNamespace(forecast_score=0.60, primary_trend="BULLISH"),
        mimic_analysis=SimpleNamespace(net_score=0.70),
        market_scores={},
    )


def test_hold_can_be_promoted_to_validated_scalp_entry():
    adapter = ScalpingEntryAdapter()
    result = adapter.promote_only_when_hold(
        _bullish_hold_result(),
        prices=[100.0, 100.2, 100.4, 100.7, 101.0, 101.3, 101.6, 101.9],
        volumes=[100, 102, 104, 106, 110, 118, 125, 150],
        volatility=0.01,
        data_quality=1.0,
    )

    assert result["original_action"] == "HOLD"
    assert result["action"] == "BUY"
    assert result["promoted"] is True
    assert result["setup"].confirmations >= 3


def test_conflicting_hold_is_not_promoted():
    result_obj = SimpleNamespace(
        final_action="HOLD",
        technical=SimpleNamespace(overall_score=0.05),
        sentiment=SimpleNamespace(overall_score=-0.05),
        decision=SimpleNamespace(action_score=0.02),
        forecast=SimpleNamespace(forecast_score=-0.10, primary_trend="CONSOLIDATING"),
        mimic_analysis=SimpleNamespace(net_score=0.05),
        market_scores={},
    )
    adapter = ScalpingEntryAdapter()
    result = adapter.promote_only_when_hold(
        result_obj,
        prices=[100.0, 100.01, 100.0, 99.99, 100.0, 100.01, 100.0, 100.0],
        volumes=[100] * 8,
        volatility=0.01,
        data_quality=1.0,
    )

    assert result["original_action"] == "HOLD"
    assert result["action"] == "HOLD"
    assert result["promoted"] is False
