from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTED = ROOT / "fronted"


def test_paper_state_has_manual_alarm_scheduler():
    source = (FRONTED / "paper_state.py").read_text(encoding="utf-8")
    assert "async def enable_paper" in source
    assert "async def stop" in source
    assert "async def alarm" in source
    assert "getAlarm" in source
    assert "setAlarm" in source
    assert "deleteAlarm" in source
    assert "durable_object_alarm" in source


def test_worker_uses_shared_cycle_runner_and_local_ai_fallback():
    worker = (FRONTED / "worker_entry_api.py").read_text(encoding="utf-8")
    adapter = (FRONTED / "cloudflare_orchestrator.py").read_text(encoding="utf-8")
    cycle = (FRONTED / "paper_cycle.py").read_text(encoding="utf-8")
    assert "from paper_cycle import run_paper_cycle" in worker
    assert "await run_paper_cycle(" in worker
    assert "durable_object_alarm_1m" in worker
    assert "AI_ENGINE_URL" in adapter
    assert "AI_ENGINE_SHARED_SECRET" in adapter
    assert "/engine/analyze" in adapter
    assert "_local_fallback" in adapter
    assert "CloudflareOrchestrator" in cycle


def test_browser_has_no_trading_watchdog():
    source = (FRONTED / "src" / "index.js").read_text(encoding="utf-8")
    tools = (FRONTED / "src" / "components" / "DashboardTools.jsx").read_text(encoding="utf-8")
    assert "window.setInterval" not in source
    assert "document.addEventListener('click'" not in source
    assert "Paper watchdog" not in source
    assert "MutationObserver" not in tools
    assert "addEventListener('click'" not in tools


def test_indodax_client_uses_public_documented_endpoints():
    source = (FRONTED / "indodax_client.py").read_text(encoding="utf-8")
    assert 'BASE_URL = "https://indodax.com/api"' in source
    assert "/{pair}/ticker" in source
    assert "/{pair}/trades" in source
    assert '"/tickers"' in source


def test_cloudflare_cron_is_disabled_for_paper_scheduler():
    source = (FRONTED / "wrangler.jsonc").read_text(encoding="utf-8")
    assert '"crons": []' in source
    assert '"PaperTradingState"' in source
    assert '"storage": "sqlite"' in source
    assert '"services"' not in source


def test_fastapi_cloud_entrypoint_is_explicit_and_safe():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    app = (ROOT / "fastapi_cloud_app.py").read_text(encoding="utf-8")
    assert 'entrypoint = "fastapi_cloud_app:app"' in pyproject
    assert '@app.get("/health")' in app
    assert '@app.post("/engine/analyze"' in app
    assert "AI_ENGINE_SHARED_SECRET" in app
    assert "_force_action" in app
    assert "Orchestrator(" in app


def test_fastapi_cloud_does_not_start_background_trading():
    app = (ROOT / "fastapi_cloud_app.py").read_text(encoding="utf-8")
    assert "asyncio.create_task" not in app
    assert "while True" not in app
    assert "create_order" not in app
