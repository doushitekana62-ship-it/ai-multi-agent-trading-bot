from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .supabase_client import SupabaseClient

bearer = HTTPBearer(auto_error=False)
supabase = SupabaseClient()

async def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if not credentials: raise HTTPException(status_code=401, detail="Authentication required")
    try: return await supabase.user(credentials.credentials)
    except Exception as exc: raise HTTPException(status_code=401, detail="Invalid Supabase session") from exc

async def current_token(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
    if not credentials: raise HTTPException(status_code=401, detail="Authentication required")
    return credentials.credentials
