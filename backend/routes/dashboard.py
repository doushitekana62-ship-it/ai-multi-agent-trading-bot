"""
Dashboard Routes
Real-time dashboard data
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.core.security import verify_token
from backend.core.database import db

from core.orchestrator import Orchestrator
from core.executor import Executor

try:
    from exchange_integration.paper_trading import PaperTrading
except ImportError:
    PaperTrading = None


# ============================================================
# LOGGING
# ============================================================

logger = logging.getLogger(__name__)


# ============================================================
# ROUTER
# ============================================================

router = APIRouter()
security = HTTPBearer()


# ============================================================
# CORE COMPONENTS
# ============================================================

orchestrator = Orchestrator()
executor = Executor()

# Paper trading optional
paper_trading = PaperTrading() if PaperTrading else None


# ============================================================
# AUTH HELPER
# ============================================================

def authenticate(credentials: HTTPAuthorizationCredentials):
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


# ============================================================
# DASHBOARD STATUS
# ============================================================

@router.get("/status")
async def get_status(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get overall dashboard/system status.
    """

    try:

        authenticate(credentials)

        # ----------------------------------------------------
        # Get trades from Supabase
        # ----------------------------------------------------

        trades = db.get_trades(limit=1000)

        # ----------------------------------------------------
        # Calculate PnL
        # ----------------------------------------------------

        total_pnl = 0.0

        for trade in trades:

            pnl = trade.get("pnl")

            if pnl is not None:
                try:
                    total_pnl += float(pnl)
                except (TypeError, ValueError):
                    pass

        # ----------------------------------------------------
        # Trading statistics
        # ----------------------------------------------------

        total_trades = len(trades)

        winning_trades = sum(
            1
            for trade in trades
            if float(trade.get("pnl", 0) or 0) > 0
        )

        losing_trades = sum(
            1
            for trade in trades
            if float(trade.get("pnl", 0) or 0) < 0
        )

        # ----------------------------------------------------
        # Win rate
        # ----------------------------------------------------

        win_rate = (
            winning_trades / total_trades
            if total_trades > 0
            else 0
        )

        # ----------------------------------------------------
        # Portfolio information
        # ----------------------------------------------------

        portfolio_value = None
        balance = None

        if paper_trading:

            try:
                portfolio_value = paper_trading.get_portfolio_value()
                balance = paper_trading.balance

            except Exception as e:
                logger.warning(
                    f"Paper trading portfolio unavailable: {e}"
                )

        # ----------------------------------------------------
        # Database status
        # ----------------------------------------------------

        database_status = db.is_connected()

        # ----------------------------------------------------
        # Response
        # ----------------------------------------------------

        return {

            "status": "running",

            "timestamp": datetime.now().isoformat(),

            "database": {
                "connected": database_status
            },

            "trading": {

                "exchange_mode": getattr(
                    executor,
                    "exchange_mode",
                    "paper"
                ),

                "active_positions": len(
                    getattr(
                        executor,
                        "active_positions",
                        {}
                    )
                ),

                "total_trades": total_trades,

                "winning_trades": winning_trades,

                "losing_trades": losing_trades,

                "win_rate": win_rate,

                "total_pnl": total_pnl,

                "daily_pnl": getattr(
                    executor,
                    "daily_pnl",
                    0
                ),

                "daily_trades": getattr(
                    executor,
                    "daily_trades",
                    0
                )
            },

            "portfolio": {

                "value": portfolio_value,

                "balance": balance
            }

        }

    except HTTPException:
        raise

    except Exception as e:

        logger.exception(
            "Error getting dashboard status"
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get dashboard status"
        )


# ============================================================
# AGENTS STATUS
# ============================================================

