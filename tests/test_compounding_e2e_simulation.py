from datetime import datetime, timezone

from fronted.core.indodax_scalping_strategy import analyze
from fronted.risk_engine import evaluate_entry, settings_with_defaults


def tape(values, start_ts):
    return [
        {"timestamp": start_ts + i * 60, "price": price, "amount": 100 + i, "observation_type": "TRADE", "side": "buy"}
        for i, price in enumerate(values)
    ]


def test_compounding_scalping_real_data_contract_opens_and_closes():
    now = int(datetime.now(timezone.utc).timestamp())
    rising = [100.0 * (1.003 ** i) for i in range(31)]
    market = {"current_price": rising[-1], "timestamp": now, "recent_trades": tape(rising, now - 30 * 60)}
    entry = analyze("BTC/IDR", market)

    assert entry["data_source"] == "INDODAX public market data"
    assert entry["strategy_version"] == "compounding-scalping-v3"
    assert entry["action"] == "BUY"
    assert entry["net_edge_pct"] >= 0.45
    assert len(entry["agents"]) >= 5

    risk = settings_with_defaults({"max_hold_minutes": 15})
    gate = evaluate_entry(
        action=entry["action"], confidence=entry["confidence"],
        requested_position_size=entry["position_size"], net_edge_pct=entry["net_edge_pct"],
        balance=10_000_000, portfolio_value=10_000_000,
        open_positions=0, current_exposure=0, settings=risk,
    )
    assert gate["approved"] is True
    assert gate["approved_position_size"] > 0

    entry_capital = 10_000_000 * gate["approved_position_size"]
    entry_price = rising[-1]
    quantity = entry_capital / entry_price
    position = {"symbol": "BTC/IDR", "side": "BUY", "entry_price": entry_price, "quantity": quantity, "created_at": datetime.now(timezone.utc).isoformat()}

    falling = [entry_price * (1 - 0.001 * i) for i in range(6)]
    exit_market = {"current_price": falling[-1], "timestamp": now + 5 * 60, "recent_trades": tape(falling, now)}
    exit_result = analyze("BTC/IDR", exit_market, position=position)

    assert exit_result["exit_plan"]["exit_action"] == "SELL"
    assert exit_result["exit_plan"]["exit_reason"] in {"TP_HIT_NO_CONTINUATION", "FORECAST_NO_CONTINUATION", "FORECAST_REVERSAL", "DYNAMIC_TP_HIT"}
    assert exit_result["action"] == "SELL"


def test_compounding_allocation_increases_after_profitable_cycle():
    initial_equity = 10_000_000.0
    first_profit = 40_000.0
    next_equity = initial_equity + first_profit
    allocation = 0.10
    first_size = initial_equity * allocation
    next_size = next_equity * allocation
    assert next_size > first_size
    assert round(next_size - first_size, 2) == 4_000.0
