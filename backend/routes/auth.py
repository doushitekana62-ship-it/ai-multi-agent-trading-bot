"""
Authentication Routes
Login, refresh token, logout
"""

import logging
from datetime import timedelta
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from backend.core.security import (
    Security, create_access_token, verify_token,
    authenticate_user, DEFAULT_USERS
)

logger = logging.getLogger(__name__)

router = APIRouter()
security = HTTPBearer()
security_instance = Security()

ACCESS_EXPIRES_MINUTES = security_instance.token_expire_minutes
REFRESH_EXPIRES_DAYS = 7


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    refresh_expires_in: int
    username: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class RefreshTokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


class UserResponse(BaseModel):
    username: str
    is_authenticated: bool


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    try:
        user = authenticate_user(request.username, request.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        access_token = create_access_token(
            data={"sub": user["username"], "type": "access"}
        )
        refresh_token = create_access_token(
            data={"sub": user["username"], "type": "refresh"},
            expires_delta=timedelta(days=REFRESH_EXPIRES_DAYS),
        )

        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=ACCESS_EXPIRES_MINUTES,
            refresh_expires_in=REFRESH_EXPIRES_DAYS * 24 * 60,
            username=user["username"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Login error: %s", e)
        raise HTTPException(status_code=500, detail="Login failed")


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(request: RefreshTokenRequest):
    try:
        payload = verify_token(request.refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            )

        username = payload.get("sub")
        if username not in DEFAULT_USERS:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        access_token = create_access_token(
            data={"sub": username, "type": "access"}
        )
        return RefreshTokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=ACCESS_EXPIRES_MINUTES,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Refresh token error: %s", e)
        raise HTTPException(status_code=500, detail="Refresh failed")


@router.post("/logout")
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
    return {"message": "Logged out successfully", "status": "success"}


@router.get("/verify", response_model=UserResponse)
async def verify(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = verify_token(credentials.credentials)
        if not payload or payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

        username = payload.get("sub")
        if username not in DEFAULT_USERS:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        return UserResponse(username=username, is_authenticated=True)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Verify error: %s", e)
        raise HTTPException(status_code=500, detail="Verification failed")


@router.post("/change-password")
async def change_password(
    old_password: str,
    new_password: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    try:
        payload = verify_token(credentials.credentials)
        if not payload or payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token")

        username = payload.get("sub")
        if username not in DEFAULT_USERS:
            raise HTTPException(status_code=404, detail="User not found")

        if not security_instance.verify_password(
            old_password, DEFAULT_USERS[username]["password"]
        ):
            raise HTTPException(status_code=400, detail="Old password is incorrect")

        DEFAULT_USERS[username]["password"] = security_instance.get_password_hash(new_password)
        return {"message": "Password changed successfully", "status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Change password error: %s", e)
        raise HTTPException(status_code=500, detail="Password change failed")
