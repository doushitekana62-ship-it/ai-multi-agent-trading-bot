from agents.agent_trading_librarian import TradingLibrarianAgent


def test_bullish_engulfing_is_alert_only_and_requires_confirmation():
    candles = [
        {"timestamp": "2026-08-29T08:00:00Z", "open": 100, "high": 101, "low": 95, "close": 96, "volume": 100},
        {"timestamp": "2026-08-29T08:01:00Z", "open": 95, "high": 106, "low": 94, "close": 105, "volume": 160},
    ]
    result = TradingLibrarianAgent.analyze_candles(candles, current_price=105, high_24h=110, low_24h=90)
    assert result["available"] is True
    assert result["pattern"] == "BULLISH_ENGULFING"
    assert result["direction"] == "BUY"
    assert result["alerts"]
    assert result["alerts"][0]["requires_confirmation"] is True


def test_doji_does_not_create_directional_opportunity():
    candles = [
        {"timestamp": "2026-08-29T08:00:00Z", "open": 100, "high": 101, "low": 99, "close": 100.2, "volume": 100},
        {"timestamp": "2026-08-29T08:01:00Z", "open": 100, "high": 106, "low": 94, "close": 100.1, "volume": 180},
    ]
    result = TradingLibrarianAgent.analyze_candles(candles, current_price=100.1, high_24h=110, low_24h=90)
    assert result["pattern"] == "DOJI_INDECISION"
    assert result["direction"] == "NEUTRAL"
    assert result["opportunity"] is False


def test_insufficient_candle_data_is_safe():
    result = TradingLibrarianAgent.analyze_candles([], current_price=100)
    assert result["available"] is False
    assert result["alerts"] == []
