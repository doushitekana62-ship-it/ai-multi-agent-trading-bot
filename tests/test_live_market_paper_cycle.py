import asyncio
import json
import time
from pathlib import Path

import pytest

from core.live_paper_cycle import LivePaperCycle


@pytest.mark.integration
@pytest.mark.timeout(360)
def test_live_indodax_runtime_paper_session(tmp_path, monkeypatch):
    """Run a longer real-market paper session instead of a tiny 5-cycle sample.

    The session consumes public Indodax ticker/OHLCV data repeatedly, keeps one
    paper executor alive across the whole runtime, monitors open positions for
    SL/TP, and records every decision/order. It deliberately does not require a
    BUY or SELL on every run because forcing a trade would invalidate the test.
    The objective is to observe whether the strategy naturally produces entries
    and exits when the live market presents a valid setup.
    """
    monkeypatch.chdir(tmp_path)
    cycle_runner = LivePaperCycle({
        "paper": {
            "initial_balance": 10_000_000,
            "fee_rate": 0.0015,
            "slippage_rate": 0.0002,
            "price_ttl_seconds": 1.0,
        },
        "daily_loss_limit": 0.05,
        "max_open_positions": 1,
    })

    results = []
    started = time.monotonic()
    cycles = 60
    for index in range(cycles):
        result = asyncio.run(cycle_runner.cycle("BTC/IDR"))
        result["cycle"] = index + 1
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        results.append(result)
        # Avoid hammering the public endpoint while still observing multiple
        # market snapshots during one continuous paper session.
        time.sleep(1.0)

    summary = cycle_runner.runtime_summary()
    actions = {action: sum(item["action"] == action for item in results) for action in {"BUY", "SELL", "HOLD"}}
    executed = sum(bool(item.get("executed")) for item in results)
    position_events = sum(bool(item.get("position_event")) for item in results)

    report = {
        "mode": "real_market_paper_runtime",
        "exchange": "indodax_public_read_only",
        "symbol": "BTC/IDR",
        "cycles": cycles,
        "duration_seconds": round(time.monotonic() - started, 3),
        "actions": actions,
        "executed_orders": executed,
        "position_events": position_events,
        "runtime_summary": summary,
        "cycles_detail": results,
    }

    assert len(results) == cycles
    assert all(item["market_data_valid"] for item in results)
    assert all(item["price"] > 0 for item in results)
    assert all(item["action"] in {"BUY", "SELL", "HOLD", "STRONG_BUY", "STRONG_SELL"} for item in results)
    assert all(item["scalping"] in {"BUY", "SELL", "HOLD"} for item in results)
    assert all(item["library_topics"] for item in results)
    assert summary["executor"]["exchange_mode"] == "paper"

    Path("test_results").mkdir(exist_ok=True)
    Path("test_results/live_market_runtime_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    print("\nREAL-MARKET RUNTIME SUMMARY")
    print(json.dumps({
        "cycles": cycles,
        "duration_seconds": report["duration_seconds"],
        "actions": actions,
        "executed_orders": executed,
        "position_events": position_events,
        "paper_performance": summary["paper_performance"],
    }, indent=2))
