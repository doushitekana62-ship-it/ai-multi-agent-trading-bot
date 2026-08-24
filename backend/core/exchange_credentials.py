"""Encrypted runtime storage for exchange credentials.

The dashboard may save credentials without putting secrets in source code or .env.
The encrypted file is ignored by git and should only be readable by the bot process.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()


class ExchangeCredentialStore:
    def __init__(self, path: str = "data/exchange_credentials.enc"):
        self.path = Path(path)
        secret = os.getenv("JWT_SECRET_KEY")
        if not secret or secret == "your-secret-key-change-this-in-production":
            raise RuntimeError("JWT_SECRET_KEY must be configured before exchange credentials can be stored")
        digest = hashlib.sha256(secret.encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    def save(self, exchange: str, api_key: str, api_secret: str, enable_trading: bool = False) -> None:
        if not api_key or not api_secret:
            raise ValueError("API key and API secret are required")
        payload = {
            "exchange": exchange.lower(),
            "api_key": api_key,
            "api_secret": api_secret,
            "enable_trading": bool(enable_trading),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(self._fernet.encrypt(json.dumps(payload).encode("utf-8")))
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def load(self) -> Optional[Dict[str, Any]]:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self._fernet.decrypt(self.path.read_bytes()).decode("utf-8"))
            return payload
        except Exception as exc:
            raise RuntimeError("Stored exchange credentials could not be decrypted") from exc

    def public_status(self) -> Dict[str, Any]:
        payload = self.load()
        if not payload:
            return {"configured": False, "exchange": None, "trading_enabled": False}
        return {
            "configured": True,
            "exchange": payload.get("exchange"),
            "trading_enabled": bool(payload.get("enable_trading", False)),
            "api_key_last4": str(payload.get("api_key", ""))[-4:],
        }
