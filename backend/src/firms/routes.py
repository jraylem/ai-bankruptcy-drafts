"""Firm management routes — Phase 3.

Router prefix: /firms
Registered in main.py as: app.include_router(firms_router, prefix="/api")
Final paths: /api/firms/...
"""

from fastapi import APIRouter, Depends, Request, Response
from ..auth.auth import get_current_user_pre_firm, set_auth_cookies
from ..auth.models import User, UserRole
from ..common.dependencies import get_current_firm_user
from ..permissions.constants import Permission, ROLE_DISPLAY_NAMES
from ..permissions.dependencies import require_permission
from ..schema import LoginResponse, UserResponse
from .schemas import (
    AcceptInvitationRequest,
    FirmCreateRequest,
    FirmCreateResponse,
    FirmPublicResponse,
    FirmResponse,
    FirmUpdateRequest,
    InviteMemberRequest,
    InvitationResponse,
    MemberResponse,
    OnboardingStatusResponse,
    TransferOwnershipRequest,
    UpdatePermissionsRequest,
)
from . import service

router = APIRouter(prefix="/firms", tags=["firms"])


@router.post("", response_model=FirmCreateResponse)
async def create_firm(
    body: FirmCreateRequest,
    current_user: User = Depends(get_current_user_pre_firm),
):
    """Create a firm for a newly registered user.

    Uses get_current_user_pre_firm (not get_current_firm_user) because
    the user has no firm_id yet. Returns a fresh JWT — frontend must
    swap the stored token immediately.
    """
    firm, token = await service.create_firm(
        user_id=current_user.id,
        firm_name=body.firm_name,
        address=body.firm_address,
        firm_type=body.firm_type,
        contact_number=body.firm_contact_number,
    )
    return FirmCreateResponse(
        id=firm.id,
        name=firm.name,
        owner_email=firm.owner_email,
        onboarding_status=firm.onboarding_status,
        subscription_status=firm.subscription_status,
        is_active=firm.is_active,
        access_token=token,
    )


@router.get("/me")
async def get_firm(
    current_user: User = Depends(get_current_firm_user),
):
    """Return the current user's firm details.

    Admin and firm_owner receive the full FirmResponse including billing and ownership fields.
    Regular members receive FirmPublicResponse with basic firm identity only.
    """
    firm = await service.get_firm(current_user.firm_id)
    if current_user.role in (UserRole.firm_owner, UserRole.admin):
        return FirmResponse.model_validate(firm)
    return FirmPublicResponse.model_validate(firm)


@router.patch("/me", response_model=FirmResponse)
async def update_firm(
    body: FirmUpdateRequest,
    current_user: User = Depends(require_permission(Permission.MANAGE_MEMBERS)),
):
    """Update firm profile fields. Admin and firm_owner only."""
    firm = await service.update_firm(
        firm_id=current_user.firm_id,
        name=body.name,
        address=body.address,
        firm_type=body.firm_type,
        contact_number=body.contact_number,
    )
    return FirmResponse.model_validate(firm)


@router.get("/members", response_model=list[MemberResponse])
async def list_members(
    current_user: User = Depends(require_permission(Permission.MANAGE_MEMBERS)),
):
    """List all active firm members with roles and permissions. Admin and firm_owner only."""
    members = await service.get_firm_members(current_user.firm_id)
    return [
        MemberResponse(
            id=m.id,
            email=m.email,
            first_name=m.first_name,
            last_name=m.last_name,
            role=m.role,
            role_display=ROLE_DISPLAY_NAMES.get(m.role, str(m.role)),
            permissions=m.permissions,
            is_active=m.is_active,
            invitation_accepted_at=m.invitation_accepted_at,
        )
        for m in members
    ]


@router.post("/invite", response_model=InvitationResponse)
async def invite_member(
    body: InviteMemberRequest,
    current_user: User = Depends(require_permission(Permission.MANAGE_MEMBERS)),
):
    """Send a firm invitation. Admin and firm_owner only."""
    invitation = await service.invite_member(
        firm_id=current_user.firm_id,
        inviter_id=current_user.id,
        email=body.email,
        role=body.role,
        permissions=body.permissions or None,
    )
    return InvitationResponse.model_validate(invitation)


@router.post("/invite/accept", response_model=LoginResponse)
async def accept_invitation(body: AcceptInvitationRequest, request: Request, response: Response):
    """Accept a firm invitation. Public — no auth required.

    Sets HttpOnly auth cookies and returns LoginResponse so the frontend
    session is established immediately without a separate login step.
    """
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    user, access_token, refresh_token = await service.accept_invitation(
        token=body.token,
        password=body.password,
        first_name=body.first_name,
        last_name=body.last_name,
        ip_address=ip,
        user_agent=ua,
    )
    set_auth_cookies(response, access_token, refresh_token)
    firm = await service.get_firm(user.firm_id)
    onboarding_status = firm.onboarding_status or "pending"
    user_response = UserResponse.from_orm(user).model_copy(update={"onboarding_status": onboarding_status})
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=user_response,
    )


@router.patch("/members/{user_id}/permissions", response_model=MemberResponse)
async def update_member_permissions(
    user_id: str,
    body: UpdatePermissionsRequest,
    current_user: User = Depends(require_permission(Permission.MANAGE_MEMBERS)),
):
    """Update a member's permissions. Admin and firm_owner only."""
    updated = await service.update_member_permissions(
        admin_id=current_user.id,
        target_id=user_id,
        permissions=body.permissions,
    )
    return MemberResponse(
        id=updated.id,
        email=updated.email,
        first_name=updated.first_name,
        last_name=updated.last_name,
        role=updated.role,
        role_display=ROLE_DISPLAY_NAMES.get(updated.role, str(updated.role)),
        permissions=updated.permissions,
        is_active=updated.is_active,
        invitation_accepted_at=updated.invitation_accepted_at,
    )


@router.delete("/members/{user_id}")
async def remove_member(
    user_id: str,
    current_user: User = Depends(require_permission(Permission.MANAGE_MEMBERS)),
):
    """Deactivate a firm member (soft delete). Admin and firm_owner only."""
    await service.remove_member(admin_id=current_user.id, target_id=user_id)
    return {"message": "Member removed successfully"}


@router.post("/transfer-ownership")
async def transfer_ownership(
    body: TransferOwnershipRequest,
    current_user: User = Depends(get_current_firm_user),
):
    """Transfer firm_owner role to another member. firm_owner check enforced in service."""
    await service.transfer_ownership(
        current_owner_id=current_user.id,
        new_owner_id=body.new_owner_id,
    )
    return {"message": "Ownership transferred successfully"}


@router.get("/onboarding-status", response_model=OnboardingStatusResponse)
async def get_onboarding_status(
    current_user: User = Depends(get_current_firm_user),
):
    """Return the current firm's onboarding status."""
    firm = await service.get_firm(current_user.firm_id)
    return OnboardingStatusResponse(onboarding_status=firm.onboarding_status)
