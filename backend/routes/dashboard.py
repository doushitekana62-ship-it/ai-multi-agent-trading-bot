"""Dashboard Routes - read-only dashboard state and explicitly gated analysis."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.core.database import db
from backend.core.security import verify_token
from core.executor import Executor
from core.orchestrator import Orchestrator
from core.runtime_state import get_engine_status, get_last_orchestrator_result

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer()
orchestrator = Orchestrator()
executor = Executor({"exchange_mode": "paper"})
paper_trading = executor.paper_trading


def authenticate(credentials: HTTPAuthorizationCredentials):
    payload = verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return payload


def _latest_snapshot(symbol: str):
    latest = get_last_orchestrator_result()
    if latest is not None:
        latest_symbol = str(getattr(latest, "symbol", "")).upper()
        if latest_symbol == symbol.upper():
            snapshot = getattr(latest, "unified_snapshot", None)
            if snapshot is not None:
                snapshot.is_stale(60)
                return snapshot
    try:
        snapshot = orchestrator.market_data_provider.get_snapshot(symbol.upper())
        if snapshot is not None:
            snapshot.is_stale(60)
        return snapshot
    except Exception:
        logger.exception("Unable to inspect cached market snapshot for %s", symbol)
        return None


def _agent_health(name, result, engine, warning="", source=""):
    """Derive health from actual latest evidence when available.

    ARMED means configured but not proven to have executed. ON requires a
    recent successful result for that specialist; this prevents the dashboard
    from claiming all five agents are healthy merely because the engine is on.
    """
    now = datetime.now(timezone.utc)
    obj = getattr(result, name, None) if result is not None else None
    status_value = str(getattr(obj, "status", "") or "").upper() if obj is not None else ""
    timestamp = getattr(obj, "data_timestamp", None) or getattr(obj, "timestamp", None) if obj is not None else None
    age = getattr(obj, "data_age_seconds", None) if obj is not None else None
    if age is None and isinstance(timestamp, datetime):
        age = max(0.0, (now - (timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc))).total_seconds())
    if status_value in {"DEGRADED", "UNAVAILABLE"}:
        state = "DEGRADED" if status_value == "DEGRADED" else "BROKE"
    elif obj is not None and bool(engine.get("running")):
        state = "ON"
    elif bool(engine.get("running")):
        state = "ARMED"
    else:
        state = "OFF"
    return {
        "name": name.title().replace("_", " ") + " Agent",
        "status": state,
        "availability": "AVAILABLE" if obj is not None and status_value not in {"UNAVAILABLE", ""} else "UNAVAILABLE" if obj is None else status_value,
        "engine_running": bool(engine.get("running")),
        "last_success_at": timestamp.isoformat() if isinstance(timestamp, datetime) else timestamp,
        "data_age_seconds": float(age) if age is not None else None,
        "source": source or "process-local orchestrator result",
        "warning": warning or None,
        "signal_status": status_value or ("NOT_RUN" if obj is None else "UNKNOWN"),
    }


@router.get("/status")
async def get_status(symbol: str = Query("BTC/IDR"), credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        authenticate(credentials)
        symbol = symbol.upper().strip()
        trades = db.get_trades(limit=1000)
        total_pnl = 0.0; winning_trades = 0; losing_trades = 0
        for trade in trades:
            try: pnl = float(trade.get("pnl", 0) or 0)
            except (TypeError, ValueError): pnl = 0.0
            total_pnl += pnl; winning_trades += int(pnl > 0); losing_trades += int(pnl < 0)
        total_trades = len(trades); win_rate = winning_trades / total_trades if total_trades else 0.0
        portfolio_value = None; balance = None
        try:
            portfolio_value = paper_trading.get_portfolio_value(); balance = paper_trading.balance
        except Exception as exc: logger.warning("Paper portfolio unavailable: %s", exc)
        snapshot = _latest_snapshot(symbol); engine = get_engine_status()
        market_data = {"available": snapshot is not None, "fresh": bool(snapshot is not None and not snapshot.is_stale(60)), "stale": bool(snapshot is None or snapshot.is_stale(60)), "age_seconds": float(getattr(snapshot, "age_seconds", 0.0)) if snapshot is not None else None, "timestamp": snapshot.timestamp.isoformat() if snapshot is not None else None, "symbol": symbol}
        return {"status": "running", "timestamp": datetime.now(timezone.utc).isoformat(), "database": {"connected": db.is_connected()}, "trading": {"exchange_mode": engine["mode"], "active_positions": len(getattr(executor, "active_positions", {})), "total_trades": total_trades, "winning_trades": winning_trades, "losing_trades": losing_trades, "win_rate": win_rate, "total_pnl": total_pnl, "daily_pnl": getattr(executor, "daily_pnl", 0), "daily_trades": getattr(executor, "daily_trades", 0)}, "portfolio": {"value": portfolio_value, "balance": balance}, "system_health": {"database": {"connected": db.is_connected()}, "market_data": market_data, "mode": engine["mode"], "engine": {"running": engine["running"], "last_cycle_at": engine["last_cycle_at"]}}}
    except HTTPException: raise
    except Exception:
        logger.exception("Error getting dashboard status")
        raise HTTPException(status_code=500, detail="Failed to get dashboard status")


@router.get("/agents")
async def get_agents_status(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Expose truthful runtime and specialist health; ARMED never means healthy."""
    try:
        authenticate(credentials)
        engine = get_engine_status()
        latest = get_last_orchestrator_result()
        now = datetime.now(timezone.utc)
        warning = str(getattr(latest, "engine_warning", "") or "") if latest is not None else ""
        source = str(getattr(latest, "engine_source", "") or "") if latest is not None else ""
        last_cycle = engine.get("last_cycle_at")
        age = None
        if last_cycle:
            try: age = max(0.0, (now - datetime.fromisoformat(str(last_cycle))).total_seconds())
            except (TypeError, ValueError): pass
        names = [
            ("sentiment", "Sentiment Agent", "Market sentiment analysis"),
            ("technical", "Technical Agent", "Technical and candlestick analysis"),
            ("decision", "Decision Agent", "Decision synthesis"),
            ("reflection", "Reflector Agent", "Trading outcome reflection"),
            ("forecast", "Forecast Agent", "Price forecasting"),
        ]
        agents = []
        for attr, label, description in names:
            item = _agent_health(attr, latest, engine, warning, source)
            item["name"] = label
            item["description"] = description
            item["last_cycle_at"] = last_cycle
            item["last_cycle_age_seconds"] = age
            agents.append(item)
        counts = {state: sum(1 for a in agents if a["status"] == state) for state in ("ON", "ARMED", "DEGRADED", "BROKE", "OFF")}
        return {"agents": agents, "counts": counts, "on_count": counts["ON"], "total_agents": len(agents), "orchestrator": "ON" if engine.get("running") and not warning else "DEGRADED" if engine.get("running") else "OFF", "executor": "ON" if engine.get("running") else "OFF", "engine_running": bool(engine.get("running")), "engine_mode": engine.get("mode"), "engine_started_at": engine.get("started_at"), "last_cycle_at": last_cycle, "last_cycle_age_seconds": age, "ai_source": source or None, "ai_warning": warning or None, "timestamp": now.isoformat()}
    except HTTPException: raise
    except Exception:
        logger.exception("Error getting agents status")
        raise HTTPException(status_code=500, detail="Failed to get agents status")


