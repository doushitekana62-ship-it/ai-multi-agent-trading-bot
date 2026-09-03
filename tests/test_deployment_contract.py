from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];FRONTED=ROOT/"fronted"
def test_paper_state_has_manual_alarm_scheduler_contract():
    state=(FRONTED/"paper_state.py").read_text(encoding="utf-8");compact=state.replace(" ","")
    assert "getAlarm" in state;assert "setAlarm" in state;assert "deleteAlarm" in state;assert "CYCLE_INTERVAL_MS=5_000" in compact;assert "DECISION_INTERVAL_MS=15_000" in compact;assert "scheduler_source" in state

def test_paper_position_control_is_persistent_and_bounded():
    worker=(FRONTED/"worker_entry_api.py").read_text(encoding="utf-8");state=(FRONTED/"paper_state.py").read_text(encoding="utf-8")
    assert "/api/dashboard/paper/settings" in worker;assert "await stub.set_position_limit(value)" in worker;assert "async def set_position_limit" in state;assert "MAX_POSITIONS=3" in state;assert "_limit(" in state

def test_paper_history_route_is_on_authoritative_worker():
    worker=(FRONTED/"worker_entry_api.py").read_text(encoding="utf-8");cycle=(FRONTED/"paper_cycle.py").read_text(encoding="utf-8");migrations=list((ROOT/"supabase"/"migrations").glob("*_create_paper_history.sql"));assert len(migrations)==1;assert 'path == "/api/dashboard/history"' in worker;assert "/rest/v1/paper_history?" in worker;assert "paper_history" in cycle
