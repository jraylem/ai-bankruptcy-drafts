"""Business logic for the Settings module — Phase 4.

All DB access uses UserAsyncSessionLocal (user_db).
"""

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func as sa_func, select

from ..auth.auth import get_password_hash, verify_password
from ..auth.database import UserAsyncSessionLocal
from ..auth.models import RefreshSession, User, UserRole
from ..firms.models import Firm, FirmInvitation, Plan
from ..notifications.email import send_invite_email
from .models import AuditLog, FirmSettings, UserSettings
from .schemas import (
    AuditLogItem,
    AuditLogResponse,
    BillingSummaryResponse,
    FirmSettingsResponse,
    PendingInvitationResponse,
    SessionItemResponse,
    SessionListResponse,
    UserSettingsResponse,
)

logger = logging.getLogger(__name__)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# User settings
# ---------------------------------------------------------------------------

async def get_or_create_user_settings(user_id: str) -> UserSettingsResponse:
    """Return existing user settings or create defaults on first call."""
    async with UserAsyncSessionLocal() as session:
        result = await session.execute(
            select(UserSettings).where(UserSettings.user_id == user_id)
        )
        settings = result.scalar_one_or_none()

        if settings is None:
            settings = UserSettings(user_id=user_id)
            session.add(settings)
            await session.commit()
            await session.refresh(settings)

        user_result = await session.execute(
            select(User.email_verified).where(User.id == user_id)
        )
        email_verified = user_result.scalar_one_or_none()

    response = UserSettingsResponse.model_validate(settings)
    return response.model_copy(update={"email_verified": email_verified})


async def update_user_settings(user_id: str, data) -> UserSettingsResponse:
    """PATCH user settings — only updates fields that are not None."""
    async with UserAsyncSessionLocal() as session:
        result = await session.execute(
            select(UserSettings).where(UserSettings.user_id == user_id)
        )
        settings = result.scalar_one_or_none()

        if settings is None:
            settings = UserSettings(user_id=user_id)
            session.add(settings)

        if data.notification_email is not None:
            settings.notification_email = data.notification_email
        if data.notification_inapp is not None:
            settings.notification_inapp = data.notification_inapp
        if data.theme is not None:
            settings.theme = data.theme
        if data.notify_motion_approved is not None:
            settings.notify_motion_approved = data.notify_motion_approved
        if data.notify_motion_rejected is not None:
            settings.notify_motion_rejected = data.notify_motion_rejected

        settings.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(settings)

        user_result = await session.execute(
            select(User.email_verified).where(User.id == user_id)
        )
        email_verified = user_result.scalar_one_or_none()

    response = UserSettingsResponse.model_validate(settings)
    return response.model_copy(update={"email_verified": email_verified})


# ---------------------------------------------------------------------------
# Firm settings
# ---------------------------------------------------------------------------

async def get_or_create_firm_settings(firm_id: str) -> FirmSettingsResponse:
    """Return existing firm settings or create defaults. Also returns Firm fields."""
    async with UserAsyncSessionLocal() as session:
        result = await session.execute(
            select(FirmSettings).where(FirmSettings.firm_id == firm_id)
        )
        firm_settings = result.scalar_one_or_none()

        if firm_settings is None:
            firm_settings = FirmSettings(firm_id=firm_id)
            session.add(firm_settings)
            await session.commit()
            await session.refresh(firm_settings)

        result = await session.execute(select(Firm).where(Firm.id == firm_id))
        firm = result.scalar_one_or_none()

        return FirmSettingsResponse(
            firm_id=firm_settings.firm_id,
            allow_member_invites=firm_settings.allow_member_invites,
            motion_approval_required=firm_settings.motion_approval_required,
            enable_chat_rooms=firm_settings.enable_chat_rooms,
            enable_motion_comments=firm_settings.enable_motion_comments,
            paywall_enabled=firm_settings.paywall_enabled,
            updated_at=firm_settings.updated_at,
            allowed_domain=firm.allowed_domain if firm else None,
            onboarding_status=firm.onboarding_status.value if firm and firm.onboarding_status else None,
        )


