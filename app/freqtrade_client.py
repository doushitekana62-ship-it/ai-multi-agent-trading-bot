import httpx
from typing import Any
from ..config import settings

class FreqtradeClient:
    def __init__(self) -> None:
        self.base_url = settings.freqtrade_url.rstrip("/")
        self.token: str | None = None

    async def login(self) -> str:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{self.base_url}/token/login",
                data={"username": settings.freqtrade_username, "password": settings.freqtrade_password},
            )
            response.raise_for_status()
            self.token = response.json()["access_token"]
            return self.token

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        async with httpx.AsyncClient(timeout=15) as client:
            headers = kwargs.pop("headers", {})
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            response = await client.request(method, f"{self.base_url}/{path.lstrip('/')}", headers=headers, **kwargs)
            if response.status_code == 401 and settings.freqtrade_username:
                await self.login()
                headers["Authorization"] = f"Bearer {self.token}"
                response = await client.request(method, f"{self.base_url}/{path.lstrip('/')}", headers=headers, **kwargs)
            response.raise_for_status()
            return response.json()

    async def ping(self) -> Any:
        return await self.request("GET", "/ping")

    async def status(self) -> Any:
        return await self.request("GET", "/status")

    async def balance(self) -> Any:
        return await self.request("GET", "/balance")

    async def trades(self) -> Any:
        return await self.request("GET", "/trades")

    async def start(self) -> Any:
        return await self.request("POST", "/start")

    async def stop(self) -> Any:
        return await self.request("POST", "/stop")
