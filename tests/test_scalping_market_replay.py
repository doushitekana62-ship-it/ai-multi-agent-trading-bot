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
        volumes=[210, 190, 175, 160, 145, 130, 115, 100],
    )


def test_stateful_buy_then_sell_realized_pnl(tmp_path):
    runtime = ScalpingRuntime(symbol="BTC/IDR", position_size=0.05)

    buy_prices = [100.0, 100.1, 100.3, 100.6, 101.0, 101.4, 101.8, 102.0]
    buy_event = runtime.step(**bullish_inputs(buy_prices))
    assert buy_event["action"] == "BUY"
    assert runtime.paper.get_position("BTC/IDR") is not None

    # Use a decisive bearish reversal so the validated scalping exit path is exercised.
    sell_prices = [102.0, 101.8, 101.5, 101.1, 100.7, 100.4, 100.1, 99.8]
    sell_event = runtime.step(**bearish_inputs(sell_prices))

    summary = runtime.summary()
    assert sell_event["setup_action"] == "SELL"
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


def test_dedicated_long_exit_closes_even_when_entry_setup_is_hold():
    runtime = ScalpingRuntime(symbol="BTC/IDR", position_size=0.05)
    buy_prices = [100.0, 100.1, 100.3, 100.6, 101.0, 101.4, 101.8, 102.0]
    runtime.step(**bullish_inputs(buy_prices))
    assert runtime.paper.get_position("BTC/IDR") is not None

    # Directional evidence is bearish, but deliberately weaken the market-structure
    # sequence so the normal entry-quality controller can return HOLD. The dedicated
    # exit path must still close the already-open spot long.
    exit_event = runtime.step(
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

    summary = runtime.summary()
    assert exit_event["action"] == "SELL"
    assert exit_event["exit_reason"] == "DEDICATED_LONG_EXIT"
    assert summary["entries"] == 1
    assert summary["exits"] == 1
    assert summary["active_position"] is None


def test_stateful_take_profit_closes_position():
    runtime = ScalpingRuntime(symbol="BTC/IDR", position_size=0.05)
    buy_prices = [100.0, 100.1, 100.3, 100.6, 101.0, 101.4, 101.8, 102.0]
    runtime.step(**bullish_inputs(buy_prices))
    position = runtime.paper.get_position("BTC/IDR")
    assert position is not None

    target = position["take_profit"]
    event = runtime.step(
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
    assert event["action"] == "SELL"
    assert event["exit_reason"] == "TAKE_PROFIT"
    assert summary["take_profits"] == 1
    assert summary["active_position"] is None
    assert summary["realized_pnl"] > 0
