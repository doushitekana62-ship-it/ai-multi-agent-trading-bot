import asyncio
import json
from pathlib import Path

import pytest

from core.live_paper_cycle import LivePaperCycle


@pytest.mark.integration
@pytest.mark.timeout(120)
def test_live_indodax_paper_cycles_use_full_pipeline(tmp_path, monkeypatch):
    """Exercise the real public Indodax market through the full paper pipeline.

    No credentials or private endpoints are used. The test requires public
    market data to be reachable and records every decision for diagnosis.
    It does not demand a profitable trade from a short live sample; it verifies
    that the pipeline can repeatedly consume real data and produce a valid
    decision without falling back to fabricated prices.
    """
    monkeypatch.chdir(tmp_path)
    cycle_runner = LivePaperCycle({
        "paper": {"initial_balance": 10_000_000, "fee_rate": 0.0015, "slippage_rate": 0.0002},
        "daily_loss_limit": 0.05,
        "max_open_positions": 1,
    })

    results = []
    for _ in range(5):
        result = asyncio.run(cycle_runner.cycle("BTC/IDR"))
        results.append(result)

    assert len(results) == 5
    assert all(item["market_data_valid"] for item in results)
    assert all(item["price"] > 0 for item in results)
    assert all(item["action"] in {"BUY", "SELL", "HOLD", "STRONG_BUY", "STRONG_SELL"} for item in results)
    assert all(item["scalping"] in {"BUY", "SELL", "HOLD"} for item in results)
    assert all(item["library_topics"] for item in results)

    Path("test_results").mkdir(exist_ok=True)
    Path("test_results/live_market_paper_cycles.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
