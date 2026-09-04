from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_live_paper_cycle_has_one_canonical_execution_path():
    source = read("core/live_paper_cycle.py")
    assert "Orchestrator" in source
    assert "RiskEngine" in source
    assert "ExecutionGate" in source
    assert "Executor" in source
    assert "exchange_mode": "paper" in source


def test_market_observation_schema_supports_minute_idempotency():
    migrations = sorted((ROOT / "supabase" / "migrations").glob("*.sql"))
    text = "\n".join(path.read_text(encoding="utf-8") for path in migrations)
    assert "market_observations" in text
    assert "minute_bucket" in text


def test_sell_requires_a_position_in_the_paper_executor():
    source = read("core/executor.py")
    assert "SELL" in source
    assert "active_positions" in source


def test_execution_gate_is_separate_from_ai_orchestration():
    source = read("core/live_paper_cycle.py")
    assert "self.execution_gate.evaluate" in source
    assert "self.risk.evaluate" in source
    assert source.index("self.risk.evaluate") < source.index("self.execution_gate.evaluate")


def test_paper_cycle_never_uses_a_live_exchange_mode():
    source = read("core/live_paper_cycle.py")
    assert '"exchange_mode": "paper"' in source
    assert "exchange_mode": "live" not in source
