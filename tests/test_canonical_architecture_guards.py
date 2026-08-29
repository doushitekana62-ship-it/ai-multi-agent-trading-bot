"""Regression guards for the canonical trading architecture.

These tests intentionally inspect source structure so legacy decision paths cannot
silently return to production while low-level strategy tests still pass.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_live_paper_cycle_uses_mandatory_risk_and_execution_gate():
    source = read("core/live_paper_cycle.py")
    assert "Orchestrator" in source
    assert "RiskEngine" in source
    assert "ExecutionGate" in source
    assert "Executor" in source
    assert "AdaptiveScalpingEngine" not in source


def test_market_data_adapter_uses_indodax_for_paper_and_preserves_candle_time():
    source = read("core/market_data_adapter.py")
    assert 'self.exchange_type in {"paper", "indodax"}' in source
    assert 'source="indodax"' in source
    assert 'datetime.fromtimestamp(ts, tz=timezone.utc)' in source


def test_orchestrator_has_explicit_data_quality_block():
    source = read("core/orchestrator.py")
    assert "SHORT_HORIZON_MOVEMENT_UNAVAILABLE" in source
    assert "OHLCV_CONTINUITY_FAILURE" in source
    assert "STALE_MARKET_DATA" in source
    assert "cycle_status" in source


def test_architecture_forbids_hold_as_data_failure():
    source = read("ARCHITECTURE.md")
    assert "Data failure is never represented as normal HOLD." in source
    assert "Missing/degraded evidence is excluded from directional scoring" in source
    assert "HOLD_EXISTING_POSITION" in source
    assert "AI_DEGRADED" in source


def test_signal_contract_has_explicit_failure_states():
    source = read("core/signal_contract.py")
    assert "DATA_UNAVAILABLE" in source
    assert "DATA_STALE" in source
    assert "AI_DEGRADED" in source
    assert "RISK_REJECTED" in source
    assert "EXECUTED" in source
