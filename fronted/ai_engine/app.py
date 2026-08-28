"""Full CPython AI engine for Cloudflare Container.

This service owns the heavyweight multi-agent stack (NumPy/Pandas/SciPy/
scikit-learn). The Cloudflare Python Worker remains the control plane and
paper-state/scheduler owner and calls this service for one AI decision.
"""
from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from core.orchestrator import Orchestrator


class AnalyzeRequest(BaseModel):
    symbol: str = Field(min_length=2, max_length=32)
    market_data: Dict[str, Any] = Field(default_factory=dict)


app = FastAPI(title="AI Trading Full Engine", version="1.0.0")
_engine = Orchestrator(
    {
        "use_unified_data": False,
        "use_mimic_trader": True,
        "min_confidence": 0.40,
        "max_position_size": 0.20,
        "debug_enabled": True,
    }
)


def _check_key(value: str | None) -> None:
    expected = os.getenv("AI_ENGINE_KEY", "").strip()
    if expected and value != expected:
        raise HTTPException(status_code=401, detail="Invalid AI engine key")


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"ok": True, "service": "ai_engine", "mode": "paper"}


@app.post("/analyze")
async def analyze(payload: AnalyzeRequest, x_ai_engine_key: str | None = Header(default=None)) -> Dict[str, Any]:
    _check_key(x_ai_engine_key)
    symbol = payload.symbol.upper()
    result = await _engine.analyze(symbol, dict(payload.market_data or {}))

    return {
        "ok": True,
        "symbol": result.symbol,
        "timestamp": result.timestamp.isoformat(),
        "current_price": _num(result.current_price),
        "final_action": result.final_action,
        "final_confidence": _num(result.final_confidence),
        "consensus_action": result.consensus_action,
        "consensus_score": _num(result.consensus_score),
        "agent_votes": dict(result.agent_votes or {}),
        "market_scores": {k: _num(v) for k, v in dict(result.market_scores or {}).items()},
        "confidence_components": {
            k: _num(v) for k, v in dict(result.confidence_components or {}).items()
        },
        "position_size": _num(result.position_size),
        "stop_loss": result.stop_loss,
        "take_profit": result.take_profit,
        "execution_reason": result.execution_reason,
        "hold_reason": result.hold_reason,
        "summary": result.summary,
    }
