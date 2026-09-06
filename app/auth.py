from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

bearer = HTTPBearer(auto_error=False)


def _token(credentials: HTTPAuthorizationCredentials | None) -> str:
    if not credentials:
        raise HTTPException(status_code=401, detail="Dashboard token required")
    if not settings.dashboard_token:
        raise HTTPException(status_code=503, detail="DASHBOARD_TOKEN is not configured")
    if credentials.credentials != settings.dashboard_token:
        raise HTTPException(status_code=401, detail="Invalid dashboard token")
    return credentials.credentials


async def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    _token(credentials)
    return {"id": "dashboard-owner"}


async def current_token(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
    return _token(credentials)
