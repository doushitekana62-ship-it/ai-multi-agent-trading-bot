from core.scalping_controller import ScalpingController
from integration.scalping_pipeline import ScalpingPipelineAdapter
from paper_trading.paper_engine import PaperTradingEngine


def _open_long():
    paper = PaperTradingEngine({"initial_balance": 10000.0, "max_position_size": 0.20})
    position = paper.open_position(
        symbol="BTC/IDR",
        side="BUY",
        price=102.0,
        position_size=0.05,
        confidence=0.80,
        stop_loss=100.0,
        take_profit=105.0,
        metadata={"strategy": "AI_SCALPING"},
    )
    assert position is not None
    return paper


def test_adapter_closes_existing_long_on_dedicated_exit():
    paper = _open_long()
    adapter = ScalpingPipelineAdapter(paper, ScalpingController())

    trade = adapter.evaluate_existing_long_exit(
        symbol="BTC/IDR",
        price=101.8,
        technical=-0.80,
        sentiment=-0.20,
        forecast=-0.65,
        mimic=-0.75,
        decision=-0.50,
        volatility=0.01,
        data_quality=1.0,
        prices=[102.0, 102.0, 101.95, 101.9, 101.88, 101.85, 101.82, 101.8],
        volumes=[210, 205, 200, 195, 190, 185, 180, 175],
    )

    assert trade is not None
    assert trade["side"] == "BUY"
    assert trade["reason"] == "DEDICATED_LONG_EXIT"
    assert trade["exit_source"] == "scalping_pipeline_adapter"
    assert paper.get_position("BTC/IDR") is None
    assert paper.trade_history[-1]["reason"] == "DEDICATED_LONG_EXIT"


def test_adapter_does_not_open_or_short_when_no_long_exists():
    paper = PaperTradingEngine()
    adapter = ScalpingPipelineAdapter(paper)

    trade = adapter.evaluate_existing_long_exit(
        symbol="BTC/IDR",
        price=101.8,
        technical=-0.90,
        sentiment=-0.90,
        forecast=-0.90,
        mimic=-0.90,
        decision=-0.90,
        prices=[102.0, 102.0, 101.95, 101.9, 101.88, 101.85, 101.82, 101.8],
        volumes=[210, 205, 200, 195, 190, 185, 180, 175],
    )

    assert trade is None
    assert paper.get_position("BTC/IDR") is None
    assert paper.trade_history == []
