"""Pydantic schemas for firms routes — request validation and response serialization."""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import field_validator
from pydantic import BaseModel, EmailStr


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class FirmCreateRequest(BaseModel):
    firm_name: str
    firm_address: Optional[str] = None
    firm_type: Optional[str] = None
    firm_contact_number: Optional[str] = None


class FirmUpdateRequest(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    firm_type: Optional[str] = None
    contact_number: Optional[str] = None


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: str = "member"              # "admin" | "member" (firm_owner not assignable via invite)
    permissions: list[str] = []       # defaults to ROLE_DEFAULT_PERMISSIONS[role] in service


class AcceptInvitationRequest(BaseModel):
    token: str
    password: Optional[str] = None    # required for new users, ignored for existing
    first_name: Optional[str] = None  # required for new users
    last_name: Optional[str] = None   # optional

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def title_case_name(cls, v):
        if v is None:
            return v
        return v.strip().title()


class UpdatePermissionsRequest(BaseModel):
    permissions: list[str]


class TransferOwnershipRequest(BaseModel):
    new_owner_id: str


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class FirmPublicResponse(BaseModel):
    """Returned for regular members — basic firm identity only, no billing or admin fields."""
    id: str
    name: str
    address: Optional[str] = None
    firm_type: Optional[str] = None
    contact_number: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True


class FirmResponse(BaseModel):
    id: str
    name: str
    owner_email: str
    subscription_status: str
    plan_id: Optional[str]
    seat_limit: int
    onboarding_status: str
    is_active: bool
    created_at: datetime
    address: Optional[str] = None
    firm_type: Optional[str] = None
    contact_number: Optional[str] = None

    class Config:
        from_attributes = True


class FirmCreateResponse(BaseModel):
    """Returned by POST /api/firms — includes fresh JWT so frontend swaps token immediately."""
    id: str
    name: str
    owner_email: str
    onboarding_status: str
    subscription_status: str
    is_active: bool
    access_token: str
    token_type: str = "bearer"


class MemberResponse(BaseModel):
    id: str
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    role: Optional[str]
    role_display: str                 # "Superadmin" | "Admin" | "Member"
    permissions: Optional[list[str]]
    is_active: bool
    invitation_accepted_at: Optional[datetime]

    class Config:
        from_attributes = True


class InvitationResponse(BaseModel):
    id: str
    email: str
    role: str
    expires_at: datetime

    class Config:
        from_attributes = True


class OnboardingStatusResponse(BaseModel):
    onboarding_status: str
