"""Authentication module for AI Petition Reviewer."""

from .auth import (
    get_current_user,
    get_current_user_optional,
    get_password_hash,
    authenticate_user,
    create_access_token,
    get_user_by_id,
    get_user_by_email
)
from .models import User
from .routes import router

__all__ = [
    "get_current_user",
    "get_current_user_optional",
    "get_password_hash",
    "authenticate_user",
    "create_access_token",
    "get_user_by_id",
    "get_user_by_email",
    "User",
    "router"
]
