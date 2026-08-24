"""Dashboard routes and runtime exchange configuration."""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from backend.core.security import verify_token
from backend.core.database import db
from backend.core.exchange_credentials import ExchangeCredentialStore
from core.orchestrator import Orchestrator
from core.executor import Executor
from core.market_data_adapter import get_market_data_adapter

try:
    from exchange_integration.paper_trading import PaperTrading
except ImportError:
    PaperTrading = None

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer()
orchestrator = Orchestrator()
executor = Executor()
paper_trading = executor.paper_trading


def authenticate(credentials: HTTPAuthorizationCredentials):
    payload = verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return payload


class ExchangeConfigRequest(BaseModel):
    exchange: str = Field(default="indodax")
    api_key: str = Field(min_length=1)
    api_secret: str = Field(min_length=1)
    enable_trading: bool = False


@router.get("/exchange")
async def get_exchange_config(credentials: HTTPAuthorizationCredentials = Depends(security)):
    authenticate(credentials)
    try:
        store = ExchangeCredentialStore()
        saved = store.public_status()
        return {**saved, "runtime_exchange_mode": executor.exchange_mode}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/exchange")
async def configure_exchange(config: ExchangeConfigRequest, credentials: HTTPAuthorizationCredentials = Depends(security)):
    authenticate(credentials)
    exchange = config.exchange.lower().strip()
    if exchange not in {"paper", "indodax", "alpaca"}:
        raise HTTPException(status_code=400, detail="Unsupported exchange")
    if exchange != "indodax":
        executor.configure_exchange(exchange)
        get_market_data_adapter({"exchange_type": exchange})
        return {"success": True, "exchange": exchange, "trading_enabled": False}
    try:
        # Verify the public/private credentials before persisting them.
        from exchange_integration.indodax_bridge import IndodaxBridge
        bridge = IndodaxBridge({"api_key": config.api_key, "secret": config.api_secret, "enable_trading": config.enable_trading})
        bridge.test_connection()
        store = ExchangeCredentialStore()
        store.save("indodax", config.api_key, config.api_secret, config.enable_trading)
        credentials_data = {
            "api_key": config.api_key,
            "api_secret": config.api_secret,
            "enable_trading": config.enable_trading,
        }
        executor.configure_exchange("indodax", credentials_data)
        get_market_data_adapter({"exchange_type": "indodax", "indodax": credentials_data})
        return {"success": True, "exchange": "indodax", "trading_enabled": config.enable_trading, "api_key_last4": config.api_key[-4:]}
    except Exception as exc:
        logger.exception("Indodax configuration failed")
        raise HTTPException(status_code=400, detail=f"Indodax connection failed: {exc}")


@router.post("/exchange/test")
async def test_exchange(credentials: HTTPAuthorizationCredentials = Depends(security)):
    authenticate(credentials)
    try:
        store = ExchangeCredentialStore()
        saved = store.load()
        if not saved:
            raise HTTPException(status_code=404, detail="No exchange credentials configured")
        if saved.get("exchange") == "indodax":
            from exchange_integration.indodax_bridge import IndodaxBridge
            bridge = IndodaxBridge({"api_key": saved["api_key"], "secret": saved["api_secret"], "enable_trading": saved.get("enable_trading", False)})
            return bridge.test_connection()
        return {"connected": True, "exchange": saved.get("exchange")}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Exchange test failed: {exc}")


@router.get("/status")
async def get_status(credentials: HTTPAuthorizationCredentials = Depends(security)):
    authenticate(credentials)
    try:
        trades = db.get_trades(limit=1000)
        pnls = [float(t.get("pnl", 0) or 0) for t in trades if t.get("pnl") is not None]
        winning = sum(1 for p in pnls if p > 0)
        losing = sum(1 for p in pnls if p < 0)
        return {
            "status": "running", "timestamp": datetime.now().isoformat(),
            "database": {"connected": db.is_connected()},
            "trading": {"exchange_mode": executor.exchange_mode, "active_positions": len(executor.active_positions),
                        "total_trades": len(trades), "winning_trades": winning, "losing_trades": losing,
                        "win_rate": winning / len(trades) if trades else 0, "total_pnl": sum(pnls),
                        "daily_pnl": executor.daily_pnl, "daily_trades": executor.daily_trades},
            "portfolio": {"value": paper_trading.get_portfolio_value(), "balance": paper_trading.balance} if executor.exchange_mode == "paper" else {"value": None, "balance": None},
        }
    except Exception as exc:
        logger.exception("Error getting dashboard status")
        raise HTTPException(status_code=500, detail="Failed to get dashboard status")


@router.get("/agents")
async def get_agents_status(credentials: HTTPAuthorizationCredentials = Depends(security)):
    authenticate(credentials)
    return {"agents": [
        {"name": "Sentiment Agent", "status": "active"},
        {"name": "Technical Agent", "status": "active"},
        {"name": "Decision Agent", "status": "active"},
        {"name": "Reflector Agent", "status": "active"},
        {"name": "Forecast Agent", "status": "active"}],
        "orchestrator": "running", "executor": "running", "timestamp": datetime.now().isoformat()}


@router.get("/positions")
async def get_positions(credentials: HTTPAuthorizationCredentials = Depends(security)):
    authenticate(credentials)
    positions = paper_trading.get_positions() if executor.exchange_mode == "paper" else list(executor.active_positions.values())
    return {"positions": positions, "total_positions": len(positions), "timestamp": datetime.now().isoformat()}


@router.get("/trades")
async def get_trades(limit: int = 50, credentials: HTTPAuthorizationCredentials = Depends(security)):
    authenticate(credentials)
    limit = max(1, min(limit, 500))
    trades = db.get_trades(limit=limit)
    return {"trades": trades, "total_trades": len(trades), "limit": limit, "timestamp": datetime.now().isoformat()}


@router.get("/performance")
async def get_performance(credentials: HTTPAuthorizationCredentials = Depends(security)):
    authenticate(credentials)
    trades = db.get_trades(limit=1000)
    pnls = [float(t.get("pnl", 0) or 0) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    return {"total_trades": len(pnls), "winning_trades": len(wins), "losing_trades": len(losses),
            "win_rate": len(wins) / len(pnls) if pnls else 0, "total_pnl": sum(pnls),
            "average_pnl": sum(pnls) / len(pnls) if pnls else 0,
            "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
            "portfolio_value": paper_trading.get_portfolio_value() if executor.exchange_mode == "paper" else None}
