from fastapi.testclient import TestClient

from backend.api import APP_ENTRYPOINT, APP_VERSION, app
from fastapi_cloud_app import app as compatibility_app


def test_health_and_ready_use_canonical_fastapi_contract():
    with TestClient(app) as client:
        health = client.get('/health')
        assert health.status_code == 200
        payload = health.json()
        assert payload['status'] == 'healthy'
        assert payload['entrypoint'] == APP_ENTRYPOINT == 'backend.api:app'
        assert payload['version'] == APP_VERSION
        assert payload['paper_mode'] is True
        assert payload['real_trading_locked'] is True

        ready = client.get('/ready')
        assert ready.status_code == 200
        assert ready.json()['entrypoint'] == 'backend.api:app'


def test_compatibility_module_exports_the_same_application():
    assert compatibility_app is app


def test_legacy_engine_endpoint_is_not_required_by_the_canonical_service():
    paths = {route.path for route in app.routes}
    assert '/engine/analyze' not in paths
    assert '/api/dashboard/analyze' in paths
