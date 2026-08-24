"""Integration contract for scalping entry fallback.

This test intentionally exercises the decision boundary without contacting an
exchange. The production engine must preserve risk/execution gates when a
normal Orchestrator HOLD is promoted to a validated scalping candidate.
"""

from core.scalping_controller import ScalpingController


def test_scalping_entry_candidate_is_validated_before_execution():
    controller = ScalpingController()
    result = controller.evaluate(
        technical=0.90,
        sentiment=0.45,
        forecast=0.72,
        decision=0.60,
        mimic=0.78,
        volatility=0.01,
        data_quality=1.0,
        prices=[100, 100.05, 100.10, 100.20, 100.35, 100.50, 100.70, 100.90],
        volumes=[100, 105, 110, 120, 135, 150, 170, 190],
    )
    assert result.action == "BUY"
    assert result.is_valid_setup is True
    assert result.confidence >= 0.55
    assert len(result.confirmations) >= 3
