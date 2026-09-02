from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];FRONTED=ROOT/"fronted"

def test_paper_state_has_durable_object_alarm_scheduler():
    source=(FRONTED/"paper_state.py").read_text(encoding="utf-8")
    compact=source.replace(" ", "")
    assert "async def enable_paper" in source
    assert "async def stop" in source
    assert "async def alarm" in source
    assert "getAlarm" in source
    assert "setAlarm" in source
    assert "deleteAlarm" in source
    assert "CYCLE_INTERVAL_MS=5_000" in compact
    assert "DECISION_INTERVAL_MS=15_000" in compact
    assert "durable_object_alarm" in source

def test_worker_uses_canonical_entrypoint_shared_cycle_runner_and_external_orchestrator():
    source=(FRONTED/"worker_entry_api.py").read_text(encoding="utf-8");wrangler=(FRONTED/"wrangler.jsonc").read_text(encoding="utf-8");cycle=(FRONTED/"paper_cycle.py").read_text(encoding="utf-8");adapter=(FRONTED/"cloudflare_orchestrator.py").read_text(encoding="utf-8")
    assert "from paper_cycle import run_paper_cycle" in source
    assert "await run_paper_cycle(" in source
    assert '"main": "./worker_entry_api.py"' in wrangler
    assert "CloudflareOrchestrator" in cycle
    assert "class CloudflareOrchestrator" in adapter
    assert "AI_ENGINE_URL" in adapter
    assert "AI_ENGINE_SHARED_SECRET" in adapter
    assert "/engine/analyze" in adapter

def test_browser_does_not_schedule_or_intercept_paper_cycles():
    source=(FRONTED/"src"/"index.jsx").read_text(encoding="utf-8")
    assert "window.setInterval" not in source
    assert "Paper watchdog" not in source

def test_cloudflare_cron_is_disabled_for_paper_scheduler():
    source=(FRONTED/"wrangler.jsonc").read_text(encoding="utf-8")
    assert '"crons": []' in source
    assert '"PaperTradingState"' in source
    assert '"storage": "sqlite"' in source
    assert '"main": "./worker_entry_api.py"' in source

def test_cloudflare_build_uses_vite():
    source=(FRONTED/"package.json").read_text(encoding="utf-8")
    assert '"build": "vite build"' in source
    assert '"build:cloudflare": "vite build"' in source
    assert '"vite"' in source
