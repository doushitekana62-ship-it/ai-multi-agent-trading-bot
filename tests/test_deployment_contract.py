from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTED = ROOT / "fronted"
WORKFLOWS = ROOT / ".github" / "workflows"


def test_fastapi_cloud_uses_canonical_backend_entrypoint():
    config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    shim = (ROOT / "fastapi_cloud_app.py").read_text(encoding="utf-8")
    assert '[tool.fastapi]' in config
    assert 'entrypoint = "backend.api:app"' in config
    assert "from backend.api import app" in shim
    assert 'entrypoint = "fastapi_cloud_app:app"' not in config


def test_canonical_fastapi_app_exposes_deployment_identity():
    source = (ROOT / "backend" / "api.py").read_text(encoding="utf-8")
    assert 'APP_ENTRYPOINT = "backend.api:app"' in source
    assert '@app.get("/health")' in source
    assert '"entrypoint": APP_ENTRYPOINT' in source
    assert '"real_trading_locked": True' in source


def test_cloudflare_runtime_is_not_part_of_the_active_deployment():
    forbidden = [
        FRONTED / "cf_worker.py",
        FRONTED / "cloudflare_orchestrator.py",
        FRONTED / "paper_cycle.py",
        FRONTED / "paper_state.py",
        FRONTED / "worker_entry_api.py",
        FRONTED / "worker_entry.py",
        FRONTED / "worker_entry_live.py",
        FRONTED / "wrangler.jsonc",
        FRONTED / "asgi.py",
        FRONTED / "indodax_client.py",
        FRONTED / "risk_engine.py",
        FRONTED / "risk_templates.py",
    ]
    assert all(not path.exists() for path in forbidden)


def test_github_workflows_do_not_deploy_to_cloudflare():
    for workflow in WORKFLOWS.glob("*.yml"):
        text = workflow.read_text(encoding="utf-8").lower()
        assert "wrangler" not in text, workflow
        assert "cloudflare_api_token" not in text, workflow
        assert "cloudflare_account_id" not in text, workflow


def test_github_pages_build_uses_public_fastapi_api_url():
    workflow = (WORKFLOWS / "github-pages.yml").read_text(encoding="utf-8")
    assert "VITE_API_URL" in workflow
    assert "fastapicloud.dev" in workflow
    assert "actions/deploy-pages@v4" in workflow


def test_backend_smoke_does_not_require_a_missing_requirements_file():
    workflow = (WORKFLOWS / "backend-smoke.yml").read_text(encoding="utf-8")
    assert "pip install -r requirements.txt" not in workflow
    assert "pip install -e ." in workflow
    assert "from backend.api import app" in workflow


def test_production_secret_names_are_documented_without_exposing_values():
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "SUPABASE_URL=" in env_example
    assert "SUPABASE_SECRET_KEY=" in env_example
    assert "JWT_SECRET_KEY=" in env_example
    assert "ADMIN_USERNAME=" in env_example
    assert "ADMIN_PASSWORD=" in env_example


def test_frontend_is_github_pages_compatible():
    vite = (FRONTED / "vite.config.mjs").read_text(encoding="utf-8")
    package = (FRONTED / "package.json").read_text(encoding="utf-8")
    assert "'/ai-multi-agent-trading-bot/'" in vite or '"/ai-multi-agent-trading-bot/"' in vite
    assert "wrangler" not in package.lower()
