import httpx
from typing import Any
from .config import settings

class SupabaseClient:
    def __init__(self): self.url=settings.supabase_url.rstrip('/')
    def _headers(self,token=None):
        key=settings.supabase_anon_key or settings.supabase_service_role_key
        h={'apikey':key}
        if token: h['Authorization']=f'Bearer {token}'
        elif settings.supabase_service_role_key: h['Authorization']=f'Bearer {settings.supabase_service_role_key}'
        return h
    async def health(self):
        if not self.url or not (settings.supabase_anon_key or settings.supabase_service_role_key): return {'configured':False}
        async with httpx.AsyncClient(timeout=10) as c:
            r=await c.get(f'{self.url}/rest/v1/',headers=self._headers()); r.raise_for_status(); return {'configured':True,'status':r.status_code}
    async def user(self,access_token):
        async with httpx.AsyncClient(timeout=10) as c:
            r=await c.get(f'{self.url}/auth/v1/user',headers=self._headers(access_token)); r.raise_for_status(); return r.json()
    async def select(self,table,access_token,params=None):
        async with httpx.AsyncClient(timeout=10) as c:
            r=await c.get(f'{self.url}/rest/v1/{table}',headers=self._headers(access_token),params=params or {'select':'*'}); r.raise_for_status(); return r.json()
