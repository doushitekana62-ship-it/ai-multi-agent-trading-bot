import json
from pathlib import Path

from agents.agent_trading_librarian import TradingLibrarianAgent
from core.adaptive_scalping import AdaptiveScalpingEngine
from core.executor import Executor


def test_50_cycle_scalping_has_real_entries_and_exits(tmp_path, monkeypatch):
    """Run a deterministic 50-cycle spot-scalping lifecycle.

    The test deliberately includes weak/neutral cycles, strong bullish entry
    cycles and bearish exit cycles. It verifies that the strategy is not
    HOLD-only while preserving spot constraints: no duplicate BUY and no
    SELL without an open position.
    """
    monkeypatch.chdir(tmp_path)

    executor = Executor({
        "exchange_mode": "paper",
        "paper": {
            "initial_balance": 1_000_000,
            "fee_rate": 0.0015,
            "slippage_rate": 0.0002,
        },
        "daily_loss_limit": 0.05,
        "max_open_positions": 1,
    })
    scalper = AdaptiveScalpingEngine({
        "base_threshold": 0.25,
        "momentum_threshold": 0.18,
        "min_confidence": 0.48,
    })
    librarian = TradingLibrarianAgent()
    advice = librarian.advise("scalping momentum risk execution", limit=3)
    assert advice["advisory_only"] is True
    assert advice["knowledge"]

    price = 100_000_000.0
    cycles = []

    for cycle in range(1, 51):
        # Ten repeated market-regime blocks:
        # 1 HOLD -> 2 BUY -> 3 HOLD -> 4 SELL -> 5 HOLD.
        phase = (cycle - 1) % 5
        if phase == 1:
            price *= 1.0005
            signal = scalper.evaluate(
                technical=0.70, sentiment=0.30, forecast=0.50,
                mimic=0.75, momentum=0.55, volatility=0.02,
            )
        elif phase == 3:
            price *= 1.004
            signal = scalper.evaluate(
                technical=-0.65, sentiment=-0.25, forecast=-0.45,
                mimic=-0.70, momentum=-0.55, volatility=0.02,
            )
        else:
            signal = scalper.evaluate(
                technical=0.02, sentiment=0.00, forecast=0.01,
                mimic=0.02, momentum=0.02, volatility=0.02,
            )

        executor.paper_trading.set_test_price("BTC/IDR", price)
        action = signal.action
        order = None

        if action == "BUY" and "BTC/IDR" not in executor.active_positions:
            order = executor.execute(
                "BTC/IDR", "BUY", signal.confidence,
                0.10,
                stop_loss=price * 0.995,
                take_profit=price * 1.008,
            )
        elif action == "SELL" and "BTC/IDR" in executor.active_positions:
            order = executor.execute(
                "BTC/IDR", "SELL", signal.confidence,
                1.0,
            )

        cycles.append({
            "cycle": cycle,
            "price": price,
            "signal": action,
            "confidence": round(signal.confidence, 6),
            "executed": order is not None,
        })

    summary = {
        "cycles": 50,
        "signal_buys": sum(c["signal"] == "BUY" for c in cycles),
        "signal_sells": sum(c["signal"] == "SELL" for c in cycles),
        "signal_holds": sum(c["signal"] == "HOLD" for c in cycles),
        "executed_orders": len(executor.order_history),
        "closed_trades": len(executor.paper_trading.trade_history),
        "final_balance": executor.paper_trading.balance,
        "total_pnl": executor.paper_trading.total_pnl,
        "win_rate": executor.paper_trading.get_performance()["win_rate"],
    }

    result_dir = Path("test_results")
    result_dir.mkdir(parents=True, exist_ok=True)
    (result_dir / "scalping_50_cycle_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    assert summary["signal_buys"] >= 10
    assert summary["signal_sells"] >= 10
    assert summary["signal_holds"] >= 10
    assert summary["executed_orders"] >= 20
    assert summary["closed_trades"] >= 10
    assert not executor.active_positions
    assert summary["total_pnl"] > 0