@router.get("/agents")
async def get_agents_status(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get status of all AI agents.
    """

    try:

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
                    "description": "Analisis hasil trading"
                },

                {
                    "name": "Forecast Agent",
                    "status": "active",
                    "description": "Prediksi pergerakan harga"
                }

            ],

            "orchestrator": "running",

            "executor": "running",

            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise

    except Exception as e:

        logger.exception(
            "Error getting agents status"
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get agents status"
        )


# ============================================================
# POSITIONS
# ============================================================

@router.get("/positions")
async def get_positions(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get current paper trading positions.
    """

    try:

        authenticate(credentials)

        positions = []

        if paper_trading:

            try:
                positions = paper_trading.get_positions()

            except Exception as e:

                logger.warning(
                    f"Unable to get paper positions: {e}"
                )

        return {

            "positions": positions,

            "total_positions": len(positions),

            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise

    except Exception as e:

        logger.exception(
            "Error getting positions"
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get positions"
        )


# ============================================================
# TRADES
# ============================================================

@router.get("/trades")
async def get_trades(
    limit: int = 50,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get recent trades from Supabase.
    """

    try:

        authenticate(credentials)

        # Prevent unreasonable requests
        limit = max(1, min(limit, 500))

        trades = db.get_trades(limit=limit)

        return {

            "trades": trades,

            "total_trades": len(trades),

            "limit": limit,

            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise

    except Exception as e:

        logger.exception(
            "Error getting trades"
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get trades"
        )


# ============================================================
# PERFORMANCE
# ============================================================

@router.get("/performance")
async def get_performance(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get trading performance from Supabase.
    """

    try:

        authenticate(credentials)

        trades = db.get_trades(limit=1000)

        # ----------------------------------------------------
        # PnL
        # ----------------------------------------------------

        pnls = []

        for trade in trades:

            try:

                pnl = float(
                    trade.get("pnl", 0) or 0
                )

                pnls.append(pnl)

            except (TypeError, ValueError):

                continue

        # ----------------------------------------------------
        # Statistics
        # ----------------------------------------------------

        total_trades = len(pnls)

        winning_trades = sum(
            1 for pnl in pnls if pnl > 0
        )

        losing_trades = sum(
            1 for pnl in pnls if pnl < 0
        )

        total_pnl = sum(pnls)

        average_pnl = (
            total_pnl / total_trades
            if total_trades > 0
            else 0
        )

        win_rate = (
            winning_trades / total_trades
            if total_trades > 0
            else 0
        )

        gross_profit = sum(
            pnl for pnl in pnls
            if pnl > 0
        )

        gross_loss = abs(
            sum(
                pnl for pnl in pnls
                if pnl < 0
            )
        )

        profit_factor = (
            gross_profit / gross_loss
            if gross_loss > 0
            else None
        )

        # ----------------------------------------------------
        # Paper portfolio
        # ----------------------------------------------------

        portfolio_value = None
        balance = None
        total_return = None

        if paper_trading:

            try:

                portfolio_value = (
                    paper_trading.get_portfolio_value()
                )

                balance = paper_trading.balance

                initial_balance = (
                    paper_trading.initial_balance
                )

                if initial_balance:

                    total_return = (
                        (
                            portfolio_value
                            - initial_balance
                        )
                        / initial_balance
                    ) * 100

            except Exception as e:

                logger.warning(
                    f"Paper performance unavailable: {e}"
                )

        # ----------------------------------------------------
        # Response
        # ----------------------------------------------------

        return {

            "performance": {

                "total_trades": total_trades,

                "winning_trades": winning_trades,

                "losing_trades": losing_trades,

                "win_rate": win_rate,

                "total_pnl": total_pnl,

                "average_pnl": average_pnl,

                "gross_profit": gross_profit,

                "gross_loss": gross_loss,

                "profit_factor": profit_factor,

                "balance": balance,

                "portfolio_value": portfolio_value,

                "total_return": total_return
            },

            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise

    except Exception as e:

        logger.exception(
            "Error getting performance"
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get performance"
        )


# ============================================================
# RECENT DECISION
# ============================================================

@router.get("/recent-decision")
async def get_recent_decision(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get the most recent AI trading decision.
    """

    try:

        authenticate(credentials)

        # ----------------------------------------------------
        # First try orchestrator history
        # ----------------------------------------------------

        try:

            history = orchestrator.get_history(1)

        except Exception as e:

            logger.warning(
                f"Could not read orchestrator history: {e}"
            )

            history = []

        if history:

            latest = history[-1]

            return {

                "decision": {

                    "symbol": latest.symbol,

                    "action": latest.final_action,

                    "confidence": latest.final_confidence,

                    "position_size": latest.position_size,

                    "timestamp": latest.timestamp.isoformat()
                },

                "votes": latest.agent_votes,

                "summary": latest.summary
            }

        # ----------------------------------------------------
        # Fallback to Supabase
        # ----------------------------------------------------

        decisions = db.get_decisions(limit=1)

        if decisions:

            decision = decisions[0]

            return {

                "decision": {

                    "symbol": decision.get("symbol"),

                    "action": decision.get("action"),

                    "confidence": decision.get("confidence"),

                    "timestamp": decision.get("created_at")
                },

                "votes": decision.get(
                    "agent_votes",
                    {}
                ),

                "summary": decision.get(
                    "reasoning"
                )
            }

        return {

            "decision": None,

            "message": "No decisions made yet"
        }

    except HTTPException:
        raise

    except Exception as e:

        logger.exception(
            "Error getting recent decision"
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get recent decision"
        )


# ============================================================
# ANALYZE SYMBOL
# ============================================================

@router.post("/analyze")
async def analyze_symbol(
    symbol: str = "BTC-USD",
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Force AI analysis on a symbol.
    """

    try:

        authenticate(credentials)

        symbol = symbol.upper().strip()

        if not symbol:

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Symbol cannot be empty"
            )

        # IMPORTANT:
        # This endpoint is already async.
        # Do NOT use asyncio.run() here.

        result = await orchestrator.analyze(symbol)

        return {

            "symbol": result.symbol,

            "action": result.final_action,

            "confidence": result.final_confidence,

            "position_size": result.position_size,

            "votes": result.agent_votes,

            "summary": result.summary,

            "timestamp": result.timestamp.isoformat()
        }

    except HTTPException:
        raise

    except Exception as e:

        logger.exception(
            f"Error analyzing symbol {symbol}"
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze {symbol}: {str(e)}"
        )
