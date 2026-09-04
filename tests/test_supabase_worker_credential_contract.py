from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTED = ROOT / "fronted"


def test_all_cloudflare_paper_paths_accept_current_and_legacy_supabase_server_keys():
    sources = [
        (FRONTED / "worker_entry_api.py").read_text(encoding="utf-8"),
        (FRONTED / "paper_state.py").read_text(encoding="utf-8"),
        (FRONTED / "paper_cycle.py").read_text(encoding="utf-8"),
    ]
    for source in sources:
        assert "SUPABASE_SECRET_KEY" in source
        assert "SUPABASE_SERVICE_ROLE_KEY" in source


def test_paper_cycle_does_not_use_only_the_legacy_supabase_key():
    source = (FRONTED / "paper_cycle.py").read_text(encoding="utf-8")
    assert 'getattr(env,"SUPABASE_SECRET_KEY","") or getattr(env,"SUPABASE_SERVICE_ROLE_KEY","")' in source


def test_worker_supabase_health_and_paper_cycle_share_the_same_project_url_contract():
    worker = (FRONTED / "worker_entry_api.py").read_text(encoding="utf-8")
    config = (FRONTED / "wrangler.jsonc").read_text(encoding="utf-8")
    assert "def _supabase_key(env)" in worker
    assert "SUPABASE_URL" in worker
    assert "SUPABASE_URL" in config
    assert "opclkckfdlkqzunzmwym.supabase.co" in config
