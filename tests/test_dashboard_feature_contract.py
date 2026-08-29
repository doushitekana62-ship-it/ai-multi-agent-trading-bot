from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_market_pulse_has_single_dashboard_location():
    app = read("fronted/src/App.jsx")
    dashboard = read("fronted/src/pages/Dashboard.jsx")
    legend = read("fronted/src/components/MarketPulseLegend.jsx")
    assert "MarketPulseStatus" not in app
    assert "<MarketPulseLegend />" in dashboard
    assert "pulseStatus" in dashboard
    assert "recent market price chart" in legend
    assert "GREEN / UP" in legend and "RED / DOWN" in legend and "GRAY / FLAT" in legend
    assert ":has(> [aria-label=\"recent market price chart\"])" in legend


def test_dashboard_analytics_features_are_present_without_duplicate_history():
    source = read("fronted/src/components/DashboardAnalytics.jsx")
    for label in ("Conflict Analyzer", "INDODAX Scalping Radar", "Volume Share", "Market Scanner"):
        assert label in source
    assert "Paper History Library" not in source
    assert "Paper History · Supabase" not in source
    assert "backgroundColor" in source
    assert "tooltip" in source


def test_history_api_is_bounded_and_paginated():
    source = read("fronted/worker_entry_api.py")
    assert "page_size = max(1, min(10" in source
    assert "page_size + 1" in source
    assert "has_next = len(rows) > page_size" in source


def test_market_scanner_is_not_hard_capped_at_five():
    source = read("fronted/cf_worker.py")
    assert '"items": items[:20]' in source
    assert '"scalping_supported"' in source


def test_ai_engine_and_worker_share_expanded_scalping_pairs():
    worker = read("fronted/cf_worker.py")
    engine = read("fastapi_cloud_app.py")
    for pair in ("beat_idr", "hype_idr"):
        assert pair in worker
    for symbol in ("BEAT/IDR", "HYPE/IDR"):
        assert symbol in engine


def test_fastapi_runtime_declares_requests_dependency():
    source = read("pyproject.toml")
    assert '"requests>=2.32,<3"' in source
