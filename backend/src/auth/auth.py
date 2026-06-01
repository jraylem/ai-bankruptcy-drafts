"""Authentication utilities for the AI Chatbot backend."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select

from ..config import settings
from .database import UserAsyncSessionLocal
from .models import RefreshSession, User

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
SECRET_KEY = settings.JWT_SECRET_KEY
ALGORITHM = settings.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS = settings.REFRESH_TOKEN_EXPIRE_DAYS

# Bearer scheme — auto_error=False so missing header returns None instead of
# raising immediately; get_current_user falls back to cookie in that case.
security = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


# ---------------------------------------------------------------------------
# Access token (short-lived JWT)
# ---------------------------------------------------------------------------

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode a JWT access token. Raises JWTError on failure."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


# ---------------------------------------------------------------------------
# Refresh token (opaque, server-side stored as hash)
# ---------------------------------------------------------------------------

def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def create_refresh_token(
    user_id: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> str:
    """Generate an opaque refresh token, persist its hash, return the raw value."""
    raw = secrets.token_urlsafe(32)
    hashed = _hash_token(raw)
    expires = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    async with UserAsyncSessionLocal() as session:
        session.add(RefreshSession(
            user_id=user_id,
            token_hash=hashed,
            expires_at=expires,
            ip_address=ip_address,
            user_agent=user_agent,
        ))
        await session.commit()

    return raw


async def validate_and_rotate_refresh_token(
    raw: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> tuple["User", str, str]:
    """Validate a refresh token, revoke it, and issue a new access + refresh pair.

    Raises 401 if the token is missing, expired, or already revoked.
    """
    hashed = _hash_token(raw)
    now = datetime.now(timezone.utc)

    async with UserAsyncSessionLocal() as session:
        result = await session.execute(
            select(RefreshSession).where(
                RefreshSession.token_hash == hashed,
                RefreshSession.revoked_at.is_(None),
                RefreshSession.expires_at > now,
            )
        )
        rs = result.scalar_one_or_none()
        if rs is None:
            raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

        user_id = rs.user_id
        rs.revoked_at = now
        await session.commit()

    user = await get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    # Multi-tenancy: rotated access tokens must carry firm_id and role
    # so downstream paywall / RBAC checks keep working.
    new_access = create_access_token(
        data={
            "sub": user.id,
            "firm_id": user.firm_id,
            "role": user.role,
        }
    )
    new_refresh = await create_refresh_token(user.id, ip_address=ip_address, user_agent=user_agent)
    return user, new_access, new_refresh


async def revoke_refresh_token(raw: str) -> None:
    """Revoke a single refresh session by its raw token value."""
    hashed = _hash_token(raw)
    now = datetime.now(timezone.utc)

    async with UserAsyncSessionLocal() as session:
        result = await session.execute(
            select(RefreshSession).where(RefreshSession.token_hash == hashed)
        )
        rs = result.scalar_one_or_none()
        if rs and rs.revoked_at is None:
            rs.revoked_at = now
            await session.commit()


async def revoke_all_refresh_tokens(user_id: str) -> None:
    """Revoke every active refresh session for a user.

    Called after a successful password reset to force re-login on all devices.
    """
    from sqlalchemy import update as sa_update

    now = datetime.now(timezone.utc)
    async with UserAsyncSessionLocal() as session:
        await session.execute(
            sa_update(RefreshSession)
            .where(
                RefreshSession.user_id == user_id,
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        await session.commit()


# ---------------------------------------------------------------------------
# User lookups
# ---------------------------------------------------------------------------

async def get_user_by_email(email: str) -> Optional[User]:
    normalized = email.lower().strip()
    async with UserAsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.email == normalized, User.is_active == True)
        )
        return result.scalar_one_or_none()


async def get_user_by_id(user_id: str) -> Optional[User]:
    async with UserAsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.id == user_id, User.is_active == True)
        )
        return result.scalar_one_or_none()


async def authenticate_user(email: str, password: str) -> Optional[User]:
    user = await get_user_by_email(email)
    if not user or not verify_password(password, user.password_hash):
        return None
    return user


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

async def _user_from_token(token: str) -> User:
    """Decode a JWT and return the corresponding active user.

    Enforces multi-tenancy: the payload MUST carry firm_id (added by
    feat/agt-revamp's paywall work). Tokens missing it predate the
    multi-tenancy migration and are rejected.
    """
    try:
        payload = decode_access_token(token)
        user_id: str = payload.get("sub")
        firm_id: str = payload.get("firm_id")
        if user_id is None or firm_id is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Session expired, please log in again",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Account not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> User:
    """Resolve the authenticated user.

    Tries the HttpOnly access_token cookie first; falls back to the
    Authorization: Bearer header so the existing frontend continues to work
    during the migration period.
    """
    access_token = request.cookies.get("access_token")
    if access_token:
        return await _user_from_token(access_token)

    if credentials:
        return await _user_from_token(credentials.credentials)

    raise HTTPException(
        status_code=401,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user_pre_firm(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> User:
    """Authenticated user dependency that does NOT require firm_id in the JWT.

    Use only on POST /api/firms — the one route where a logged-in user
    has no firm yet and firm_id is legitimately None in the token.
    All other protected routes should use get_current_user or get_current_firm_user.
    """
    access_token = request.cookies.get("access_token")
    token = access_token or (credentials.credentials if credentials else None)
    if token is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(token)
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Session expired, please log in again",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Account not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[User]:
    """Like get_current_user but returns None instead of raising."""
    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None


# ---------------------------------------------------------------------------
# Cookie helpers (shared by auth/routes.py and firms/routes.py)
# ---------------------------------------------------------------------------

_ACCESS_COOKIE_MAX_AGE = ACCESS_TOKEN_EXPIRE_MINUTES * 60
_REFRESH_COOKIE_MAX_AGE = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Write the three auth cookies: access (HttpOnly), refresh (HttpOnly, path-scoped), csrf.

    Called by: auth/routes.py (login, verify-email, refresh)
               firms/routes.py (accept_invitation)
    """
    secure = settings.COOKIE_SECURE
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=_ACCESS_COOKIE_MAX_AGE,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=_REFRESH_COOKIE_MAX_AGE,
        path="/api/auth/refresh",
    )
    response.set_cookie(
        key="csrf_token",
        value=secrets.token_urlsafe(32),
        httponly=False,
        secure=secure,
        samesite="lax",
        max_age=_ACCESS_COOKIE_MAX_AGE,
        path="/",
    )
