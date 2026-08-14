"""
Security module for authentication and authorization
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-this-in-production")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

class Security:
    """Security class for authentication"""
    
    def __init__(self):
        self.secret_key = SECRET_KEY
        self.algorithm = ALGORITHM
        self.token_expire_minutes = ACCESS_TOKEN_EXPIRE_MINUTES
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify password against hash"""
        return pwd_context.verify(plain_password, hashed_password)
    
    def get_password_hash(self, password: str) -> str:
        """Hash password"""
        return pwd_context.hash(password)
    
    def create_access_token(self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT access token"""
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({"exp": expire, "iat": datetime.utcnow()})
        
        try:
            encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
            return encoded_jwt
        except Exception as e:
            logger.error(f"Error creating token: {e}")
            raise
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify JWT token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
    
    def get_current_user(self, token: str) -> Optional[Dict[str, Any]]:
        """Get current user from token"""
        payload = self.verify_token(token)
        if payload is None:
            return None
        
        username = payload.get("sub")
        if username is None:
            return None
        
        return {"username": username, "exp": payload.get("exp")}

# Helper functions for easy use
def create_access_token(data: Dict[str, Any]) -> str:
    """Helper to create access token"""
    security = Security()
    return security.create_access_token(data)

def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Helper to verify token"""
    security = Security()
    return security.verify_token(token)

def get_password_hash(password: str) -> str:
    """Helper to hash password"""
    security = Security()
    return security.get_password_hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Helper to verify password"""
    security = Security()
    return security.verify_password(plain_password, hashed_password)

# Example users (in production, this would be in database)
DEFAULT_USERS = {
    "admin": {
        "username": "admin",
        "password": get_password_hash("admin123")  # Change in production!
    }
}

def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticate user"""
    if username in DEFAULT_USERS:
        user = DEFAULT_USERS[username]
        if verify_password(password, user["password"]):
            return {"username": username}
    return None
