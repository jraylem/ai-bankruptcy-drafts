"""Pydantic schemas for the Settings module — Phase 4."""

import re
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class UserSettingsUpdate(BaseModel):
    notification_email: Optional[bool] = None
    notification_inapp: Optional[bool] = None
    theme: Optional[Literal["light", "dark", "system"]] = None
    notify_motion_approved: Optional[bool] = None
    notify_motion_rejected: Optional[bool] = None


_DOMAIN_RE = re.compile(
    r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
)


class FirmSettingsUpdate(BaseModel):
    allow_member_invites: Optional[bool] = None
    motion_approval_required: Optional[bool] = None
    allowed_domain: Optional[str] = None
    enable_chat_rooms: Optional[bool] = None
    enable_motion_comments: Optional[bool] = None
    paywall_enabled: Optional[bool] = None

    @field_validator("allowed_domain")
    @classmethod
    def validate_domain(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return v
        if not _DOMAIN_RE.match(v):
            raise ValueError("Must be a valid domain format (e.g. lawfirm.com)")
        return v.lower()


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class UserSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    notification_email: bool
    notification_inapp: bool
    theme: str
    notify_motion_approved: bool = True
    notify_motion_rejected: bool = True
    email_verified: Optional[bool] = None
    updated_at: Optional[datetime] = None


class FirmSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    firm_id: str
    allow_member_invites: bool
    motion_approval_required: bool
    enable_chat_rooms: bool = True
    enable_motion_comments: bool = True
    paywall_enabled: bool = True
    updated_at: Optional[datetime] = None
    # From Firm model
    allowed_domain: Optional[str] = None
    onboarding_status: Optional[str] = None


class UserPermissionsResponse(BaseModel):
    role: str
    role_display: str
    permissions: list[str]


class SessionItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: Optional[datetime] = None
    expires_at: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    is_current: bool = False


class SessionListResponse(BaseModel):
    sessions: list[SessionItemResponse]


class SessionRevokeResponse(BaseModel):
    message: str
    session_id: str


class BillingSummaryResponse(BaseModel):
    plan_name: Optional[str] = None
    subscription_status: Optional[str] = None
    seat_used: int
    seat_limit: int
    portal_url: Optional[str] = None
    portal_url_error: bool = False


class PendingInvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    role: str
    expires_at: datetime


class MemberRoleUpdate(BaseModel):
    role: str  # "admin" | "member"


class MemberRoleResponse(BaseModel):
    user_id: str
    role: str
    role_display: str


class UserAccessToggle(BaseModel):
    is_active: bool


class UserAccessResponse(BaseModel):
    user_id: str
    is_active: bool


class AuditLogItem(BaseModel):
    id: str
    action: str
    actor_email: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    created_at: datetime


class AuditLogResponse(BaseModel):
    items: list[AuditLogItem]
    total: int
    limit: int
    offset: int