async def update_firm_settings(firm_id: str, data, actor_id: Optional[str] = None) -> FirmSettingsResponse:
    """PATCH firm settings + optionally update Firm.allowed_domain."""
    from ..common.audit import log_audit_event

    async with UserAsyncSessionLocal() as session:
        result = await session.execute(
            select(FirmSettings).where(FirmSettings.firm_id == firm_id)
        )
        firm_settings = result.scalar_one_or_none()

        if firm_settings is None:
            firm_settings = FirmSettings(firm_id=firm_id)
            session.add(firm_settings)

        if data.allow_member_invites is not None:
            firm_settings.allow_member_invites = data.allow_member_invites
        if data.motion_approval_required is not None:
            firm_settings.motion_approval_required = data.motion_approval_required
        if data.enable_chat_rooms is not None:
            firm_settings.enable_chat_rooms = data.enable_chat_rooms
        if data.enable_motion_comments is not None:
            firm_settings.enable_motion_comments = data.enable_motion_comments
        if data.paywall_enabled is not None:
            firm_settings.paywall_enabled = data.paywall_enabled

        firm_settings.updated_at = datetime.now(timezone.utc)

        result = await session.execute(select(Firm).where(Firm.id == firm_id))
        firm = result.scalar_one_or_none()

        if firm and data.allowed_domain is not None:
            firm.allowed_domain = data.allowed_domain or None  # empty string → None

        await session.commit()
        if firm:
            await session.refresh(firm)
        await session.refresh(firm_settings)

    await log_audit_event(
        firm_id=firm_id,
        action="settings.firm_updated",
        user_id=actor_id,
        resource_type="firm_settings",
        resource_id=firm_id,
        metadata=data.model_dump(exclude_none=True),
    )

    return FirmSettingsResponse(
        firm_id=firm_settings.firm_id,
        allow_member_invites=firm_settings.allow_member_invites,
        motion_approval_required=firm_settings.motion_approval_required,
        enable_chat_rooms=firm_settings.enable_chat_rooms,
        enable_motion_comments=firm_settings.enable_motion_comments,
        paywall_enabled=firm_settings.paywall_enabled,
        updated_at=firm_settings.updated_at,
        allowed_domain=firm.allowed_domain if firm else None,
        onboarding_status=firm.onboarding_status.value if firm and firm.onboarding_status else None,
    )


async def get_paywall_enabled(firm_id: str) -> bool:
    """Return whether the subscription gate is active for this firm.

    Defaults to True (gated) when no FirmSettings row exists yet.
    """
    async with UserAsyncSessionLocal() as session:
        result = await session.execute(
            select(FirmSettings.paywall_enabled).where(FirmSettings.firm_id == firm_id)
        )
        value = result.scalar_one_or_none()
    return value if value is not None else True


# ---------------------------------------------------------------------------
# Password change
# ---------------------------------------------------------------------------

