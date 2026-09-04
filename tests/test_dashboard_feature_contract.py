from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_dashboard_has_single_market_pulse_location():
    app = read("fronted/src/App.jsx")
    dashboard = read("fronted/src/pages/Dashboard.jsx")
    assert "MarketPulseStatus" not in app
    assert "MarketPulseLegend" in dashboard
    assert "30 segmen 1-menit" in dashboard
    assert "INDODAX public data" in dashboard
    assert "pulse_segments" not in dashboard or "MarketPulseLegend" in dashboard


def test_dashboard_uses_fastapi_routes_not_worker_routes():
    source = read("fronted/src/pages/Dashboard.jsx")
    assert "/api/dashboard/status" in source
    assert "/api/dashboard/positions" in source
    assert "/api/dashboard/performance" in source
    assert "/api/dashboard/analyze" in source
    assert "/api/market/overview" in source
    assert "/api/market/insights" in source
    assert "Worker." not in source


def test_market_pulse_is_observation_driven_and_30_minutes():
    source = read("fronted/src/components/MarketPulseLegend.jsx")
    assert "POLL_MS=5000" in source
    assert "WINDOW_MINUTES = 30" in source
    assert "GREEN" in source and "RED" in source and "GRAY" in source
    assert "price changed" in source
    assert "pulse_segments" in source


def test_frontend_auth_uses_configurable_fastapi_base_url():
    source = read("fronted/src/context/AuthContext.jsx")
    assert "VITE_API_URL" in source
    assert "baseURL" in source


def test_dashboard_paper_controls_are_api_backed():
    source = read("fronted/src/pages/Dashboard.jsx")
    assert "/api/dashboard/paper/start" in source
    assert "/api/dashboard/paper/stop" in source
    assert "/api/dashboard/paper/reset" in source
    assert "Start Paper Bot" in source
    assert "Reset Paper" in source


def test_fastapi_runtime_declares_market_dependencies():
    source = read("pyproject.toml")
    assert '"requests>=2.32,<3"' in source
    assert '"ccxt>=4.4,<5"' in source
    assert '"ta>=0.11,<1"' in source
