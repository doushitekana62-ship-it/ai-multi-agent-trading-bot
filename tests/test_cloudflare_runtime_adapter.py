from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTED = ROOT / "fronted"


def test_cloudflare_adapter_does_not_call_legacy_asgi_fetch_helper():
    source = (FRONTED / "asgi.py").read_text(encoding="utf-8")
    assert "from workers import asgi" not in source
    assert "workers.asgi" not in source
    assert "async def fetch(app, request, env)" in source


def test_market_routes_use_lightweight_ticker_adapter():
    source = (FRONTED / "asgi.py").read_text(encoding="utf-8")
    assert "/api/market/overview" in source
    assert "/api/market/data" in source
    assert "/api/market/insights" in source
    assert "async def _light_market_overview" in source
    assert "await _light_market_overview(pair)" in source
    assert "_cf_worker._market_insights" in source
    assert "_cf_worker._market_overview(scope)" not in source


def test_indodax_market_fetch_bypasses_cloudflare_edge_cache():
    source = (FRONTED / "asgi.py").read_text(encoding="utf-8")
    assert '"cache": "no-store"' in source
    assert '"Cache-Control": "no-cache"' in source
    assert "_live=" in source


def test_market_pulse_is_one_minute_rolling_and_marks_observed_changes():
    source = (FRONTED / "paper_cycle.py").read_text(encoding="utf-8")
    assert "PULSE_MINUTES = 30" in source
    assert "bucket = int(ts // 60) * 60" in source
    assert "row[\"changed\"] = True" in source
    assert "GREEN" in source and "RED" in source and "GRAY" in source


def test_browser_market_polling_remains_live():
    for name in ("MarketPulseLegend.jsx", "MarketPulseStatus.jsx"):
        source = (FRONTED / "src" / "components" / name).read_text(encoding="utf-8")
        assert "POLL_MS = 5000" in source
        assert "window.setInterval(load, POLL_MS)" in source
        assert "_ts: Date.now()" in source