async def change_password(
    user_id: str,
    current_password: str,
    new_password: str,
    firm_id: Optional[str] = None,
    current_token_hash: Optional[str] = None,
) -> None:
    """Verify current password then update to new hash.

    Revokes all sessions except the current one on success.
    Raises 400 if current_password is wrong.
    """
    from ..common.audit import log_audit_event

    async with UserAsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.id == user_id, User.is_active == True)  # noqa: E712
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        if not verify_password(current_password, user.password_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect")

        if verify_password(new_password, user.password_hash):
            raise HTTPException(status_code=400, detail="New password must be different from your current password")

        user.password_hash = get_password_hash(new_password)

        # Revoke all sessions except the current one so compromised sessions are invalidated
        sessions_result = await session.execute(
            select(RefreshSession).where(
                RefreshSession.user_id == user_id,
                RefreshSession.revoked_at.is_(None),
            )
        )
        now = datetime.now(timezone.utc)
        revoked_count = 0
        for rs in sessions_result.scalars().all():
            if current_token_hash and rs.token_hash == current_token_hash:
                continue
            rs.revoked_at = now
            revoked_count += 1

        await session.commit()

    if firm_id:
        await log_audit_event(
            firm_id=firm_id,
            action="security.password_changed",
            user_id=user_id,
            resource_type="user",
            resource_id=user_id,
            metadata={"sessions_revoked": revoked_count},
        )


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

async def list_active_sessions(user_id: str, current_token_hash: Optional[str] = None) -> SessionListResponse:
    """Return all non-revoked, non-expired sessions for the user."""
    now = datetime.now(timezone.utc)
    async with UserAsyncSessionLocal() as session:
        result = await session.execute(
            select(RefreshSession).where(
                RefreshSession.user_id == user_id,
                RefreshSession.revoked_at.is_(None),
                RefreshSession.expires_at > now,
            ).order_by(RefreshSession.created_at.desc())
        )
        sessions = result.scalars().all()

    items = [
        SessionItemResponse(
            id=s.id,
            created_at=s.created_at,
            expires_at=s.expires_at,
            ip_address=s.ip_address,
            user_agent=s.user_agent,
            is_current=(current_token_hash is not None and s.token_hash == current_token_hash),
        )
        for s in sessions
    ]
    return SessionListResponse(sessions=items)


async def revoke_session(
    user_id: str,
    session_id: str,
    current_token_hash: Optional[str] = None,
    firm_id: Optional[str] = None,
) -> None:
    """Revoke a specific session. Raises 400 if trying to revoke the current session."""
    from ..common.audit import log_audit_event

    async with UserAsyncSessionLocal() as session:
        result = await session.execute(
            select(RefreshSession).where(
                RefreshSession.id == session_id,
                RefreshSession.user_id == user_id,
            )
        )
        rs = result.scalar_one_or_none()
        if rs is None:
            raise HTTPException(status_code=404, detail="Session not found")

        if current_token_hash and rs.token_hash == current_token_hash:
            raise HTTPException(
                status_code=400,
                detail="Cannot revoke your current session. Use logout instead.",
            )

        rs.revoked_at = datetime.now(timezone.utc)
        await session.commit()

    if firm_id:
        await log_audit_event(
            firm_id=firm_id,
            action="security.session_revoked",
            user_id=user_id,
            resource_type="session",
            resource_id=session_id,
        )


async def revoke_all_sessions(
    user_id: str,
    current_token_hash: Optional[str] = None,
    firm_id: Optional[str] = None,
) -> int:
    """Revoke all sessions except the current one. Returns count of revoked sessions."""
    from ..common.audit import log_audit_event

    now = datetime.now(timezone.utc)
    async with UserAsyncSessionLocal() as session:
        result = await session.execute(
            select(RefreshSession).where(
                RefreshSession.user_id == user_id,
                RefreshSession.revoked_at.is_(None),
            )
        )
        sessions = result.scalars().all()

        count = 0
        for rs in sessions:
            if current_token_hash and rs.token_hash == current_token_hash:
                continue
            rs.revoked_at = now
            count += 1

        await session.commit()

    if firm_id and count > 0:
        await log_audit_event(
            firm_id=firm_id,
            action="security.all_sessions_revoked",
            user_id=user_id,
            resource_type="session",
            metadata={"count": count},
        )

    return count


# ---------------------------------------------------------------------------
# Billing summary
# ---------------------------------------------------------------------------

async def get_billing_summary(firm_id: str) -> BillingSummaryResponse:
    """Load firm billing overview: plan, status, seats, and portal URL."""
    async with UserAsyncSessionLocal() as session:
        result = await session.execute(select(Firm).where(Firm.id == firm_id))
        firm = result.scalar_one_or_none()
        if firm is None:
            raise HTTPException(status_code=404, detail="Firm not found")

        plan_name: Optional[str] = None
        if firm.plan_id:
            result = await session.execute(select(Plan).where(Plan.id == firm.plan_id))
            plan = result.scalar_one_or_none()
            if plan:
                plan_name = plan.name

        seat_count_result = await session.execute(
            select(sa_func.count(User.id)).where(
                User.firm_id == firm_id,
                User.is_active == True,  # noqa: E712
            )
        )
        seat_used = seat_count_result.scalar() or 0

    subscription_status = firm.subscription_status.value if firm.subscription_status else None

    portal_url: Optional[str] = None
    portal_url_error = False
    if firm.stripe_customer_id:
        try:
            from ..billing.service import create_billing_portal_session
            portal_url = await create_billing_portal_session(firm_id)
        except Exception as exc:
            logger.warning(f"[settings] could not create portal URL for firm {firm_id}: {exc}")
            portal_url_error = True

    return BillingSummaryResponse(
        plan_name=plan_name,
        subscription_status=subscription_status,
        seat_used=seat_used,
        seat_limit=firm.seat_limit,
        portal_url=portal_url,
        portal_url_error=portal_url_error,
    )


# ---------------------------------------------------------------------------
# Pending invitations
# ---------------------------------------------------------------------------

async def list_pending_invitations(firm_id: str) -> list[PendingInvitationResponse]:
    """Return all unexpired, unaccepted invitations for the firm."""
    now = datetime.now(timezone.utc)
    async with UserAsyncSessionLocal() as session:
        result = await session.execute(
            select(FirmInvitation).where(
                FirmInvitation.firm_id == firm_id,
                FirmInvitation.accepted_at.is_(None),
                FirmInvitation.expires_at > now,
            ).order_by(FirmInvitation.expires_at.asc())
        )
        invitations = result.scalars().all()

    return [
        PendingInvitationResponse(
            id=inv.id,
            email=inv.email,
            role=inv.role.value if hasattr(inv.role, "value") else inv.role,
            expires_at=inv.expires_at,
        )
        for inv in invitations
    ]


async def revoke_invitation(firm_id: str, invitation_id: str) -> None:
    """Delete a pending invitation (must belong to this firm)."""
    async with UserAsyncSessionLocal() as session:
        result = await session.execute(
            select(FirmInvitation).where(FirmInvitation.id == invitation_id)
        )
        invitation = result.scalar_one_or_none()
        if invitation is None:
            raise HTTPException(status_code=404, detail="Invitation not found")
        if invitation.firm_id != firm_id:
            raise HTTPException(status_code=403, detail="Invitation does not belong to this firm")
        if invitation.accepted_at is not None:
            raise HTTPException(status_code=400, detail="Cannot revoke an accepted invitation")

        await session.delete(invitation)
        await session.commit()


async def resend_invitation(firm_id: str, invitation_id: str, inviter: User) -> PendingInvitationResponse:
    """Refresh an invitation's expiry and re-send the invite email."""
    async with UserAsyncSessionLocal() as session:
        result = await session.execute(
            select(FirmInvitation).where(FirmInvitation.id == invitation_id)
        )
        invitation = result.scalar_one_or_none()
        if invitation is None:
            raise HTTPException(status_code=404, detail="Invitation not found")
        if invitation.firm_id != firm_id:
            raise HTTPException(status_code=403, detail="Invitation does not belong to this firm")
        if invitation.accepted_at is not None:
            raise HTTPException(status_code=400, detail="Invitation has already been accepted")

        result = await session.execute(select(Firm).where(Firm.id == firm_id))
        firm = result.scalar_one_or_none()
        if firm is None:
            raise HTTPException(status_code=404, detail="Firm not found")

        # Refresh the expiry window
        invitation.expires_at = datetime.now(timezone.utc) + timedelta(hours=48)
        # Regenerate the token so old link is invalidated
        invitation.token = str(uuid.uuid4())
        await session.commit()
        await session.refresh(invitation)

    inviter_name = f"{inviter.first_name or ''} {inviter.last_name or ''}".strip() or inviter.email
    await send_invite_email(
        to_email=invitation.email,
        inviter_name=inviter_name,
        firm_name=firm.name,
        invite_token=invitation.token,
    )

    return PendingInvitationResponse(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role.value if hasattr(invitation.role, "value") else invitation.role,
        expires_at=invitation.expires_at,
    )


# ---------------------------------------------------------------------------
# Member role change (admin ↔ member)
# ---------------------------------------------------------------------------

async def change_member_role(
    firm_id: str,
    target_user_id: str,
    new_role: str,
    actor_id: str,
) -> User:
    """Change a firm member's role between 'admin' and 'member'.

    Guardrails:
    - Cannot change your own role.
    - Cannot target the firm_owner.
    - Only 'admin' and 'member' are valid targets (firm_owner via transfer-ownership only).
    - Permissions are reset to role defaults on change.
    """
    from ..common.audit import log_audit_event
    from ..permissions.constants import ROLE_DEFAULT_PERMISSIONS

    if new_role not in ("admin", "member"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'member'.")

    if target_user_id == actor_id:
        raise HTTPException(status_code=400, detail="You cannot change your own role.")

    async with UserAsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.id == target_user_id, User.firm_id == firm_id)
        )
        target = result.scalar_one_or_none()
        if target is None:
            raise HTTPException(status_code=404, detail="User not found in this firm.")

        role_val = target.role.value if hasattr(target.role, "value") else target.role
        if role_val == "firm_owner":
            raise HTTPException(status_code=403, detail="Cannot change the firm owner's role. Use transfer-ownership instead.")

        target.role = UserRole(new_role)
        target.permissions = ROLE_DEFAULT_PERMISSIONS.get(new_role, [])
        await session.commit()
        await session.refresh(target)

    await log_audit_event(
        firm_id=firm_id,
        action="member.role_changed",
        user_id=actor_id,
        resource_type="user",
        resource_id=target_user_id,
        metadata={"new_role": new_role},
    )

    return target


