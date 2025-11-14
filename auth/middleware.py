"""
Authentication Middleware

Handles authentication and authorization for Fawkes network communication.
"""

import json
import logging
from typing import Dict, Any, Optional, Callable
from functools import wraps

logger = logging.getLogger("fawkes.auth")


class AuthenticationError(Exception):
    """Raised when authentication fails"""
    pass


class AuthorizationError(Exception):
    """Raised when authorization fails"""
    pass


def authenticate_request(auth_db, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Authenticate a network request

    Args:
        auth_db: AuthDB instance
        message: Request message with authentication credentials

    Returns:
        Dict with authenticated principal (user or API key info)

    Raises:
        AuthenticationError: If authentication fails
    """
    auth_type = message.get("auth_type")

    if not auth_type:
        raise AuthenticationError("No authentication provided")

    if auth_type == "api_key":
        api_key = message.get("api_key")
        if not api_key:
            raise AuthenticationError("API key missing")

        principal = auth_db.validate_api_key(api_key)
        if not principal:
            raise AuthenticationError("Invalid or expired API key")

        logger.debug(f"Authenticated API key: {principal['key_name']}")
        return principal

    elif auth_type == "session_token":
        token = message.get("session_token")
        if not token:
            raise AuthenticationError("Session token missing")

        principal = auth_db.validate_session(token)
        if not principal:
            raise AuthenticationError("Invalid or expired session token")

        logger.debug(f"Authenticated user session: {principal['username']}")
        return principal

    else:
        raise AuthenticationError(f"Unknown authentication type: {auth_type}")


def require_permission(principal: Dict[str, Any], permission: str) -> bool:
    """
    Check if principal has required permission

    Args:
        principal: Authenticated principal (from authenticate_request)
        permission: Required permission (e.g., "job:create")

    Returns:
        True if authorized

    Raises:
        AuthorizationError: If permission denied
    """
    permissions = principal.get("permissions", [])

    if permission not in permissions:
        logger.warning(f"Permission denied: {permission} for {principal.get('key_name') or principal.get('username')}")
        raise AuthorizationError(f"Permission denied: {permission}")

    return True


def authenticated(auth_db_getter: Callable):
    """
    Decorator for functions that require authentication

    Args:
        auth_db_getter: Function that returns AuthDB instance

    Example:
        @authenticated(lambda: get_auth_db())
        def handle_request(message, principal):
            # principal is automatically injected
            pass
    """
    def decorator(func):
        @wraps(func)
        def wrapper(message, *args, **kwargs):
            auth_db = auth_db_getter()
            try:
                principal = authenticate_request(auth_db, message)
                return func(message, principal=principal, *args, **kwargs)
            except AuthenticationError as e:
                logger.error(f"Authentication failed: {e}")
                raise
        return wrapper
    return decorator


def authorized(*required_permissions):
    """
    Decorator for functions that require specific permissions

    Args:
        *required_permissions: Required permissions

    Example:
        @authenticated(lambda: get_auth_db())
        @authorized("job:create", "worker:update")
        def handle_job_request(message, principal):
            pass
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, principal=None, **kwargs):
            if principal is None:
                raise AuthorizationError("No authenticated principal")

            for permission in required_permissions:
                require_permission(principal, permission)

            return func(*args, principal=principal, **kwargs)
        return wrapper
    return decorator


def add_authentication(message: Dict[str, Any], auth_type: str,
                      credential: str) -> Dict[str, Any]:
    """
    Add authentication credentials to a message

    Args:
        message: Message dict
        auth_type: Type of authentication ("api_key" or "session_token")
        credential: API key or session token

    Returns:
        Message with authentication added
    """
    message["auth_type"] = auth_type

    if auth_type == "api_key":
        message["api_key"] = credential
    elif auth_type == "session_token":
        message["session_token"] = credential
    else:
        raise ValueError(f"Unknown auth type: {auth_type}")

    return message


def create_auth_response(success: bool, message: str = "",
                        data: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Create a standardized authentication response

    Args:
        success: Whether authentication succeeded
        message: Optional message
        data: Optional additional data

    Returns:
        Response dict
    """
    response = {
        "auth_success": success,
        "message": message
    }

    if data:
        response["data"] = data

    return response
