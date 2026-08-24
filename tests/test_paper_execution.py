import pytest

from exchange_integration.paper_trading import PaperTrading


@pytest.fixture
def paper(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return PaperTrading({"initial_balance": 1_000_000, "fee_rate": 0.001, "slippage_rate": 0.0})


def test_buy_price_move_sell_profit(paper):
    paper.set_test_price("BTC/IDR", 100_000_000)
    assert paper.execute_order("BTC/IDR", "BUY", 0.005, 100_000_000)
    paper.set_test_price("BTC/IDR", 102_000_000)
    assert paper.execute_order("BTC/IDR", "SELL", 0.005, 102_000_000)
    # Gross gain = 10,000; entry fee = 500; exit fee = 510.
    assert paper.total_pnl == pytest.approx(8_990)
    assert paper.total_trades == 1
    assert paper.winning_trades == 1
    assert not paper.positions


def test_buy_price_move_sell_loss(paper):
    paper.set_test_price("BTC/IDR", 100_000_000)
    assert paper.execute_order("BTC/IDR", "BUY", 0.005, 100_000_000)
    paper.set_test_price("BTC/IDR", 98_000_000)
    assert paper.execute_order("BTC/IDR", "SELL", 0.005, 98_000_000)
    # Gross loss = -10,000; entry fee = 500; exit fee = 490.
    assert paper.total_pnl == pytest.approx(-10_990)
    assert paper.losing_trades == 1


def test_duplicate_buy_rejected(paper):
    assert paper.execute_order("BTC/IDR", "BUY", 0.005, 100_000_000)
    assert not paper.execute_order("BTC/IDR", "BUY", 0.001, 100_000_000)
    assert len(paper.positions) == 1


def test_insufficient_balance_rejected(paper):
    assert not paper.execute_order("BTC/IDR", "BUY", 0.02, 100_000_000)
    assert not paper.positions
    assert paper.balance == 1_000_000


def test_sell_without_position_rejected(paper):
    assert not paper.execute_order("BTC/IDR", "SELL", 0.001, 100_000_000)


def test_partial_sell_preserves_position(paper):
    assert paper.execute_order("BTC/IDR", "BUY", 0.005, 100_000_000)
    assert paper.execute_order("BTC/IDR", "SELL", 0.002, 101_000_000)
    assert paper.positions["BTC/IDR"].quantity == pytest.approx(0.003)
    assert paper.total_trades == 1
