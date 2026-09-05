from __future__ import annotations

from typing import Any

import httpx

from .config import settings


class SupabaseClient:
    def __init__(self) -> None:
        self.url = settings.supabase_url.rstrip("/")

    def _headers(self, token: str | None = None, service_role: bool = False) -> dict[str, str]:
        if service_role:
            key = settings.supabase_service_role_key
            if not key:
                raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is required for server-side writes")
        else:
            key = settings.supabase_anon_key or settings.supabase_service_role_key
        headers = {"apikey": key}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif service_role and key:
            headers["Authorization"] = f"Bearer {key}"
        elif settings.supabase_service_role_key:
            headers["Authorization"] = f"Bearer {settings.supabase_service_role_key}"
        return headers

    async def health(self) -> dict[str, Any]:
        if not self.url or not (settings.supabase_anon_key or settings.supabase_service_role_key):
            return {"configured": False}
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{self.url}/rest/v1/", headers=self._headers())
            response.raise_for_status()
            return {"configured": True, "status": response.status_code}

    async def user(self, access_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{self.url}/auth/v1/user", headers=self._headers(access_token)
            )
            response.raise_for_status()
            return response.json()

    async def select(
        self, table: str, access_token: str, params: dict[str, Any] | None = None
    ) -> Any:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{self.url}/rest/v1/{table}",
                headers=self._headers(access_token),
                params=params or {"select": "*"},
            )
            response.raise_for_status()
            return response.json()

    async def upsert(
        self,
        table: str,
        values: dict[str, Any] | list[dict[str, Any]],
        on_conflict: str | None = None,
    ) -> Any:
        params = {"on_conflict": on_conflict} if on_conflict else None
        headers = self._headers(service_role=True)
        headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{self.url}/rest/v1/{table}",
                headers=headers,
                params=params,
                json=values,
            )
            response.raise_for_status()
            return response.json() if response.content else None
