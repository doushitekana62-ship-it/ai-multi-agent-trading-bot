import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_fastapi_cloud_entrypoint_is_explicit():
    config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'entrypoint = "fastapi_cloud_app:app"' in config
    assert "fastapi[standard]" in config
    assert "numpy" in config
    assert "pandas" in config
    assert "scipy" in config
    assert "scikit-learn" in config


def test_cloudflare_worker_has_authoritative_paper_state_export():
    config = json.loads((ROOT / "fronted" / "wrangler.jsonc").read_text(encoding="utf-8"))

    assert config["name"] == "ai-multi-agent-trading-bot"
    assert config["main"] == "./worker_entry_api.py"
    assert config["compatibility_flags"] == ["python_workers"]

    bindings = config["durable_objects"]["bindings"]
    assert bindings == [{"name": "PAPER_STATE", "class_name": "PaperTradingState"}]

    export = config["exports"]["PaperTradingState"]
    assert export == {
        "type": "durable-object",
        "state": "created",
        "storage": "sqlite",
    }


def test_cloudflare_worker_does_not_depend_on_the_removed_ai_engine_service_binding():
    config = json.loads((ROOT / "fronted" / "wrangler.jsonc").read_text(encoding="utf-8"))
    bindings = config.get("services", [])
    assert not any(binding.get("binding") == "AI_ENGINE" for binding in bindings)
    assert "AI_ENGINE" not in json.dumps(config)


def test_cloudflare_and_fastapi_contract_use_the_same_secret_name():
    worker_adapter = (ROOT / "fronted" / "cloudflare_orchestrator.py").read_text(encoding="utf-8")
    fastapi_app = (ROOT / "fastapi_cloud_app.py").read_text(encoding="utf-8")

    assert "AI_ENGINE_URL" in worker_adapter
    assert "AI_ENGINE_SHARED_SECRET" in worker_adapter
    assert "AI_ENGINE_SHARED_SECRET" in fastapi_app
    assert "X-AI-Engine-Key" in worker_adapter
    assert "X-AI-Engine-Key" in fastapi_app


def test_paper_scheduler_is_manual_only():
    worker = (ROOT / "fronted" / "worker_entry_api.py").read_text(encoding="utf-8")
    state = (ROOT / "fronted" / "paper_state.py").read_text(encoding="utf-8")

    assert 'await stub.enable_paper(pair)' in worker
    assert 'await stub.stop()' in worker
    assert 'if not state.get("enabled")' in state
    assert "self.ctx.storage.setAlarm(next_ms)" in state
