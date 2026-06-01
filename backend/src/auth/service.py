"""Business logic for authentication."""

import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func as sa_func, select

from ..chatbot.database import log_user_action
from ..firms.models import Firm, OnboardingStatus, SubscriptionStatus
from ..permissions.constants import Permission
from ..schema import RegisterResponse, UserCreate, UserResponse
from .auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    get_password_hash,
    revoke_all_refresh_tokens,
)
from .database import UserAsyncSessionLocal
from .models import User, UserRole


async def register_new_user(user_data: UserCreate) -> tuple[RegisterResponse, str, str, str]:
    """Register a new user and their firm in a single atomic transaction.

    User and Firm are created together and committed once — if either validation
    fails, neither is persisted. This eliminates the broken state where a user
    exists with firm_id=null (previously possible when create_firm() raised after
    the user was already committed in a separate session).

    Called by: POST /api/auth/register (via routes.py)
    """
    async with UserAsyncSessionLocal() as session:
        normalized_email = user_data.email.lower().strip()
        firm_name = user_data.firm_name.strip()

        # Validate email uniqueness
        email_check = await session.execute(select(User).where(User.email == normalized_email))
        if email_check.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Email already registered")

        # Validate firm name uniqueness — checked here so failure rolls back the user too
        firm_check = await session.execute(
            select(Firm).where(sa_func.lower(Firm.name) == firm_name.lower())
        )
        if firm_check.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail="A firm with this name already exists. Please choose a different name.",
            )

        verification_token = str(uuid4())
        verification_expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        firm_id = str(uuid4())

        firm = Firm(
            id=firm_id,
            name=firm_name,
            owner_email=normalized_email,
            subscription_status=SubscriptionStatus.trialing,
            is_active=True,
            onboarding_status=OnboardingStatus.pending,
        )
        session.add(firm)

        db_user = User(
            email=normalized_email,
            password_hash=get_password_hash(user_data.password),
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            email_verified=False,
            email_verification_token=verification_token,
            email_verification_expires_at=verification_expires_at,
            firm_id=firm_id,
            role=UserRole.firm_owner,
            permissions=list(Permission.ALL),
            # Firm owners create their own firm — no invitation flow, so set joined date now
            invitation_accepted_at=datetime.now(timezone.utc),
        )
        session.add(db_user)

        # Single commit — both User and Firm succeed or both fail
        await session.commit()
        await session.refresh(db_user)

    await log_user_action(
        action="register",
        user_id=db_user.id,
        firm_id=db_user.firm_id,
        metadata={"email": normalized_email},
    )

    return (
        RegisterResponse(
            message="Verification email sent. Please check your inbox.",
            user_id=db_user.id,
        ),
        normalized_email,
        verification_token,
        firm_name,
    )


