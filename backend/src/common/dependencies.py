"""Shared dependency injection for FastAPI endpoints."""

from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from jose import JWTError, jwt

from ..auth.auth import get_current_user, security
from ..auth.models import User
from ..config import settings


async def get_current_firm_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    user: User = Depends(get_current_user),
) -> User:
    """Authenticated user dependency with firm_id cross-validation.

    Wraps get_current_user() and adds a DB-vs-token cross-check:
    the firm_id embedded in the JWT must match the firm_id stored
    in the database for that user. Raises HTTP 401 on mismatch.

    Use this instead of get_current_user() on all tenant-scoped routes.

    Auth precedence matches get_current_user: HttpOnly access_token cookie
    first (cookie-era FE), then Authorization: Bearer header (legacy FE
    during the cookie-migration transition).
    """
    raw_token: Optional[str] = request.cookies.get("access_token")
    if not raw_token and credentials is not None:
        raw_token = credentials.credentials

    if not raw_token:
        # get_current_user would have already raised before us, so this
        # branch is mostly defensive — kept for clarity if the dep tree
        # ever changes.
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            raw_token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        token_firm_id: str = payload.get("firm_id")
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if token_firm_id is None or token_firm_id != user.firm_id:
        raise HTTPException(
            status_code=401,
            detail="Token firm does not match user record.",
        )

    return user


# Legacy helpers kept for backwards compatibility
def get_current_user_dep():
    """Dependency for getting current authenticated user."""
    return Depends(get_current_user)


def get_current_user_optional_dep():
    """Dependency for getting current user (optional)."""
    from ..auth.auth import get_current_user_optional
    return Depends(get_current_user_optional)
