"""Authentication, password hashing and JWT security."""

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import jwt
from dotenv import load_dotenv
from passlib.context import CryptContext

load_dotenv()

logger = logging.getLogger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

_INSECURE_JWT_VALUES = {
    "your-secret-key-change-this-in-production",
    "your_jwt_secret_here_use_openssl_rand_hex",
    "replace_with_a_long_random_secret",
}

if not SECRET_KEY or SECRET_KEY in _INSECURE_JWT_VALUES or len(SECRET_KEY) < 32:
    raise RuntimeError(
        "JWT_SECRET_KEY must be a strong random value of at least 32 characters"
    )

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
if not ADMIN_PASSWORD:
    logger.warning(
        "ADMIN_PASSWORD is not configured; dashboard login will be unavailable until it is set"
    )


class Security:
    def __init__(self):
        self.secret_key = SECRET_KEY
        self.algorithm = ALGORITHM
        self.token_expire_minutes = ACCESS_TOKEN_EXPIRE_MINUTES

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        return pwd_context.hash(password)

    def create_access_token(
        self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None
    ) -> str:
        to_encode = data.copy()
        now = datetime.utcnow()
        expire = now + (expires_delta or timedelta(minutes=self.token_expire_minutes))
        to_encode.update({"exp": expire, "iat": now})
        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        try:
            return jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return None

    def get_current_user(self, token: str) -> Optional[Dict[str, Any]]:
        payload = self.verify_token(token)
        if not payload or not payload.get("sub"):
            return None
        return {"username": payload["sub"], "exp": payload.get("exp")}


def create_access_token(data: Dict[str, Any]) -> str:
    return Security().create_access_token(data)


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    return Security().verify_token(token)


def get_password_hash(password: str) -> str:
    return Security().get_password_hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return Security().verify_password(plain_password, hashed_password)


DEFAULT_USERS = {}
if ADMIN_PASSWORD:
    DEFAULT_USERS[ADMIN_USERNAME] = {
        "username": ADMIN_USERNAME,
        "password": get_password_hash(ADMIN_PASSWORD),
    }


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    user = DEFAULT_USERS.get(username)
    if user and verify_password(password, user["password"]):
        return {"username": username}
    return None
