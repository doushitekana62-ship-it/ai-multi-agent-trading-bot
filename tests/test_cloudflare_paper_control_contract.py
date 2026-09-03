from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];FRONTED=ROOT/"fronted"
def test_paper_state_has_manual_alarm_scheduler():
    source=(FRONTED/"paper_state.py").read_text(encoding="utf-8");assert "async def enable_paper" in source;assert "async def stop" in source;assert "async def alarm" in source;assert "getAlarm" in source;assert "setAlarm" in source;assert "deleteAlarm" in source;assert "scheduler_source" in source;assert "durable_object_alarm" in source;assert "CYCLE_INTERVAL_MS=5_000" in source;assert "DECISION_INTERVAL_MS=15_000" in source;assert "risk_settings" in source;assert "async def preview_risk_exit" in source;assert "update_protection(" in source
def test_worker_uses_shared_cycle_runner_and_risk_api():
    source=(FRONTED/"worker_entry_api.py").read_text(encoding="utf-8");assert "from paper_cycle import run_paper_cycle" in source;assert "await run_paper_cycle(" in source;assert "await stub.enable_paper(pair)" in source;assert "await stub.stop()" in source;assert "/api/dashboard/paper/risk" in source;assert "risk_settings" in source
def test_browser_entrypoint_does_not_schedule_paper_cycles():
    source=(FRONTED/"src"/"index.jsx").read_text(encoding="utf-8");assert "window.setInterval" not in source;assert "Paper watchdog" not in source
def test_human_history_is_single_supabase_ledger_component():
    app=(FRONTED/"src"/"App.jsx").read_text(encoding="utf-8");history=(FRONTED/"src"/"components"/"PaperHistoryLibrary.jsx").read_text(encoding="utf-8");assert app.count("<PaperHistoryLibrary />")==1;assert "Paper History — Human View" in history;assert "JSON.stringify" not in history
def test_cloudflare_cron_is_disabled_for_paper_scheduler():
    source=(FRONTED/"wrangler.jsonc").read_text(encoding="utf-8");assert '"crons": []' in source;assert '"PaperTradingState"' in source;assert '"storage": "sqlite"' in source;assert '"services"' not in source
def test_dashboard_uses_external_fastapi_ai_engine():
    adapter=(FRONTED/"cloudflare_orchestrator.py").read_text(encoding="utf-8");cycle=(FRONTED/"paper_cycle.py").read_text(encoding="utf-8");assert "AI_ENGINE_URL" in adapter;assert "AI_ENGINE_SHARED_SECRET" in adapter;assert "/engine/analyze" in adapter;assert "env.AI_ENGINE.analyze" not in adapter;assert "Cloudflare Container" not in adapter;assert "CloudflareOrchestrator" in cycle
def test_ai_engine_failure_is_explicitly_degraded_not_silent_hold():
    adapter=(FRONTED/"cloudflare_orchestrator.py").read_text(encoding="utf-8");assert "AI_DEGRADED" in adapter;assert 'cycle_status="AI_DEGRADED" if engine_warning else "ANALYZED"' in adapter;assert "engine_warning" in adapter
def test_fastapi_cloud_entrypoint_is_explicit_and_safe():
    pyproject=(ROOT/"pyproject.toml").read_text(encoding="utf-8");app=(ROOT/"fastapi_cloud_app.py").read_text(encoding="utf-8");assert 'entrypoint = "fastapi_cloud_app:app"' in pyproject;assert '@app.get("/health")' in app;assert '@app.post("/engine/analyze"' in app;assert "AI_ENGINE_SHARED_SECRET" in app;assert "_force_action" in app;assert "Orchestrator(" in app
def test_fastapi_cloud_does_not_start_background_trading():
    app=(ROOT/"fastapi_cloud_app.py").read_text(encoding="utf-8");assert "asyncio.create_task" not in app;assert "while True" not in app;assert "create_order" not in app
def test_risk_engine_supports_adaptive_and_fixed_modes():
    source=(FRONTED/"risk_engine.py").read_text(encoding="utf-8");assert "FIXED_PERCENT" in source;assert "ATR" in source;assert "RISK_REWARD" in source;assert "trailing_enabled" in source;assert "break_even_enabled" in source;assert "slippage_bps" in source
