import hashlib
import hmac
import time
from urllib.parse import urlencode
import httpx
from app.config import settings

class IndodaxClient:
    def __init__(self):
        self.public_url = settings.indodax_public_url.rstrip("/")
        self.private_url = settings.indodax_private_url.rstrip("/")

    def get_pairs(self):
        r = httpx.get(f"{self.public_url}/pairs", timeout=10)
        r.raise_for_status()
        return r.json()

    def get_ticker(self, symbol):
        r = httpx.get(f"{self.public_url}/ticker/{symbol.lower()}", timeout=10)
        r.raise_for_status()
        ticker = r.json().get("ticker", r.json())
        return {"symbol": symbol.lower(), "price": float(ticker.get("last") or ticker.get("last_price") or 0),
                "high": float(ticker.get("high") or 0), "low": float(ticker.get("low") or 0), "timestamp": time.time()}

    def private_request(self, method, params):
        if not settings.indodax_api_key or not settings.indodax_secret_key:
            raise RuntimeError("Indodax private credentials are not configured")
        payload = {"method": method, "timestamp": int(time.time() * 1000), "recvWindow": 5000, **params}
        body = urlencode(payload)
        signature = hmac.new(settings.indodax_secret_key.encode(), body.encode(), hashlib.sha512).hexdigest()
        headers = {"Key": settings.indodax_api_key, "Sign": signature, "Content-Type": "application/x-www-form-urlencoded"}
        r = httpx.post(self.private_url, content=body, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("success") in (0, False): raise RuntimeError(data.get("error", "Indodax private API error"))
        return data

    def trade(self, symbol, side, price, quantity):
        base = symbol.lower().removesuffix("idr")
        params = {"pair": symbol.lower(), "type": side, "price": str(price), "idr": str(price * quantity)}
        params[base] = str(quantity)
        return self.private_request("trade", params)
