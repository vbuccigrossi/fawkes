"""Authentication API endpoints"""

import logging
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from api.models.user import UserLogin, Token, User

router = APIRouter()
logger = logging.getLogger("fawkes.web.api.auth")

# Security configuration
import os
SECRET_KEY = os.environ.get("FAWKES_SECRET_KEY", "change-me-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours

security = HTTPBearer()


def hash_password(password: str) -> str:
    """Simple password hashing using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return hash_password(plain_password) == hashed_password


# Simple in-memory user store (TODO: Replace with database)
USERS_DB = {
    "admin": {
        "username": "admin",
        "hashed_password": hash_password("admin"),  # Default password: admin
        "role": "admin"
    }
}


def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    """Get current authenticated user from JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = USERS_DB.get(username)
    if user is None:
        raise credentials_exception

    return User(username=user["username"], role=user["role"])


@router.post("/login", response_model=Token)
async def login(user_login: UserLogin):
    """
    Authenticate user and return JWT token.

    Args:
        user_login: Username and password

    Returns:
        JWT access token
    """
    try:
        # Check if user exists
        user = USERS_DB.get(user_login.username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password"
            )

        # Verify password
        if not verify_password(user_login.password, user["hashed_password"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password"
            )

        # Create access token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user["username"], "role": user["role"]},
            expires_delta=access_token_expires
        )

        logger.info(f"User {user_login.username} logged in successfully")

        return Token(access_token=access_token, token_type="bearer")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during login: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/logout", response_model=Dict[str, Any])
async def logout(current_user: User = Depends(get_current_user)):
    """
    Logout current user.

    Note: JWT tokens are stateless, so logout is handled client-side
    by removing the token from storage.

    Args:
        current_user: Current authenticated user

    Returns:
        Success confirmation
    """
    logger.info(f"User {current_user.username} logged out")

    return {
        "success": True,
        "message": "Logged out successfully"
    }


@router.get("/me", response_model=User)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """
    Get current user information.

    Args:
        current_user: Current authenticated user

    Returns:
        User information
    """
    return current_user
