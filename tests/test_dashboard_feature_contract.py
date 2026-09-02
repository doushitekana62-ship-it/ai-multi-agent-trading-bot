from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(path):return (ROOT/path).read_text(encoding='utf-8')

def test_market_pulse_has_single_dashboard_location():
    app=read('fronted/src/App.jsx');dashboard=read('fronted/src/pages/Dashboard.jsx')
    assert 'MarketPulseStatus' not in app
    assert 'function Pulse' in dashboard
    assert '30 segmen 1-menit' in dashboard
    assert 'INDODAX → Supabase' in dashboard
    assert 'pulse_segments' in dashboard
    assert "label==='UP'" not in dashboard

def test_dashboard_analytics_features_are_present_without_duplicate_history():
    source=read('fronted/src/components/DashboardAnalytics.jsx')
    for label in ('Conflict Analyzer','INDODAX Scalping Radar','Volume Share','Market Scanner'):assert label in source
    assert 'Paper History Library' not in source
    assert 'Paper History · Supabase' not in source
    assert 'backgroundColor' in source and 'tooltip' in source

def test_history_api_is_bounded_and_paginated():
    source=read('fronted/worker_entry_api.py');assert 'page_size = max(1, min(10' in source;assert 'page_size + 1' in source;assert 'has_next = len(rows) > page_size' in source

def test_dashboard_history_is_supabase_only_and_paginated():
    source=read('fronted/src/components/DashboardTools.jsx')
    for text in ('Supabase','Forensic ledger','page_size: 10','historyHasNext','No persisted'):assert text in source
    assert 'decisionHistory.filter' not in source

def test_dashboard_v02_control_plane_is_observable():
    source=read('fronted/src/components/DashboardTools.jsx')
    for text in ('Server-authoritative entry limit','Market direction comes from the current 1m pulse','Deterministic control-plane view','risk_rejection_reason','candidate_action','execution_status'):assert text in source

def test_dashboard_refresh_and_paper_reset_controls_exist():
    source=read('fronted/src/pages/Dashboard.jsx')
    assert 'Refresh' in source and 'fetchData' in source
    assert 'api/dashboard/paper/reset' in source
    assert 'Reset Paper' in source

def test_scalping_selector_uses_live_scanner_supported_pairs_only():
    source=read('fronted/src/pages/Dashboard.jsx')
    assert 'scalping_supported' in source
    assert 'available.length?available:PAIRS' in source

def test_market_scanner_is_not_hard_capped_at_five():
    source=read('fronted/cf_worker.py');assert '"items": items[:20]' in source;assert '"scalping_supported"' in source

def test_ai_engine_and_worker_share_expanded_scalping_pairs():
    worker=read('fronted/cf_worker.py');engine=read('fastapi_cloud_app.py')
    for pair in ('beat_idr','hype_idr'):assert pair in worker
    for symbol in ('BEAT/IDR','HYPE/IDR'):assert symbol in engine

def test_fastapi_runtime_declares_requests_dependency():
    source=read('pyproject.toml');assert '"requests>=2.32,<3"' in source
