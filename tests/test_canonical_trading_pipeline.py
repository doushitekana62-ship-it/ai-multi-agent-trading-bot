import asyncio
from datetime import datetime, timezone

from agents.agent_decision import DecisionAgent
from agents.agent_forecast import ForecastAgent
from agents.agent_sentiment import SentimentAgent
from agents.agent_technical import TechnicalAgent
from core.hold_diagnostics import HoldDiagnostics


def candles(values):
    now = int(datetime.now(timezone.utc).timestamp())
    return [{"open": v * 0.999, "high": v * 1.002, "low": v * 0.998, "close": v, "volume": 1000 + i * 50, "timestamp": now - (len(values)-i)*60} for i, v in enumerate(values)]


def test_missing_data_is_not_normal_hold():
    result = TechnicalAgent().analyze("BTC/IDR", {"current_price": 100, "unified_price": 100, "ohlcv": []})
    assert result.status == "UNAVAILABLE"
    assert "INSUFFICIENT_OHLCV" in result.evidence


def test_bullish_replay_produces_directional_evidence():
    values = [100 + i * 0.35 for i in range(100)]
    data = {"symbol": "BTC/IDR", "current_price": values[-1], "unified_price": values[-1], "ohlcv": candles(values), "timestamp": datetime.now(timezone.utc), "timeframe": "1m"}
    technical = TechnicalAgent().analyze("BTC/IDR", data)
    forecast = ForecastAgent().analyze("BTC/IDR", technical_result=technical, market_data=data)
    sentiment = SentimentAgent().analyze("BTC/IDR", data)
    decision = DecisionAgent().analyze("BTC/IDR", sentiment, technical, data, forecast_result=forecast)
    assert technical.direction == "BULLISH"
    assert decision.action in {"BUY", "HOLD"}
    assert decision.status == "OK"
    assert decision.no_trade_reason != "NO_USABLE_ANALYTICAL_EVIDENCE"


def test_bearish_replay_produces_directional_evidence():
    values = [150 - i * 0.40 for i in range(100)]
    data = {"symbol": "BTC/IDR", "current_price": values[-1], "unified_price": values[-1], "ohlcv": candles(values), "timestamp": datetime.now(timezone.utc), "timeframe": "1m"}
    technical = TechnicalAgent().analyze("BTC/IDR", data)
    forecast = ForecastAgent().analyze("BTC/IDR", technical_result=technical, market_data=data)
    decision = DecisionAgent().analyze("BTC/IDR", None, technical, data, forecast_result=forecast)
    assert technical.direction == "BEARISH"
    assert decision.action in {"SELL", "HOLD"}


def test_degraded_sentiment_is_not_a_directional_vote():
    result = SentimentAgent().analyze("BTC/IDR", {"current_price": 100, "unified_price": 100, "ohlcv": candles([100+i for i in range(10)]), "timestamp": datetime.now(timezone.utc)})
    assert result.status == "UNAVAILABLE"
    assert result.direction == "NEUTRAL"


def test_hold_diagnostics_identifies_repeated_holds():
    diagnostics = HoldDiagnostics()
    warning = None
    for _ in range(10):
        warning = diagnostics.observe(action="HOLD", cycle_status="NO_EDGE", movement_available=True, score=0.0)
    assert warning is not None
    assert "10 consecutive HOLD" in warning