# ---------------------------------------------------------------------------
# User access toggle (enable / disable login)
# ---------------------------------------------------------------------------

async def set_user_access(
    firm_id: str,
    target_user_id: str,
    is_active: bool,
    actor_id: str,
) -> None:
    """Enable or disable a firm member's ability to log in.

    Guardrails:
    - Cannot toggle your own account.
    - Cannot disable the firm_owner.
    - Target must belong to the same firm.
    - On disable: all existing sessions are revoked immediately.
    """
    from ..common.audit import log_audit_event

    if target_user_id == actor_id:
        raise HTTPException(status_code=400, detail="You cannot change your own access.")

    async with UserAsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.id == target_user_id, User.firm_id == firm_id)
        )
        target = result.scalar_one_or_none()
        if target is None:
            raise HTTPException(status_code=404, detail="User not found in this firm.")

        role_val = target.role.value if hasattr(target.role, "value") else target.role
        if role_val == "firm_owner":
            raise HTTPException(status_code=403, detail="Cannot change access for the firm owner.")

        target.is_active = is_active

        if not is_active:
            # Revoke all active sessions so the user is immediately logged out
            sessions_result = await session.execute(
                select(RefreshSession).where(
                    RefreshSession.user_id == target_user_id,
                    RefreshSession.revoked_at.is_(None),
                )
            )
            now = datetime.now(timezone.utc)
            for rs in sessions_result.scalars().all():
                rs.revoked_at = now

        await session.commit()

    await log_audit_event(
        firm_id=firm_id,
        action="member.access_enabled" if is_active else "member.access_disabled",
        user_id=actor_id,
        resource_type="user",
        resource_id=target_user_id,
        metadata={"is_active": is_active},
    )


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

