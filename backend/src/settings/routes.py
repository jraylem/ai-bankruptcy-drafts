"""Settings API routes — Phase 4.

All endpoints live under /api/settings/...

Auth patterns:
  - get_current_firm_user   → any authenticated firm member
  - require_permission(MANAGE_MEMBERS) → firm_owner + admin only
"""

import hashlib
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Annotated, Optional

from ..auth.models import User
from ..common.dependencies import get_current_firm_user
from ..permissions.constants import Permission, ROLE_DISPLAY_NAMES
from ..permissions.dependencies import require_permission
from . import service
from .schemas import (
    AuditLogResponse,
    BillingSummaryResponse,
    FirmSettingsResponse,
    FirmSettingsUpdate,
    MemberRoleResponse,
    MemberRoleUpdate,
    PasswordChangeRequest,
    PendingInvitationResponse,
    SessionListResponse,
    SessionRevokeResponse,
    UserAccessResponse,
    UserAccessToggle,
    UserPermissionsResponse,
    UserSettingsResponse,
    UserSettingsUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["Settings"])


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# User preferences
# ---------------------------------------------------------------------------

@router.get("/user", response_model=UserSettingsResponse)
async def get_user_settings(
    current_user: User = Depends(get_current_firm_user),
):
    """Return user preferences (notification toggles, theme). Creates defaults on first call."""
    return await service.get_or_create_user_settings(current_user.id)


@router.patch("/user", response_model=UserSettingsResponse)
async def patch_user_settings(
    body: UserSettingsUpdate,
    current_user: User = Depends(get_current_firm_user),
):
    """Update user preferences. Only provided fields are updated."""
    return await service.update_user_settings(current_user.id, body)


# ---------------------------------------------------------------------------
# Firm configuration — admin/owner only
# ---------------------------------------------------------------------------

@router.get("/firm", response_model=FirmSettingsResponse)
async def get_firm_settings(
    current_user: User = Depends(require_permission(Permission.MANAGE_MEMBERS)),
):
    """Return firm configuration flags and Firm metadata. Admin/owner only."""
    return await service.get_or_create_firm_settings(current_user.firm_id)


@router.patch("/firm", response_model=FirmSettingsResponse)
async def patch_firm_settings(
    body: FirmSettingsUpdate,
    current_user: User = Depends(require_permission(Permission.MANAGE_MEMBERS)),
):
    """Update firm configuration. Admin/owner only."""
    return await service.update_firm_settings(current_user.firm_id, body, actor_id=current_user.id)


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

@router.get("/permissions", response_model=UserPermissionsResponse)
async def get_user_permissions(
    current_user: User = Depends(get_current_firm_user),
):
    """Return the current user's role, display name, and permissions list."""
    role_str = current_user.role.value if hasattr(current_user.role, "value") else (current_user.role or "member")
    role_display = ROLE_DISPLAY_NAMES.get(role_str, role_str.replace("_", " ").title())
    permissions = current_user.permissions or []
    return UserPermissionsResponse(
        role=role_str,
        role_display=role_display,
        permissions=permissions,
    )


# ---------------------------------------------------------------------------
# Password change
# ---------------------------------------------------------------------------

@router.post("/password", status_code=200)
async def change_password(
    body: PasswordChangeRequest,
    request: Request,
    current_user: User = Depends(get_current_firm_user),
):
    """Change the current user's password. Requires current password verification.

    All sessions except the current one are revoked on success.
    """
    raw_refresh = request.cookies.get("refresh_token")
    current_hash = _hash_token(raw_refresh) if raw_refresh else None
    await service.change_password(
        user_id=current_user.id,
        current_password=body.current_password,
        new_password=body.new_password,
        firm_id=current_user.firm_id,
        current_token_hash=current_hash,
    )
    return {"message": "Password updated successfully"}


# ---------------------------------------------------------------------------
# Security — sessions
# ---------------------------------------------------------------------------

@router.get("/security/sessions", response_model=SessionListResponse)
async def list_sessions(
    request: Request,
    current_user: User = Depends(get_current_firm_user),
):
    """List all active sessions for the current user. Marks the current session."""
    raw_refresh = request.cookies.get("refresh_token")
    current_hash = _hash_token(raw_refresh) if raw_refresh else None
    return await service.list_active_sessions(current_user.id, current_token_hash=current_hash)


@router.delete("/security/sessions/{session_id}", response_model=SessionRevokeResponse)
async def revoke_session(
    session_id: str,
    request: Request,
    current_user: User = Depends(get_current_firm_user),
):
    """Revoke a specific session (logs out that device). Cannot revoke your current session."""
    raw_refresh = request.cookies.get("refresh_token")
    current_hash = _hash_token(raw_refresh) if raw_refresh else None
    await service.revoke_session(
        user_id=current_user.id,
        session_id=session_id,
        current_token_hash=current_hash,
        firm_id=current_user.firm_id,
    )
    return SessionRevokeResponse(message="Session revoked", session_id=session_id)


