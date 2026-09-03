import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTED = ROOT / "fronted"


def test_fastapi_cloud_entrypoint_is_explicit():
    config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'entrypoint = "fastapi_cloud_app:app"' in config
    assert "fastapi[standard]" in config
    assert "numpy" in config
    assert "pandas" in config
    assert "scipy" in config
    assert "scikit-learn" in config


def test_cloudflare_worker_has_authoritative_paper_state_export():
    config = json.loads((FRONTED / "wrangler.jsonc").read_text(encoding="utf-8"))
    assert config["name"] == "ai-multi-agent-trading-bot"
    assert config["main"] == "./worker_entry_api.py"
    assert config["compatibility_flags"] == ["python_workers"]
    assert config["durable_objects"]["bindings"] == [
        {"name": "PAPER_STATE", "class_name": "PaperTradingState"}
    ]
    assert config["exports"]["PaperTradingState"] == {
        "type": "durable-object",
        "state": "created",
        "storage": "sqlite",
    }


def test_cloudflare_worker_does_not_depend_on_removed_ai_engine_service_binding():
    config = json.loads((FRONTED / "wrangler.jsonc").read_text(encoding="utf-8"))
    bindings = config.get("services", [])
    assert not any(binding.get("binding") == "AI_ENGINE" for binding in bindings)
    assert "AI_ENGINE" not in json.dumps(config)


def test_cloudflare_and_fastapi_contract_use_same_secret_name():
    worker_adapter = (FRONTED / "cloudflare_orchestrator.py").read_text(encoding="utf-8")
    fastapi_app = (ROOT / "fastapi_cloud_app.py").read_text(encoding="utf-8")
    assert "AI_ENGINE_URL" in worker_adapter
    assert "AI_ENGINE_SHARED_SECRET" in worker_adapter
    assert "/engine/analyze" in worker_adapter
    assert "AI_ENGINE_SHARED_SECRET" in fastapi_app
    assert "X-AI-Engine-Key" in worker_adapter
    assert "x_ai_engine_key" in fastapi_app
    assert "Header(default=None)" in fastapi_app


def test_paper_scheduler_is_durable_object_alarm_driven():
    worker = (FRONTED / "worker_entry_api.py").read_text(encoding="utf-8")
    state = (FRONTED / "paper_state.py").read_text(encoding="utf-8")
    compact = state.replace(" ", "")
    assert "await stub.enable_paper(pair)" in worker
    assert "await stub.stop()" in worker
    assert "async def alarm" in state
    assert "getAlarm" in state
    assert "setAlarm" in state
    assert "deleteAlarm" in state
    assert "CYCLE_INTERVAL_MS=5_000" in compact
    assert "DECISION_INTERVAL_MS=15_000" in compact
    assert "scheduler_source" in state


def test_paper_position_control_is_persistent_and_bounded():
    worker = (FRONTED / "worker_entry_api.py").read_text(encoding="utf-8")
    state = (FRONTED / "paper_state.py").read_text(encoding="utf-8")
    assert "/api/dashboard/paper/settings" in worker
    assert "await stub.set_position_limit(value)" in worker
    assert "async def set_position_limit" in state
    assert "MAX_POSITIONS = 3" in state
    assert "_limit(" in state


def test_paper_history_route_is_on_authoritative_worker():
    worker = (FRONTED / "worker_entry_api.py").read_text(encoding="utf-8")
    cycle = (FRONTED / "paper_cycle.py").read_text(encoding="utf-8")
    migrations = list((ROOT / "supabase" / "migrations").glob("*_create_paper_history.sql"))
    assert len(migrations) == 1
    migration = migrations[0].read_text(encoding="utf-8")
    assert 'path == "/api/dashboard/history"' in worker
    assert "/rest/v1/paper_history?" in worker
    assert '"paper_history"' in cycle
    assert "create table if not exists public.paper_history" in migration


def test_legacy_worker_entrypoint_is_only_a_compatibility_shim():
    source = (FRONTED / "worker_entry.py").read_text(encoding="utf-8")
    assert "from worker_entry_api import Default, PaperTradingState" in source
    assert "class Default" not in source


def test_cloudflare_asgi_compatibility_shim_is_runtime_safe():
    shim = (FRONTED / "asgi.py").read_text(encoding="utf-8")
    assert "from workers import asgi as _asgi" not in shim
    assert "workers.asgi" not in shim
    assert "async def fetch(app, request, env)" in shim
    assert "/api/market/overview" in shim
    assert "/api/market/data" in shim
    assert "/api/market/insights" in shim


def test_cloudflare_strategy_module_is_packaged_under_worker_root():
    adapter = (FRONTED / "cloudflare_orchestrator.py").read_text(encoding="utf-8")
    packaged = FRONTED / "core" / "indodax_scalping_strategy.py"
    dynamic_exit = FRONTED / "core" / "dynamic_exit.py"
    source = packaged.read_text(encoding="utf-8")
    assert "from core.indodax_scalping_strategy import" in adapter
    assert "from core.dynamic_exit import forecast_exit" in adapter
    assert packaged.exists()
    assert dynamic_exit.exists()
    assert 'SOURCE="INDODAX public market data"' in source
    assert 'STRATEGY_VERSION="compounding-scalping-v3"' in source
