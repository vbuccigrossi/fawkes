"""User and authentication models"""

from pydantic import BaseModel, Field


class UserLogin(BaseModel):
    """Model for user login."""
    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")


class Token(BaseModel):
    """Model for JWT token response."""
    access_token: str
    token_type: str = "bearer"


class User(BaseModel):
    """Model for user response."""
    username: str
    role: str  # admin, operator, viewer

    class Config:
        from_attributes = True
