from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.config import settings

bearer = HTTPBearer(auto_error=False)

def _auth_client():
    from supabase import create_client
    key = settings.supabase_secret_key or settings.supabase_service_role_key
    if not settings.supabase_url or not key:
        raise RuntimeError("Supabase server credentials are not configured")
    return create_client(settings.supabase_url, key)

def require_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    try:
        user = _auth_client().auth.get_user(credentials.credentials).user
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session") from exc
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    return {"id": str(user.id), "email": user.email, "user": user}
