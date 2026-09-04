from datetime import datetime, timedelta, timezone

from core.unified_market_data import UnifiedMarketSnapshot


def test_market_snapshot_becomes_stale_from_source_timestamp():
    snapshot = UnifiedMarketSnapshot(
        symbol="BTC/IDR",
        timestamp=datetime.now(timezone.utc) - timedelta(seconds=91),
        timeframe="1m",
        current_price=100.0,
        data_quality_score=1.0,
    )
    assert snapshot.is_stale(90) is True
    assert snapshot.is_fresh is False
    assert snapshot.age_seconds >= 90
    assert snapshot.is_valid() is False


def test_market_snapshot_freshness_is_exposed_to_agents():
    snapshot = UnifiedMarketSnapshot(
        symbol="BTC/IDR",
        timestamp=datetime.now(timezone.utc) - timedelta(seconds=2),
        timeframe="1m",
        current_price=100.0,
        data_quality_score=1.0,
    )
    payload = snapshot.to_dict()
    assert payload["is_fresh"] is True
    assert payload["age_seconds"] < 10
    assert payload["current_price"] == 100.0
