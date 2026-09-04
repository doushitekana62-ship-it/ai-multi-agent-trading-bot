from time import time

from backend.routes.market import _pulse


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
