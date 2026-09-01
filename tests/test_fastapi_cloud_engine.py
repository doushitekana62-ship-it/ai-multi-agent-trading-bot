from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from fastapi_cloud_app import app


def _market_data():
    prices = [100_000_000 + i * 10_000 + ((i % 7) - 3) * 5_000 for i in range(100)]
    now = datetime.now(timezone.utc)
    ohlcv = [
        {
            "timestamp": (now - timedelta(minutes=99 - i)).isoformat(),
            "open": float(price),
            "high": float(price * 1.001),
            "low": float(price * 0.999),
            "close": float(price),
            "volume": 1000.0 + i,
        }
        for i, price in enumerate(prices)
    ]
    return {
        "current_price": float(prices[-1]),
        "unified_price": float(prices[-1]),
        "timestamp": now.isoformat(),
        "timeframe": "1m",
        "ohlcv": ohlcv,
        "high_24h": float(max(prices)),
        "low_24h": float(min(prices)),
        "volume_24h": 5_000_000.0,
        "change_percent_24h": 0.5,
        "short_term_move_percent": 0.5,
        "data_quality_score": 0.9,
        "recent_trades": [],
    }


def test_health_and_ready():
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "healthy"
        ready = client.get("/ready").json()
        assert ready["real_trading"] == "locked"


def test_analyze_requires_shared_secret(monkeypatch):
    monkeypatch.setenv("AI_ENGINE_SHARED_SECRET", "x" * 32)
    with TestClient(app) as client:
        response = client.post(
            "/engine/analyze",
            json={"symbol": "BTC/IDR", "market_data": _market_data()},
        )
        assert response.status_code == 401


def test_analyze_runs_existing_multi_agent_orchestrator(monkeypatch):
    secret = "x" * 32
    monkeypatch.setenv("AI_ENGINE_SHARED_SECRET", secret)
    with TestClient(app) as client:
        response = client.post(
            "/engine/analyze",
            headers={"X-AI-Engine-Key": secret},
            json={"symbol": "BTC/IDR", "market_data": _market_data()},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["ok"] is True
        assert payload["symbol"] == "BTC/IDR"
        assert payload["final_action"] in {"BUY", "SELL", "HOLD"}
        assert set(payload["agent_votes"]).issuperset({"technical", "forecast"})
        assert "sentiment" not in payload["agent_votes"]
        assert payload["hold_analysis"]["diagnostic"]


def test_real_trading_bypass_is_not_accepted(monkeypatch):
    secret = "x" * 32
    monkeypatch.setenv("AI_ENGINE_SHARED_SECRET", secret)
    data = _market_data()
    data["_force_action"] = "BUY"
    with TestClient(app) as client:
        response = client.post(
            "/engine/analyze",
            headers={"X-AI-Engine-Key": secret},
            json={"symbol": "BTC/IDR", "market_data": data},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["final_action"] in {"BUY", "SELL", "HOLD"}
        assert payload["final_action"] != "STRONG_BUY"
