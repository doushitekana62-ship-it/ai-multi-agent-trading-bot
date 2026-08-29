"""FastAPI Cloud AI engine entrypoint.

The service is stateless with respect to the paper account. Durable Object state
remains authoritative. This service performs the multi-agent analysis and the
Trading Librarian's deterministic candle-context analysis.
"""
from __future__ import annotations

import hmac
import os
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from agents.agent_trading_librarian import TradingLibrarianAgent
from core.orchestrator import Orchestrator

app = FastAPI(title="AI Multi-Agent Trading Bot AI Engine", version="1.2.0")


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str = Field(min_length=3, max_length=20)
    market_data: Dict[str, Any]


class AnalysisResponse(BaseModel):
    ok: bool = True
    timestamp: str
    symbol: str
    current_price: float
    final_action: str
    final_confidence: float
    consensus_action: str
    consensus_score: float
    agent_votes: Dict[str, str]
    market_scores: Dict[str, float]
    confidence_components: Dict[str, float]
    position_size: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    execution_reason: Optional[str] = None
    hold_reason: Optional[str] = None
    summary: str
    knowledge_topics: List[str] = Field(default_factory=list)
    library_version: str = TradingLibrarianAgent.LIBRARY_VERSION
    candle_analysis: Dict[str, Any] = Field(default_factory=dict)
    library_alerts: List[Dict[str, Any]] = Field(default_factory=list)


_ALLOWED_SYMBOLS = {"BTC/IDR", "ETH/IDR", "USDT/IDR", "XRP/IDR", "DOGE/IDR", "SOL/IDR"}


def _shared_secret() -> str:
    return str(os.getenv("AI_ENGINE_SHARED_SECRET", "")).strip()


def _require_engine_key(value: Optional[str]) -> None:
    secret = _shared_secret()
    if len(secret) < 32:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI engine shared secret is not configured")
    if not value or not hmac.compare_digest(value, secret):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid AI engine credential")


def _clean_number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number or number in (float("inf"), float("-inf")):
        return default
    return number


def _score_to_action(score: float) -> str:
    if score >= 0.30:
        return "BUY"
    if score <= -0.30:
        return "SELL"
    return "HOLD"