async def list_audit_log(
    firm_id: str,
    action: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    limit: int = 50,
    offset: int = 0,
) -> AuditLogResponse:
    """Paginated firm audit log with optional filters."""
    async with UserAsyncSessionLocal() as session:
        base_query = select(AuditLog).where(AuditLog.firm_id == firm_id)

        if action:
            base_query = base_query.where(AuditLog.action == action)
        if actor_user_id:
            base_query = base_query.where(AuditLog.user_id == actor_user_id)
        if from_date:
            base_query = base_query.where(AuditLog.created_at >= from_date)
        if to_date:
            base_query = base_query.where(AuditLog.created_at <= to_date)

        count_result = await session.execute(
            select(sa_func.count()).select_from(base_query.subquery())
        )
        total = count_result.scalar() or 0

        result = await session.execute(
            base_query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
        )
        logs = result.scalars().all()

        # Batch-load actor emails for logs that have a user_id
        user_ids = {log.user_id for log in logs if log.user_id}
        email_map: dict[str, str] = {}
        if user_ids:
            users_result = await session.execute(
                select(User.id, User.email).where(User.id.in_(user_ids))
            )
            email_map = {row.id: row.email for row in users_result}

    items = [
        AuditLogItem(
            id=log.id,
            action=log.action,
            actor_email=email_map.get(log.user_id) if log.user_id else None,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            metadata=log.event_data,
            created_at=log.created_at,
        )
        for log in logs
    ]

    return AuditLogResponse(items=items, total=total, limit=limit, offset=offset)
