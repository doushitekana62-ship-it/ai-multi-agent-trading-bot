"""Runtime exchange configuration endpoints.

Credentials are accepted only over the authenticated dashboard API and are
stored encrypted on the server. Secrets are never returned to the client.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from backend.core.security import verify_token
from backend.core.exchange_credentials import ExchangeCredentialStore
from core.market_data_adapter import get_market_data_adapter
from backend.routes.dashboard import executor

router = APIRouter()
security = HTTPBearer()


class ExchangeConfigRequest(BaseModel):
    exchange: str = Field(default="indodax")
    api_key: str = Field(min_length=1)
    api_secret: str = Field(min_length=1)
    enable_trading: bool = False


def authenticate(credentials: HTTPAuthorizationCredentials):
    payload = verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return payload


@router.get("/config")
async def get_config(credentials: HTTPAuthorizationCredentials = Depends(security)):
    authenticate(credentials)
    store = ExchangeCredentialStore()
    return {**store.public_status(), "runtime_exchange_mode": executor.exchange_mode}


@router.post("/config")
async def configure(config: ExchangeConfigRequest, credentials: HTTPAuthorizationCredentials = Depends(security)):
    authenticate(credentials)
    exchange = config.exchange.lower().strip()
    if exchange == "paper":
        executor.configure_exchange("paper")
        get_market_data_adapter({"exchange_type": "paper"})
        return {"success": True, "exchange": "paper", "trading_enabled": False}
    if exchange != "indodax":
        raise HTTPException(status_code=400, detail="Only paper and Indodax are supported by the dashboard flow")

    try:
        from exchange_integration.indodax_bridge import IndodaxBridge
        data = {"api_key": config.api_key, "api_secret": config.api_secret, "enable_trading": config.enable_trading}
        # Validate private API access before saving anything.
        IndodaxBridge({"api_key": config.api_key, "secret": config.api_secret, "enable_trading": config.enable_trading}).test_connection()
        ExchangeCredentialStore().save("indodax", config.api_key, config.api_secret, config.enable_trading)
        executor.configure_exchange("indodax", data)
        get_market_data_adapter({"exchange_type": "indodax", "indodax": data})
        return {"success": True, "exchange": "indodax", "trading_enabled": config.enable_trading, "api_key_last4": config.api_key[-4:]}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Indodax connection failed: {exc}")


@router.post("/test")
async def test(credentials: HTTPAuthorizationCredentials = Depends(security)):
    authenticate(credentials)
    saved = ExchangeCredentialStore().load()
    if not saved:
        raise HTTPException(status_code=404, detail="No exchange credentials configured")
    if saved.get("exchange") == "indodax":
        from exchange_integration.indodax_bridge import IndodaxBridge
        return IndodaxBridge({"api_key": saved["api_key"], "secret": saved["api_secret"], "enable_trading": saved.get("enable_trading", False)}).test_connection()
    return {"connected": True, "exchange": saved.get("exchange")}
