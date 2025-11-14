"""
Fawkes Authentication Module

Provides authentication and authorization for Fawkes distributed fuzzing system.
"""

from .middleware import (
    authenticate_request,
    require_permission,
    AuthenticationError,
    AuthorizationError
)

from .tls import (
    generate_self_signed_cert,
    wrap_socket_tls,
    verify_certificate
)

__all__ = [
    "authenticate_request",
    "require_permission",
    "AuthenticationError",
    "AuthorizationError",
    "generate_self_signed_cert",
    "wrap_socket_tls",
    "verify_certificate"
]