@router.post("/security/sessions/revoke-all", status_code=200)
async def revoke_all_sessions(
    request: Request,
    current_user: User = Depends(get_current_firm_user),
):
    """Revoke all sessions except the current one (logs out all other devices)."""
    raw_refresh = request.cookies.get("refresh_token")
    current_hash = _hash_token(raw_refresh) if raw_refresh else None
    count = await service.revoke_all_sessions(
        user_id=current_user.id,
        current_token_hash=current_hash,
        firm_id=current_user.firm_id,
    )
    return {"message": f"Revoked {count} session(s)", "count": count}


@router.get("/security/2fa")
async def get_2fa_status(
    current_user: User = Depends(get_current_firm_user),
):
    """2FA status — stub for future implementation."""
    return {"enabled": False}


# ---------------------------------------------------------------------------
# Billing summary — admin/owner only
# ---------------------------------------------------------------------------

@router.get("/billing-summary", response_model=BillingSummaryResponse)
async def get_billing_summary(
    current_user: User = Depends(require_permission(Permission.MANAGE_MEMBERS)),
):
    """Return billing overview: plan, subscription status, seat usage, portal URL."""
    return await service.get_billing_summary(current_user.firm_id)


# ---------------------------------------------------------------------------
# Pending invitations — admin/owner only
# ---------------------------------------------------------------------------

@router.get("/firm/invitations", response_model=list[PendingInvitationResponse])
async def list_invitations(
    current_user: User = Depends(require_permission(Permission.MANAGE_MEMBERS)),
):
    """List all pending (unexpired, unaccepted) invitations for the firm."""
    return await service.list_pending_invitations(current_user.firm_id)


@router.delete("/firm/invitations/{invitation_id}", status_code=200)
async def revoke_invitation(
    invitation_id: str,
    current_user: User = Depends(require_permission(Permission.MANAGE_MEMBERS)),
):
    """Delete a pending invitation so the invite link is no longer usable."""
    await service.revoke_invitation(current_user.firm_id, invitation_id)
    return {"message": "Invitation revoked"}


@router.post("/firm/invitations/{invitation_id}/resend", response_model=PendingInvitationResponse)
async def resend_invitation(
    invitation_id: str,
    current_user: User = Depends(require_permission(Permission.MANAGE_MEMBERS)),
):
    """Refresh an invitation's expiry window and resend the invite email."""
    return await service.resend_invitation(current_user.firm_id, invitation_id, current_user)


# ---------------------------------------------------------------------------
# Member role change — admin/owner only
# ---------------------------------------------------------------------------

@router.patch("/firm/members/{user_id}/role", response_model=MemberRoleResponse)
async def change_member_role(
    user_id: str,
    body: MemberRoleUpdate,
    current_user: User = Depends(require_permission(Permission.MANAGE_MEMBERS)),
):
    """Change a firm member's role between 'admin' and 'member'. Admin/owner only.

    Permissions are reset to role defaults on change.
    Cannot target the firm owner (use /firms/transfer-ownership instead).
    """
    updated = await service.change_member_role(
        firm_id=current_user.firm_id,
        target_user_id=user_id,
        new_role=body.role,
        actor_id=current_user.id,
    )
    role_str = updated.role.value if hasattr(updated.role, "value") else updated.role
    return MemberRoleResponse(
        user_id=updated.id,
        role=role_str,
        role_display=ROLE_DISPLAY_NAMES.get(role_str, role_str.replace("_", " ").title()),
    )


# ---------------------------------------------------------------------------
# Member access toggle — admin/owner only
# ---------------------------------------------------------------------------

@router.patch("/firm/members/{user_id}/access", response_model=UserAccessResponse)
async def toggle_member_access(
    user_id: str,
    body: UserAccessToggle,
    current_user: User = Depends(require_permission(Permission.MANAGE_MEMBERS)),
):
    """Enable or disable a firm member's ability to log in. Admin/owner only.

    Disabling immediately revokes all active sessions for that user.
    Cannot target the firm owner or your own account.
    """
    await service.set_user_access(
        firm_id=current_user.firm_id,
        target_user_id=user_id,
        is_active=body.is_active,
        actor_id=current_user.id,
    )
    return UserAccessResponse(user_id=user_id, is_active=body.is_active)


# ---------------------------------------------------------------------------
# Audit log — admin/owner only
# ---------------------------------------------------------------------------

@router.get("/firm/activity", response_model=AuditLogResponse)
async def get_firm_activity(
    action: Annotated[Optional[str], Query(description="Filter by action type, e.g. 'member.invited'")] = None,
    actor_user_id: Annotated[Optional[str], Query(description="Filter by actor user ID")] = None,
    from_date: Annotated[Optional[datetime], Query(description="Filter events on or after this datetime (ISO 8601)")] = None,
    to_date: Annotated[Optional[datetime], Query(description="Filter events on or before this datetime (ISO 8601)")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    current_user: User = Depends(require_permission(Permission.MANAGE_MEMBERS)),
):
    """Paginated firm activity/audit log. Admin/owner only."""
    if from_date and to_date and from_date >= to_date:
        raise HTTPException(status_code=400, detail="from_date must be before to_date")
    return await service.list_audit_log(
        firm_id=current_user.firm_id,
        action=action,
        actor_user_id=actor_user_id,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
    )