@router.get("/positions")
async def get_positions(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        authenticate(credentials); positions = paper_trading.get_positions()
        return {"positions": positions, "total_positions": len(positions), "timestamp": datetime.now(timezone.utc).isoformat()}
    except HTTPException: raise
    except Exception:
        logger.exception("Error getting positions"); raise HTTPException(status_code=500, detail="Failed to get positions")


@router.get("/trades")
async def get_trades(limit: int = 50, credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        authenticate(credentials); limit = max(1, min(limit, 500)); trades = db.get_trades(limit=limit)
        return {"trades": trades, "total_trades": len(trades), "limit": limit, "timestamp": datetime.now(timezone.utc).isoformat()}
    except HTTPException: raise
    except Exception:
        logger.exception("Error getting trades"); raise HTTPException(status_code=500, detail="Failed to get trades")


@router.get("/performance")
async def get_performance(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        authenticate(credentials); trades = db.get_trades(limit=1000); pnls = []
        for trade in trades:
            try: pnls.append(float(trade.get("pnl", 0) or 0))
            except (TypeError, ValueError): continue
        total_trades = len(pnls); winning_trades = sum(1 for p in pnls if p > 0); losing_trades = sum(1 for p in pnls if p < 0); total_pnl = sum(pnls); average_pnl = total_pnl / total_trades if total_trades else 0.0; win_rate = winning_trades / total_trades if total_trades else 0.0; gross_profit = sum(p for p in pnls if p > 0); gross_loss = abs(sum(p for p in pnls if p < 0)); profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
        portfolio_value = None; balance = None; total_return = None
        try:
            portfolio_value = paper_trading.get_portfolio_value(); balance = paper_trading.balance; initial_balance = paper_trading.initial_balance
            if initial_balance: total_return = ((portfolio_value - initial_balance) / initial_balance) * 100
        except Exception as exc: logger.warning("Paper performance unavailable: %s", exc)
        return {"performance": {"total_trades": total_trades, "winning_trades": winning_trades, "losing_trades": losing_trades, "win_rate": win_rate, "total_pnl": total_pnl, "average_pnl": average_pnl, "gross_profit": gross_profit, "gross_loss": gross_loss, "profit_factor": profit_factor, "balance": balance, "portfolio_value": portfolio_value, "total_return": total_return}, "timestamp": datetime.now(timezone.utc).isoformat()}
    except HTTPException: raise
    except Exception:
        logger.exception("Error getting performance"); raise HTTPException(status_code=500, detail="Failed to get performance")


@router.get("/recent-decision")
async def get_recent_decision(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        authenticate(credentials); latest = get_last_orchestrator_result()
        if latest is not None:
            return {"decision": {"symbol": latest.symbol, "action": latest.final_action, "confidence": latest.final_confidence, "position_size": latest.position_size, "timestamp": latest.timestamp.isoformat(), "cycle_status": latest.cycle_status, "hold_reason": latest.hold_reason, "execution_reason": latest.execution_reason}, "votes": latest.agent_votes, "market_scores": latest.market_scores, "summary": latest.summary, "conflict_review": latest.conflict_review, "signals": latest.signals}
        decisions = db.get_decisions(limit=1)
        if decisions:
            decision = decisions[0]
            return {"decision": {"symbol": decision.get("symbol"), "action": decision.get("action"), "confidence": decision.get("confidence"), "timestamp": decision.get("created_at"), "cycle_status": decision.get("cycle_status"), "hold_reason": decision.get("hold_reason"), "execution_reason": decision.get("execution_reason")}, "votes": decision.get("agent_votes", {}), "market_scores": {}, "summary": decision.get("reasoning"), "conflict_review": decision.get("conflict_review", {}), "signals": decision.get("signals", [])}
        return {"decision": None, "message": "No decisions made yet"}
    except HTTPException: raise
    except Exception:
        logger.exception("Error getting recent decision"); raise HTTPException(status_code=500, detail="Failed to get recent decision")


@router.post("/analyze")
async def analyze_symbol(symbol: str = "BTC-USD", credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        authenticate(credentials); symbol = symbol.upper().strip()
        if not symbol: raise HTTPException(status_code=400, detail="Symbol cannot be empty")
        result = await orchestrator.analyze(symbol)
        return {"symbol": result.symbol, "action": result.final_action, "confidence": result.final_confidence, "position_size": result.position_size, "votes": result.agent_votes, "market_scores": result.market_scores, "summary": result.summary, "timestamp": result.timestamp.isoformat(), "cycle_status": result.cycle_status, "hold_reason": result.hold_reason, "execution_reason": result.execution_reason, "conflict_review": result.conflict_review, "signals": result.signals}
    except HTTPException: raise
    except Exception as exc:
        logger.exception("Error analyzing symbol %s", symbol); raise HTTPException(status_code=500, detail=f"Failed to analyze {symbol}: {exc}")
