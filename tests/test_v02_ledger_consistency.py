from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTED = ROOT / "fronted"


def test_paper_scheduler_keeps_fast_decision_and_live_observation_surface():
    state_source = (FRONTED / "paper_state.py").read_text(encoding="utf-8")
    pulse_source = (FRONTED / "src" / "components" / "MarketPulseLegend.jsx").read_text(encoding="utf-8")
    assert "CYCLE_INTERVAL_MS = 5_000" in state_source
    assert "DECISION_INTERVAL_MS = 15_000" in state_source
    assert "POLL_MS = 5000" in pulse_source


def test_market_observation_is_minute_idempotent():
    source = (FRONTED / "paper_cycle.py").read_text(encoding="utf-8")
    assert "/rest/v1/rpc/upsert_market_observation" in source
    assert "minute_bucket" in source
    migration = (ROOT / "supabase/migrations/20260901100000_execution_ledger_reconciliation.sql").read_text(encoding="utf-8")
    assert "uq_market_observations_symbol_minute" in migration


def test_sell_requires_an_open_position_before_execution():
    source = (FRONTED / "paper_state.py").read_text(encoding="utf-8")
    assert 'elif action=="SELL" and price>0 and idx is not None' in source
    assert "active_positions" in source
    assert "positions.pop(idx)" in source


def test_execution_is_reconciled_into_decision_payload():
    source = (FRONTED / "paper_cycle.py").read_text(encoding="utf-8")
    assert '"execution_status"' in source
    assert '"execution_result"' in source
    assert '"trade_id":trade_id' in source


def test_decision_trade_link_is_schema_supported():
    migration = ROOT / "supabase/migrations/20260901100000_execution_ledger_reconciliation.sql"
    source = migration.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS trade_id bigint" in source
    assert "exit_decision_id bigint" in source
    assert "uq_market_observations_symbol_minute" in source
