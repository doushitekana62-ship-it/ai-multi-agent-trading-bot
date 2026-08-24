import pytest

from core.executor import Executor


@pytest.fixture
def executor(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    instance = Executor({
        "exchange_mode": "paper",
        "paper": {"initial_balance": 1_000_000, "fee_rate": 0.0, "slippage_rate": 0.0},
        "daily_loss_limit": 0.05,
        "max_open_positions": 1,
    })
    instance.paper_trading.set_test_price("BTC/IDR", 100_000_000)
    instance.paper_trading.set_test_price("ETH/IDR", 5_000_000)
    return instance


def test_buy_then_take_profit_closes_position(executor):
    order = executor.execute("BTC/IDR", "BUY", 0.9, 0.1, stop_loss=99_000_000, take_profit=101_000_000)
    assert order is not None
    executor.paper_trading.set_test_price("BTC/IDR", 101_000_000)
    executor.monitor_positions()
    assert "BTC/IDR" not in executor.active_positions
    assert executor.order_history[-1].metadata["close_reason"] == "TAKE_PROFIT"
    assert executor.daily_pnl > 0


def test_buy_then_stop_loss_closes_position(executor):
    order = executor.execute("BTC/IDR", "BUY", 0.9, 0.1, stop_loss=99_000_000, take_profit=101_000_000)
    assert order is not None
    executor.paper_trading.set_test_price("BTC/IDR", 99_000_000)
    executor.monitor_positions()
    assert "BTC/IDR" not in executor.active_positions
    assert executor.order_history[-1].metadata["close_reason"] == "STOP_LOSS"
    assert executor.daily_pnl < 0


def test_duplicate_entry_is_blocked(executor):
    assert executor.execute("BTC/IDR", "BUY", 0.9, 0.1) is not None
    assert executor.execute("BTC/IDR", "BUY", 0.9, 0.1) is None


def test_sell_without_position_is_blocked(executor):
    assert executor.execute("BTC/IDR", "SELL", 0.9, 0.1) is None


def test_daily_loss_blocks_next_entry(executor):
    assert executor.execute("BTC/IDR", "BUY", 0.9, 0.9, stop_loss=95_000_000) is not None
    executor.paper_trading.set_test_price("BTC/IDR", 94_000_000)
    executor.monitor_positions()
    assert executor.daily_pnl < -0.05
    assert executor.execute("ETH/IDR", "BUY", 0.9, 0.1) is None
