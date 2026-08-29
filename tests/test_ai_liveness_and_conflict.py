from datetime import datetime, timezone, timedelta

from agents.agent_decision import DecisionAgent
from agents.agent_forecast import ForecastAgent
from core.signal_contract import AnalyticalSignal, SignalStatus


def _signal(agent, score, confidence=0.85):
    return AnalyticalSignal(
        agent=agent,
        symbol="BTC/IDR",
        direction="BULLISH" if score > 0 else "BEARISH" if score < 0 else "NEUTRAL",
        score=score,
        confidence=confidence,
        timeframe="1m",
        evidence=[f"{agent} replay evidence"],
        data_timestamp=datetime.now(timezone.utc),
        data_age_seconds=1,
        status=SignalStatus.OK.value,
    )


def test_trader_can_reach_buy_on_aligned_bullish_evidence():
    trader = DecisionAgent({"min_candidate_score": 0.55, "min_confidence": 0.60, "min_confirmations": 2})
    result = trader.analyze(
        "BTC/IDR",
        market_data={"unified_price": 100.0, "timeframe": "1m"},
        evidence=[_signal("technical", 0.80), _signal("forecast", 0.72), _signal("trading_librarian", 0.60, 0.65)],
        debate={"conflict_score": 0.0, "contradictions": []},
    )
    assert result.action == "BUY"
    assert result.confidence >= 0.60


def test_trader_can_reach_sell_on_aligned_bearish_evidence():
    trader = DecisionAgent({"min_candidate_score": 0.55, "min_confidence": 0.60, "min_confirmations": 2})
    result = trader.analyze(
        "BTC/IDR",
        market_data={"unified_price": 100.0, "timeframe": "1m"},
        evidence=[_signal("technical", -0.80), _signal("forecast", -0.72), _signal("trading_librarian", -0.60, 0.65)],
        debate={"conflict_score": 0.0, "contradictions": []},
    )
    assert result.action == "SELL"
    assert result.confidence >= 0.60


def test_material_conflict_does_not_flip_into_opposite_direction():
    trader = DecisionAgent({"min_candidate_score": 0.55, "min_confidence": 0.60, "min_confirmations": 2, "max_conflict": 0.20})
    result = trader.analyze(
        "BTC/IDR",
        market_data={"unified_price": 100.0, "timeframe": "1m"},
        evidence=[_signal("technical", 0.80), _signal("forecast", -0.80)],
        debate={"conflict_score": 0.80, "contradictions": ["technical vs forecast"]},
    )
    assert result.action == "HOLD"
    assert result.no_trade_reason == "MATERIAL_AGENT_CONFLICT"


def test_forecast_is_independent_of_technical_vote():
    candles = []
    base = datetime.now(timezone.utc) - timedelta(minutes=40)
    for i in range(40):
        price = 100.0 + i * 0.05
        candles.append({
            "timestamp": (base + timedelta(minutes=i)).isoformat(),
            "open": price,
            "high": price + 0.02,
            "low": price - 0.02,
            "close": price,
            "volume": 100.0,
        })
    forecast = ForecastAgent()
    bullish = forecast.analyze("BTC/IDR", technical_result=type("R", (), {"overall_score": 0.9})(), market_data={"current_price": 102.0, "unified_price": 102.0, "timestamp": datetime.now(timezone.utc), "timeframe": "1m", "ohlcv": candles})
    bearish = forecast.analyze("BTC/IDR", technical_result=type("R", (), {"overall_score": -0.9})(), market_data={"current_price": 102.0, "unified_price": 102.0, "timestamp": datetime.now(timezone.utc), "timeframe": "1m", "ohlcv": candles})
    assert bullish.score == bearish.score
    assert bullish.direction == bearish.direction


def test_unavailable_signal_is_not_a_hold_vote():
    signal = AnalyticalSignal(
        agent="forecast", symbol="BTC/IDR", direction="NEUTRAL", score=0.0, confidence=0.0,
        status=SignalStatus.UNAVAILABLE.value,
    )
    assert not signal.usable()