def _build_candles_from_trades(trades: Any, bucket_seconds: int = 60) -> List[Dict[str, Any]]:
    """Convert bounded public trade observations into real OHLCV buckets.

    The Worker previously represented each trade as O=H=L=C. That is not a
    candlestick. This aggregation preserves the actual trade sequence and makes
    candle pattern detection possible without inventing OHLC values.
    """
    if not isinstance(trades, list):
        return []
    buckets: "OrderedDict[int, Dict[str, Any]]" = OrderedDict()
    for trade in trades[-240:]:
        if not isinstance(trade, dict):
            continue
        price = _clean_number(trade.get("price"))
        if price <= 0:
            continue
        timestamp = _clean_number(trade.get("timestamp") or trade.get("date"))
        if timestamp <= 0:
            continue
        bucket = int(timestamp // bucket_seconds) * bucket_seconds
        volume = max(0.0, _clean_number(trade.get("amount")))
        if bucket not in buckets:
            buckets[bucket] = {"timestamp": datetime.fromtimestamp(bucket, tz=timezone.utc).isoformat(), "open": price, "high": price, "low": price, "close": price, "volume": volume}
        else:
            candle = buckets[bucket]
            candle["high"] = max(candle["high"], price)
            candle["low"] = min(candle["low"], price)
            candle["close"] = price
            candle["volume"] += volume
    return list(buckets.values())[-120:]


def _prepare_candles(market_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    candles = market_data.get("ohlcv")
    if isinstance(candles, list) and len(candles) >= 2:
        meaningful = [
            item for item in candles
            if isinstance(item, dict) and abs(_clean_number(item.get("high")) - _clean_number(item.get("low"))) > 0
        ]
        if len(meaningful) >= 2:
            return candles[-120:]
    return _build_candles_from_trades(market_data.get("recent_trades"))


def _apply_trading_knowledge_guard(result: Any, market_data: Dict[str, Any], knowledge: Dict[str, Any], candle_analysis: Dict[str, Any]):
    """Use the shared library as confirmation, never as a risk bypass."""
    action = str(getattr(result, "final_action", "HOLD") or "HOLD").upper()
    scores = {str(k): _clean_number(v) for k, v in dict(getattr(result, "market_scores", {}) or {}).items()}
    technical = scores.get("technical", 0.0)
    decision = scores.get("decision", 0.0)
    forecast = scores.get("forecast", 0.0)
    sentiment = scores.get("sentiment", 0.0)
    directional = 0.38 * technical + 0.27 * decision + 0.20 * forecast + 0.15 * sentiment

    move = _clean_number(market_data.get("short_term_move_percent", market_data.get("change_percent_24h")))
    quality = _clean_number(market_data.get("data_quality_score"), 0.5)
    candidate = _score_to_action(directional)
    candle_direction = str(candle_analysis.get("direction") or "NEUTRAL").upper()
    candle_opportunity = bool(candle_analysis.get("opportunity"))

    # The library can confirm an existing directional setup, but a candle alert
    # alone cannot create an execution decision.
    if action == "HOLD" and candidate != "HOLD" and abs(move) >= 0.08 and quality >= 0.55:
        if candle_direction in {"NEUTRAL", candidate}:
            existing_confidence = _clean_number(getattr(result, "final_confidence", 0.0))
            recovered_confidence = max(existing_confidence, min(0.70, 0.50 + abs(directional) * 0.45))
            if recovered_confidence >= 0.60:
                result.final_action = candidate
                result.final_confidence = recovered_confidence
                result.consensus_action = candidate
                result.consensus_score = directional
                result.execution_reason = (
                    "Trading Librarian confirmation recovered a directional candidate from "
                    "technical/decision/forecast agreement; final paper risk gate still applies."
                )
                result.hold_reason = None
                result.confidence_components = dict(getattr(result, "confidence_components", {}) or {})
                result.confidence_components["knowledge_directional_score"] = directional
                result.confidence_components["knowledge_guard_recovered"] = 1.0

    if candle_opportunity and candle_direction == str(result.final_action).upper():
        result.confidence_components = dict(getattr(result, "confidence_components", {}) or {})
        result.confidence_components["library_opportunity_confirmation"] = 1.0

    return result


def _result_payload(result: Any, knowledge_topics: List[str], candle_analysis: Dict[str, Any]) -> Dict[str, Any]:
    action = str(getattr(result, "final_action", "HOLD") or "HOLD").upper()
    if action == "STRONG_BUY":
        action = "BUY"
    elif action == "STRONG_SELL":
        action = "SELL"
    if action not in {"BUY", "SELL", "HOLD"}:
        action = "HOLD"

    library_alerts = list(candle_analysis.get("alerts") or [])[:4]
    return {
        "ok": True,
        "timestamp": getattr(result, "timestamp", datetime.now(timezone.utc)).isoformat(),
        "symbol": str(getattr(result, "symbol", "")).upper(),
        "current_price": _clean_number(getattr(result, "current_price", 0)),
        "final_action": action,
        "final_confidence": max(0.0, min(1.0, _clean_number(getattr(result, "final_confidence", 0)))),
        "consensus_action": str(getattr(result, "consensus_action", "HOLD") or "HOLD"),
        "consensus_score": _clean_number(getattr(result, "consensus_score", 0)),
        "agent_votes": {str(k): str(v) for k, v in dict(getattr(result, "agent_votes", {}) or {}).items()},
        "market_scores": {str(k): _clean_number(v) for k, v in dict(getattr(result, "market_scores", {}) or {}).items()},
        "confidence_components": {str(k): _clean_number(v) for k, v in dict(getattr(result, "confidence_components", {}) or {}).items()},
        "position_size": max(0.0, min(0.20, _clean_number(getattr(result, "position_size", 0)))),
        "stop_loss": getattr(result, "stop_loss", None),
        "take_profit": getattr(result, "take_profit", None),
        "execution_reason": getattr(result, "execution_reason", None),
        "hold_reason": getattr(result, "hold_reason", None),
        "summary": str(getattr(result, "summary", "AI engine completed analysis.") or "AI engine completed analysis."),
        "knowledge_topics": knowledge_topics,
        "library_version": TradingLibrarianAgent.LIBRARY_VERSION,
        "candle_analysis": candle_analysis,
        "library_alerts": library_alerts,
    }


@app.get("/")
async def root():
    return {"status": "online", "service": "ai-multi-agent-trading-bot-ai-engine"}


@app.get("/health")
async def health():
    return {"status": "healthy", "runtime": "fastapi-cloud", "library_version": TradingLibrarianAgent.LIBRARY_VERSION}


@app.get("/ready")
async def ready():
    secret_configured = len(_shared_secret()) >= 32
    return {
        "status": "ready" if secret_configured else "degraded",
        "ai_engine_secret_configured": secret_configured,
        "paper_state": "external_durable_object",
        "real_trading": "locked",
        "library_version": TradingLibrarianAgent.LIBRARY_VERSION,
    }


@app.post("/engine/analyze", response_model=AnalysisResponse)
async def analyze(request: AnalysisRequest, x_ai_engine_key: Optional[str] = Header(default=None)):
    _require_engine_key(x_ai_engine_key)

    symbol = request.symbol.upper().strip().replace("_", "/")
    if symbol not in _ALLOWED_SYMBOLS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported paper symbol: {symbol}")

    market_data = dict(request.market_data or {})
    market_data.pop("_force_action", None)
    current_price = _clean_number(market_data.get("current_price") or market_data.get("unified_price"))
    if current_price <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="current_price must be greater than zero")

    candles = _prepare_candles(market_data)
    market_data["ohlcv"] = candles
    candle_analysis = TradingLibrarianAgent.analyze_candles(
        candles,
        current_price=current_price,
        high_24h=_clean_number(market_data.get("high_24h")),
        low_24h=_clean_number(market_data.get("low_24h")),
    )

    librarian = TradingLibrarianAgent()
    advice = librarian.advise(
        "scalping momentum volume candlestick ohlcv doji engulfing hammer support resistance risk position sizing",
        limit=8,
    )
    knowledge = advice.get("knowledge") or []
    market_data["trading_knowledge"] = knowledge
    market_data["library_context"] = {
        "version": TradingLibrarianAgent.LIBRARY_VERSION,
        "candle_analysis": candle_analysis,
        "alert_count": len(candle_analysis.get("alerts") or []),
    }

    if not isinstance(candles, list) or len(candles) > 120:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="ohlcv must contain at most 120 bounded points")

    try:
        orchestrator = Orchestrator({
            "use_unified_data": False,
            "use_mimic_trader": True,
            "min_confidence": 0.40,
            "max_position_size": 0.20,
            "debug_enabled": True,
        })
        result = await orchestrator.analyze(symbol, market_data)
        result = _apply_trading_knowledge_guard(result, market_data, advice, candle_analysis)
        topics = [str(item.get("topic")) for item in knowledge if isinstance(item, dict) and item.get("topic")]
        return _result_payload(result, topics, candle_analysis)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"AI engine analysis failed: {type(exc).__name__}") from exc