async def verify_email_token(
    token: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[User, str, str]:
    """Verify the email token and issue JWT + refresh token.

    1. Find user by email_verification_token
    2. Check not already verified + not expired
    3. Set email_verified=True, clear token fields
    4. Issue JWT (with firm_id if user has a firm)
    5. Return (user, access_token, refresh_token)

    Called by: POST /api/auth/verify-email (via routes.py)
    """
    async with UserAsyncSessionLocal() as session:
        now = datetime.now(timezone.utc)

        result = await session.execute(
            select(User).where(User.email_verification_token == token)
        )
        user = result.scalar_one_or_none()

        if user is None:
            raise HTTPException(status_code=400, detail="Invalid or expired verification token")

        if user.email_verified:
            raise HTTPException(status_code=409, detail="Email already verified")

        expires_at = user.email_verification_expires_at
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at is None or expires_at < now:
            raise HTTPException(status_code=410, detail="Verification token has expired")

        user.email_verified = True
        user.email_verification_token = None
        user.email_verification_expires_at = None

        # Generate approval token so admin can approve/deny via email link
        user.approval_token = str(uuid4())
        user.approval_token_expires_at = now + timedelta(days=7)

        await session.commit()
        await session.refresh(user)

        access_token = create_access_token(data={
            "sub": user.id,
            "firm_id": user.firm_id,
            "role": user.role,
        })
        refresh_token = await create_refresh_token(user.id, ip_address=ip_address, user_agent=user_agent)

        await log_user_action(
            action="email_verified",
            user_id=user.id,
            firm_id=user.firm_id,
            metadata={"email": user.email},
        )

        # Notify admin — fire-and-forget, never blocks the verification response
        from urllib.parse import quote_plus
        from ..notifications.email import send_approval_request_email
        from ..config import settings
        from ..firms.service import get_firm

        firm_name = ""
        if user.firm_id:
            try:
                firm = await get_firm(user.firm_id)
                firm_name = firm.name or ""
            except Exception:
                pass

        base = f"{settings.FRONTEND_URL}/user-approval?token={user.approval_token}"
        approve_url = f"{base}&action=approve&firm={quote_plus(firm_name)}&email={quote_plus(user.email)}"
        deny_url = f"{base}&action=deny&firm={quote_plus(firm_name)}&email={quote_plus(user.email)}"
        user_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email
        await send_approval_request_email(
            to_email=settings.APPROVAL_ADMIN_EMAIL,
            user_name=user_name,
            user_email=user.email,
            firm_name=firm_name,
            approve_url=approve_url,
            deny_url=deny_url,
        )

        return user, access_token, refresh_token


async def resend_verification_email(email: str) -> tuple[dict, str | None, str | None, str | None]:
    """Resend the email verification link.

    Security: always returns the same success message whether or not the email
    exists, so callers cannot enumerate registered addresses.

    Returns (response_dict, email_to_send, token, firm_name) where email_to_send/token/firm_name
    are None when no email should be sent — route sends email via BackgroundTasks.

    TODO (future): add 3 max per 24 h + 2-minute cooldown:
      - Add verification_resend_count (INT DEFAULT 0) and
        verification_resend_reset_at (TIMESTAMPTZ) columns to users
      - Enforce limit here before generating a new token

    Called by: POST /api/auth/resend-verification (via routes.py)
    """
    _SAFE_MSG = "If an account with this email exists and is unverified, a new verification email has been sent."

    async with UserAsyncSessionLocal() as session:
        normalized_email = email.lower().strip()
        result = await session.execute(select(User).where(User.email == normalized_email))
        user = result.scalar_one_or_none()

        # Silently succeed if unknown email or already verified — no enumeration
        if user is None or user.email_verified:
            return {"message": _SAFE_MSG}, None, None, None

        verification_token = str(uuid4())
        user.email_verification_token = verification_token
        user.email_verification_expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

        firm_name = ""
        if user.firm_id:
            firm_result = await session.execute(select(Firm).where(Firm.id == user.firm_id))
            firm = firm_result.scalar_one_or_none()
            if firm:
                firm_name = firm.name

        await session.commit()

    return {"message": _SAFE_MSG}, normalized_email, verification_token, firm_name


async def login_user(
    email: str,
    password: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[User, str, str]:
    """Authenticate credentials and return (user, access_token, refresh_token).

    The access token carries firm_id + role so downstream multi-tenancy
    and RBAC checks (get_current_user firm_id requirement, paywall
    enforcement) keep working.

    Decision 2: raises 401 if email is not yet verified.
    """
    normalized_email = email.lower().strip()

    # Check email existence separately so we can return a distinct message
    async with UserAsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == normalized_email))
        email_exists = result.scalar_one_or_none() is not None

    if not email_exists:
        raise HTTPException(status_code=404, detail="Email is not yet registered")

    user = await authenticate_user(normalized_email, password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Incorrect password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Decision 2: email verification gate — prevents bypassing verification via direct login
    if not user.email_verified:
        raise HTTPException(
            status_code=401,
            detail="Email not verified. Please check your inbox.",
        )

    # Guard: firm association is required. If firm_id is null the account is in a
    # broken state (firm creation failed during registration). Issuing a JWT with
    # firm_id=null would cause every subsequent request to fail with "Invalid token",
    # so we surface the problem here instead.
    if not user.firm_id:
        raise HTTPException(
            status_code=403,
            detail="Account setup is incomplete. Please contact support.",
        )
    
    if not user.is_accepted:
        raise HTTPException(
            status_code=403,
            detail="Please contact nickf@cvhlawgroup.com to gain access.",
        )

    access_token = create_access_token(
        data={
            "sub": user.id,
            "firm_id": user.firm_id,
            "role": user.role,
        }
    )
    refresh_token = await create_refresh_token(user.id, ip_address=ip_address, user_agent=user_agent)

    await log_user_action(
        action="login",
        user_id=user.id,
        firm_id=user.firm_id,
        metadata={"email": normalized_email},
    )
    return user, access_token, refresh_token


_RESET_TOKEN_TTL_HOURS = 1


async def request_password_reset(email: str) -> tuple[str | None, str | None]:
    """Generate a password reset token and persist it on the user record.

    Security: always returns the same message regardless of whether the email
    exists, so callers cannot enumerate registered addresses.

    Returns (email_to_send, reset_token) — both None when no email should be
    sent. The route sends the email via BackgroundTasks.

    Called by: POST /api/auth/forgot-password (via routes.py)
    """
    async with UserAsyncSessionLocal() as session:
        normalized_email = email.lower().strip()
        result = await session.execute(select(User).where(User.email == normalized_email))
        user = result.scalar_one_or_none()

        if user is None or not user.is_active:
            return None, None

        reset_token = secrets.token_urlsafe(32)
        user.password_reset_token = reset_token
        user.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(hours=_RESET_TOKEN_TTL_HOURS)

        await session.commit()

    return normalized_email, reset_token


async def reset_password(token: str, new_password: str) -> None:
    """Consume a password reset token and update the user's password.

    1. Look up user by password_reset_token
    2. Validate token is not expired
    3. bcrypt-hash the new password and persist it
    4. Clear the reset token fields (single-use)
    5. Revoke ALL active refresh sessions → forces re-login on all devices

    Raises 400 for invalid/expired token.

    Called by: POST /api/auth/reset-password (via routes.py)
    """
    async with UserAsyncSessionLocal() as session:
        now = datetime.now(timezone.utc)

        result = await session.execute(
            select(User).where(User.password_reset_token == token)
        )
        user = result.scalar_one_or_none()

        if user is None:
            raise HTTPException(status_code=400, detail="Invalid or expired reset token")

        expires_at = user.password_reset_expires_at
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at is None or expires_at < now:
            raise HTTPException(status_code=400, detail="Invalid or expired reset token")

        user.password_hash = get_password_hash(new_password)
        user.password_reset_token = None
        user.password_reset_expires_at = None

        await session.commit()
        user_id = user.id

    await revoke_all_refresh_tokens(user_id)

    await log_user_action(
        action="password_reset",
        user_id=user_id,
        firm_id=None,
        metadata={},
    )


# ---------------------------------------------------------------------------
# User approval / waitlist
# ---------------------------------------------------------------------------

async def get_waitlist() -> list[User]:
    """Return all users pending admin approval — email verified but not yet accepted.

    Called by: GET /api/admin/waitlist (via admin_routes.py)
    """
    async with UserAsyncSessionLocal() as session:
        result = await session.execute(
            select(User)
            .where(User.email_verified == True, User.is_accepted == False)  # noqa: E712
            .order_by(User.created_at.asc())
        )
        return list(result.scalars().all())


async def approve_user(user_id: str) -> User:
    """Approve a waitlisted user — sets is_accepted=True and clears the approval token.

    Called by:
      - GET /api/auth/user-approval/{token}?action=approve (via routes.py)
      - POST /api/admin/waitlist/{user_id}/approve (via admin_routes.py)
    """
    from ..notifications.email import send_user_approved_email
    from ..config import settings

    async with UserAsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        if user.is_accepted:
            raise HTTPException(status_code=409, detail="User is already approved")

        user.is_accepted = True
        user.approval_token = None
        user.approval_token_expires_at = None
        await session.commit()
        await session.refresh(user)

    await send_user_approved_email(
        to_email=user.email,
        login_url=f"{settings.FRONTEND_URL}/login",
    )
    return user


async def deny_user(user_id: str) -> User:
    """Deny a waitlisted user — clears the approval token and notifies the user.

    Called by:
      - GET /api/auth/user-approval/{token}?action=deny (via routes.py)
      - POST /api/admin/waitlist/{user_id}/deny (via admin_routes.py)
    """
    from ..notifications.email import send_user_denied_email

    async with UserAsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        user.approval_token = None
        user.approval_token_expires_at = None
        await session.commit()
        await session.refresh(user)

    await send_user_denied_email(to_email=user.email)
    return user


async def review_by_token(token: str, action: str) -> User:
    """Approve or deny a user via the tokenized email link.

    Called by: GET /api/auth/user-approval/{token}?action= (via routes.py)
    """
    if action not in ("approve", "deny"):
        raise HTTPException(status_code=400, detail="Invalid action. Must be 'approve' or 'deny'.")

    async with UserAsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.approval_token == token)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="Invalid or already used approval link")

        expires_at = user.approval_token_expires_at
        now = datetime.now(timezone.utc)
        if expires_at is not None:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < now:
                raise HTTPException(status_code=410, detail="Approval link has expired")

        user_id = user.id

    if action == "approve":
        return await approve_user(user_id)
    return await deny_user(user_id)
