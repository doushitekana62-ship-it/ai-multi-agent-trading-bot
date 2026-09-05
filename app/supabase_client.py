import httpx
from typing import Any
from ..config import settings

class SupabaseClient:
    def __init__(self) -> None:
        self.url = settings.supabase_url.rstrip("/")
        self.key = settings.supabase_service_role_key

    async def health(self) -> dict[str, Any]:
        if not self.url or not self.key:
            return {"configured": False}
        headers = {"apikey": self.key, "Authorization": f"Bearer {self.key}"}
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{self.url}/rest/v1/", headers=headers)
            response.raise_for_status()
            return {"configured": True, "status": response.status_code}
