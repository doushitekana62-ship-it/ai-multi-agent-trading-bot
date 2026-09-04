import asyncio
from time import time

import backend.routes.market as market_module
from backend.routes.market import _overview, _pulse


def test_market_pulse_keeps_intraminute_directional_change():
    now = time()
    current_minute = int(now // 60) * 60
    points = [
        {"timestamp": current_minute + 5, "price": 100.0},
        {"timestamp": current_minute + 20, "price": 101.0},
        {"timestamp": current_minute + 40, "price": 99.5},
    ]
    segments, _ = _pulse(points, now)
    current = segments[-1]
    assert current["samples"] == 3
    assert current["changed"] is True
    assert current["status"] == "RED"
    assert current["open"] == 100.0
    assert current["close"] == 99.5


def test_market_pulse_returns_exactly_thirty_one_minute_segments():
    now = time()
    segments, _ = _pulse([], now)
    assert len(segments) == 30
    assert all(segment["status"] == "GRAY" for segment in segments)


def test_market_overview_keeps_ticker_when_trade_history_is_unavailable(monkeypatch):
    now = time()

    def fake_get(path):
        if path == "/btc_idr/ticker":
            return {
                "ticker": {
                    "last": "1750000000",
                    "buy": "1749000000",
                    "sell": "1751000000",
                    "high": "1760000000",
                    "low": "1720000000",
                    "vol_idr": "1234567890",
                }
            }
        if path == "/btc_idr/trades":
            raise TimeoutError("trade history unavailable")
        raise AssertionError(path)

    monkeypatch.setattr(market_module, "_get", fake_get)
    monkeypatch.setattr(market_module.time, "time", lambda: now)

    result = asyncio.run(_overview("btc_idr"))

    assert result["available"] is True
    assert result["last"] == 1750000000.0
    assert result["market_data_quality"] == "TICKER_FALLBACK"
    assert result["market_data_quality_score"] < 0.70
    assert result["trades_available"] is False
    assert result["trades_error"] == "TimeoutError"
    assert len(result["pulse_segments"]) == 30
    assert result["pulse_segments"][-1]["samples"] == 1
