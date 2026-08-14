"""
Dashboard Routes

Menyediakan:
- System status
- Agent status
- Current positions
- Recent trades
- Performance
- Recent AI decision
- Symbol analysis
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import (
    APIRouter,
    HTTPException,
    status,
    Depends,
    Query
)

from fastapi.security import (
    HTTPBearer,
    HTTPAuthorizationCredentials
)

from backend.core.security import verify_token
from backend.core.database import get_supabase

from core.orchestrator import Orchestrator
from core.executor import Executor

logger = logging.getLogger(__name__)

router = APIRouter()
security = HTTPBearer()

# Supabase
supabase = get_supabase()

# AI components
orchestrator = Orchestrator()
executor = Executor()


# =========================================================
# AUTH HELPER
# =========================================================

def authenticate(
    credentials: HTTPAuthorizationCredentials
):
    """
    Verify JWT token.
    """

    token = credentials.credentials

    payload = verify_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    return payload


# =========================================================
# ROOT DASHBOARD STATUS
# =========================================================

@router.get("/status")
async def get_status(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get dashboard/system status.
    """

    authenticate(credentials)

    try:

        # Get latest trades
        trades_response = (
            supabase
            .table("trades")
            .select("*")
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )

        trades = trades_response.data or []

        total_trades = len(trades)

        # Calculate realized PnL
        total_pnl = sum(
            float(trade.get("pnl") or 0)
            for trade in trades
        )

        # Get latest decisions
        decisions_response = (
            supabase
            .table("decisions")
            .select("*")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        latest_decision = (
            decisions_response.data[0]
            if decisions_response.data
            else None
        )

        return {
            "status": "running",
            "timestamp": datetime.now().isoformat(),

            "exchange_mode": getattr(
                executor,
                "exchange_mode",
                "paper"
            ),

            "total_trades": total_trades,

            "total_pnl": total_pnl,

            "latest_decision": latest_decision
        }

    except Exception as e:

        logger.exception(
            "Error getting dashboard status"
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to get dashboard status"
        )


# =========================================================
# AGENTS
# =========================================================

@router.get("/agents")
async def get_agents_status(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get AI agents status.
    """

    authenticate(credentials)

    return {
        "agents": [
            {
                "name": "Sentiment Agent",
                "status": "active",
                "description": "Analisis sentimen pasar"
            },
            {
                "name": "Technical Agent",
                "status": "active",
                "description": "Analisis teknikal dan candlestick"
            },
            {
                "name": "Decision Agent",
                "status": "active",
                "description": "Pengambil keputusan trading"
            },
            {
                "name": "Reflector Agent",
                "status": "active",
                "description": "Evaluasi hasil trading"
            },
            {
                "name": "Forecast Agent",
                "status": "active",
                "description": "Prediksi pergerakan harga"
            }
        ],

        "orchestrator": "running",
        "executor": "running"
    }


# =========================================================
# POSITIONS
# =========================================================

@router.get("/positions")
async def get_positions(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get current positions.

    Untuk sementara posisi diambil dari executor.
    """

    authenticate(credentials)

    try:

        active_positions = getattr(
            executor,
            "active_positions",
            {}
        )

        positions = []

        if isinstance(active_positions, dict):

            for symbol, position in active_positions.items():

                if isinstance(position, dict):

                    positions.append({
                        "symbol": symbol,
                        **position
                    })

                else:

                    positions.append({
                        "symbol": symbol,
                        "position": str(position)
                    })

        elif isinstance(active_positions, list):

            positions = active_positions

        return {
            "positions": positions,
            "total_positions": len(positions),
            "timestamp": datetime.now().isoformat()
        }

    except Exception:

        logger.exception(
            "Error getting positions"
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to get positions"
        )


# =========================================================
# TRADES
# =========================================================

@router.get("/trades")
async def get_trades(
    limit: int = Query(
        default=50,
        ge=1,
        le=500
    ),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get recent trades from Supabase.
    """

    authenticate(credentials)

    try:

        response = (
            supabase
            .table("trades")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        trades = response.data or []

        return {
            "trades": trades,
            "total_returned": len(trades),
            "limit": limit,
            "timestamp": datetime.now().isoformat()
        }

    except Exception:

        logger.exception(
            "Error getting trades"
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to get trades"
        )


# =========================================================
# PERFORMANCE
# =========================================================

@router.get("/performance")
async def get_performance(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get trading performance from Supabase.
    """

    authenticate(credentials)

    try:

        response = (
            supabase
            .table("trades")
            .select("pnl")
            .execute()
        )

        trades = response.data or []

        pnls = [
            float(t.get("pnl") or 0)
            for t in trades
        ]

        total_trades = len(pnls)

        winning_trades = sum(
            1 for pnl in pnls
            if pnl > 0
        )

        losing_trades = sum(
            1 for pnl in pnls
            if pnl < 0
        )

        total_pnl = sum(pnls)

        win_rate = (
            winning_trades / total_trades
            if total_trades > 0
            else 0
        )

        return {
            "performance": {
                "total_trades": total_trades,

                "winning_trades": winning_trades,

                "losing_trades": losing_trades,

                "win_rate": win_rate,

                "total_pnl": total_pnl
            },

            "timestamp": datetime.now().isoformat()
        }

    except Exception:

        logger.exception(
            "Error getting performance"
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to get performance"
        )


# =========================================================
# RECENT AI DECISION
# =========================================================

@router.get("/recent-decision")
async def get_recent_decision(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get latest AI trading decision.
    """

    authenticate(credentials)

    try:

        response = (
            supabase
            .table("decisions")
            .select("*")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        decisions = response.data or []

        if not decisions:

            return {
                "decision": None,
                "message": "No decisions made yet"
            }

        latest = decisions[0]

        return {
            "decision": {
                "id": latest.get("id"),
                "symbol": latest.get("symbol"),
                "action": latest.get("action"),
                "confidence": latest.get("confidence"),
                "reasoning": latest.get("reasoning"),
                "agent_votes": latest.get("agent_votes"),
                "created_at": latest.get("created_at")
            }
        }

    except Exception:

        logger.exception(
            "Error getting recent decision"
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to get recent decision"
        )


# =========================================================
# DECISIONS HISTORY
# =========================================================

@router.get("/decisions")
async def get_decisions(
    limit: int = Query(
        default=50,
        ge=1,
        le=500
    ),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get AI decision history.
    """

    authenticate(credentials)

    try:

        response = (
            supabase
            .table("decisions")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        decisions = response.data or []

        return {
            "decisions": decisions,
            "total_returned": len(decisions),
            "limit": limit,
            "timestamp": datetime.now().isoformat()
        }

    except Exception:

        logger.exception(
            "Error getting decisions"
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to get decisions"
        )


# =========================================================
# ANALYZE SYMBOL
# =========================================================

@router.post("/analyze")
async def analyze_symbol(
    symbol: str = "BTC-USD",
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Force AI analysis for a symbol.
    """

    authenticate(credentials)

    try:

        result = await orchestrator.analyze(symbol)

        # Save AI decision to Supabase
        supabase.table("decisions").insert({
            "symbol": result.symbol,
            "action": result.final_action,
            "confidence": result.final_confidence,
            "reasoning": result.summary,
            "agent_votes": result.agent_votes
        }).execute()

        return {
            "symbol": result.symbol,
            "action": result.final_action,
            "confidence": result.final_confidence,
            "position_size": result.position_size,
            "votes": result.agent_votes,
            "summary": result.summary,
            "timestamp": result.timestamp.isoformat()
        }

    except Exception as e:

        logger.exception(
            f"Error analyzing {symbol}"
        )

        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze {symbol}: {str(e)}"
        )
