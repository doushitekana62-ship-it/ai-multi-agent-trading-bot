import json
from pathlib import Path

from core.scalping_runtime import ScalpingRuntime


def bullish_inputs(prices):
    return dict(
        price=prices[-1],
        technical=0.85,
        sentiment=0.25,
        forecast=0.70,
        mimic=0.80,
        decision=0.55,
        volatility=0.01,
        data_quality=1.0,
        prices=prices,
        volumes=[100, 105, 110, 115, 130, 150, 170, 210],
    )


def bearish_inputs(prices):
    return dict(
        price=prices[-1],
        technical=-0.85,
        sentiment=-0.25,
        forecast=-0.70,
        mimic=-0.80,
        decision=-0.55,
        volatility=0.01,
        data_quality=1.0,
        prices=prices,
        volumes=[100, 105, 110, 115, 130, 150, 170, 210],
    )


def test_stateful_buy_then_sell_realized_pnl(tmp_path):
    runtime = ScalpingRuntime(symbol="BTC/IDR", position_size=0.05)

    # Rising micro-sequence should create a validated BUY setup.
    buy_prices = [100.0, 100.1, 100.3, 100.6, 101.0, 101.4, 101.8, 102.0]
    buy_event = runtime.step(**bullish_inputs(buy_prices))
    assert buy_event["action"] == "BUY"
    assert runtime.paper.get_position("BTC/IDR") is not None

    # A bearish sequence should close the long through the strategy exit path.
    sell_prices = [102.0, 101.9, 101.7, 101.4, 101.0, 100.6, 100.3, 100.0]
    sell_event = runtime.step(**bearish_inputs(sell_prices))

    summary = runtime.summary()
    assert sell_event["action"] == "SELL"
    assert summary["entries"] == 1
    assert summary["exits"] == 1
    assert summary["active_position"] is None
    assert summary["trades"]
    assert summary["trades"][-1]["pnl"] < 0

    Path("test_results").mkdir(exist_ok=True)
    Path("test_results/scalping_market_replay.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )


def test_stateful_take_profit_closes_position():
    runtime = ScalpingRuntime(symbol="BTC/IDR", position_size=0.05)
    buy_prices = [100.0, 100.1, 100.3, 100.6, 101.0, 101.4, 101.8, 102.0]
    runtime.step(**bullish_inputs(buy_prices))
    position = runtime.paper.get_position("BTC/IDR")
    assert position is not None

    # Controller-derived target is at most 2x stop; move enough to trigger it.
    target = position["take_profit"]
    runtime.step(
        price=target,
        technical=0.0,
        sentiment=0.0,
        forecast=0.0,
        mimic=0.0,
        decision=0.0,
        volatility=0.01,
        data_quality=1.0,
        prices=[100.0, 100.2, 100.4, 100.6, 100.8, 101.0, 101.2, target],
        volumes=[100] * 8,
    )
    summary = runtime.summary()
    assert summary["take_profits"] == 1
    assert summary["active_position"] is None
    assert summary["realized_pnl"] > 0
