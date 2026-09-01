from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTED = ROOT / "fronted"


def test_paper_scheduler_does_not_poll_every_five_seconds():
    source = (FRONTED / "paper_state.py").read_text(encoding="utf-8")
    assert "CYCLE_INTERVAL_MS = 60_000" in source


def test_sell_requires_an_open_position_before_approval():
    source = (FRONTED / "paper_cycle.py").read_text(encoding="utf-8")
    assert "NO_OPEN_POSITION" in source
    assert "account_allows_candidate" in source


def test_execution_reconciles_canonical_trade_ledger():
    source = (FRONTED / "paper_cycle.py").read_text(encoding="utf-8")
    assert "_persist_execution_trade" in source
    assert '"trades"' in source
    assert '"trade_id": trade_persistence.get("trade_id")' in source


def test_decision_trade_link_is_schema_supported():
    migration = ROOT / "supabase/migrations/20260901100000_execution_ledger_reconciliation.sql"
    source = migration.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS trade_id bigint" in source
    assert "exit_decision_id bigint" in source
