from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAPER_STATE = (ROOT / "fronted" / "paper_state.py").read_text(encoding="utf-8")
DASHBOARD = (ROOT / "fronted" / "src" / "pages" / "Dashboard.jsx").read_text(encoding="utf-8")


def test_paper_account_uses_persistent_cash_and_equity_state():
    assert 'state["balance"] = float(state.get("balance", 0)) - allocation - fee' in PAPER_STATE
    assert 'state["balance"] = float(state.get("balance", 0)) + proceeds - fee' in PAPER_STATE
    assert 'state["portfolio_value"] = float(state.get("balance", 0)) + sum(' in PAPER_STATE
    assert 'state["positions"] = positions' in PAPER_STATE


def test_paper_account_dashboard_does_not_use_hardcoded_initial_balance_for_live_balance():
    assert 'const INITIAL_BALANCE=10000000' not in DASHBOARD
    assert 'const cashBalance=Number(status?.balance||0)' in DASHBOARD
    assert 'const equity=Number(status?.portfolio_value||cashBalance)' in DASHBOARD
    assert 'const unrealizedPnl=positions.reduce(' in DASHBOARD
    assert 'const reservedCapital=positions.reduce(' in DASHBOARD
    assert 'const initialBalance=Number(status?.initial_balance||0)' in DASHBOARD
