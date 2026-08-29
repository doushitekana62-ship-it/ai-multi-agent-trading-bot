"""FastAPI Cloud AI engine entrypoint.

This service is intentionally stateless with respect to paper account state.
Cloudflare Durable Object remains the authoritative manual ON/OFF gate and
paper-account ledger. FastAPI Cloud executes the CPython multi-agent engine.
"""
from __future__ import annotations

import hmac
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from core.orchestrator import Orchestrator
from agents.agent_trading_librarian import TradingLibrarianAgent

app = FastAPI(title="AI Multi-Agent Trading Bot AI Engine", version="1.1.0")


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
    knowledge_topics: List[str] = []


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


def _apply_trading_knowledge_guard(result: Any, market_data: Dict[str, Any], knowledge: Dict[str, Any]):
    """Use the Trading Librarian as shared confirmation policy.

    The agents remain responsible for their domains. This guard only recovers a
    directional candidate when several independent scores agree and market
    movement is large enough to justify consideration. It never bypasses the
    paper execution confidence/risk gate in the Worker.
    """
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

    if action == "HOLD" and candidate != "HOLD" and abs(move) >= 0.08 and quality >= 0.55:
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
            return result

    return result


def _result_payload(result: Any, knowledge_topics: List[str]) -> Dict[str, Any]:
    action = str(getattr(result, "final_action", "HOLD") or "HOLD").upper()
    if action == "STRONG_BUY":
        action = "BUY"
    elif action == "STRONG_SELL":
        action = "SELL"
    if action not in {"BUY", "SELL", "HOLD"}:
        action = "HOLD"

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
    }


@app.get("/")
async def root():
    return {"status": "online", "service": "ai-multi-agent-trading-bot-ai-engine"}


@app.get("/health")
async def health():
    return {"status": "healthy", "runtime": "fastapi-cloud"}


@app.get("/ready")
async def ready():
    secret_configured = len(_shared_secret()) >= 32
    return {
        "status": "ready" if secret_configured else "degraded",
        "ai_engine_secret_configured": secret_configured,
        "paper_state": "external_durable_object",
        "real_trading": "locked",
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

    ohlcv = market_data.get("ohlcv") or []
    if not isinstance(ohlcv, list) or len(ohlcv) > 120:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="ohlcv must be a list containing at most 120 points")

    librarian = TradingLibrarianAgent()
    advice = librarian.advise("scalping momentum volume support resistance risk position sizing", limit=6)
    knowledge = advice.get("knowledge") or []
    market_data["trading_knowledge"] = knowledge

    try:
        orchestrator = Orchestrator({
            "use_unified_data": False,
            "use_mimic_trader": True,
            "min_confidence": 0.40,
            "max_position_size": 0.20,
            "debug_enabled": True,
        })
        result = await orchestrator.analyze(symbol, market_data)
        result = _apply_trading_knowledge_guard(result, market_data, advice)
        topics = [str(item.get("topic")) for item in knowledge if isinstance(item, dict) and item.get("topic")]
        return _result_payload(result, topics)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"AI engine analysis failed: {type(exc).__name__}") from exc
