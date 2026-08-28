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


def test_worker_uses_shared_cycle_runner_and_orchestrator():
    source = (FRONTED / "worker_entry_api.py").read_text(encoding="utf-8")
    cycle = (FRONTED / "paper_cycle.py").read_text(encoding="utf-8")
    adapter = (FRONTED / "cloudflare_orchestrator.py").read_text(encoding="utf-8")
    assert "from paper_cycle import run_paper_cycle" in source
    assert "await run_paper_cycle(" in source
    assert "durable_object_alarm_1m" in source
    assert "CloudflareOrchestrator" in cycle
    assert "await orchestrator.analyze" in cycle
    assert '"use_unified_data": False' in cycle
    assert "class CloudflareOrchestrator" in adapter
    assert "async def _run_base_agents" in adapter
    assert "self.sentiment_agent.analyze" in adapter
    assert "self.technical_agent.analyze" in adapter
    assert "self.decision_agent.analyze" in adapter
    assert "self.forecast_agent.analyze" in adapter
    assert "self.reflector_agent.analyze" in adapter


def test_browser_does_not_schedule_or_intercept_paper_cycles():
    source = (FRONTED / "src" / "index.js").read_text(encoding="utf-8")
    assert "window.setInterval" not in source
    assert "document.addEventListener('click'" not in source
    assert "Paper watchdog" not in source


def test_cloudflare_cron_is_disabled_for_paper_scheduler():
    source = (FRONTED / "wrangler.jsonc").read_text(encoding="utf-8")
    assert '"crons": []' in source
    assert '"PaperTradingState"' in source
    assert '"storage": "sqlite"' in source


def test_cloudflare_build_vendors_existing_agent_modules():
    source = (FRONTED / "package.json").read_text(encoding="utf-8")
    assert '"build": "react-scripts build && rm -rf agents core exchange_integration && cp -r ../agents ../core ../exchange_integration ."' in source
