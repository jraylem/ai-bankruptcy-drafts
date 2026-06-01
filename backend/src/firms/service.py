"""Business logic for firm management — Phase 3.

No imports from src/billing/ — safe to run while Phase 2 is on a separate branch.
Always import UserRole from src/auth/models, not from src/firms/models.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import HTTPException
from sqlalchemy import select, func as sa_func
from sqlalchemy.exc import IntegrityError
from ..auth.database import UserAsyncSessionLocal
from ..auth.models import User, UserRole
from ..auth.auth import create_access_token, create_refresh_token, get_password_hash
from ..permissions.constants import Permission, ROLE_DEFAULT_PERMISSIONS
from .models import Firm, FirmInvitation, OnboardingStatus, SubscriptionStatus
from ..notifications.email import send_invite_email, send_invitation_accepted_email
from ..common.audit import log_audit_event


async def create_firm(
    user_id: str,
    firm_name: str,
    address: Optional[str] = None,
    firm_type: Optional[str] = None,
    contact_number: Optional[str] = None,
) -> tuple[Firm, str]:
    """Create a firm for a newly registered user and issue a fresh JWT with firm_id.

    Called by: POST /api/firms (via routes.py)
               src/auth/service.register_new_user() — JWT discarded there; real token
               comes from POST /api/auth/verify-email after email verification.

    Why re-issue JWT: register_new_user() creates users with firm_id=None.
    get_current_user() raises 401 when firm_id is missing, so the frontend
    must swap to the returned token immediately after firm creation.
    """
    async with UserAsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        if user.firm_id is not None:
            raise HTTPException(status_code=409, detail="User already belongs to a firm")

        existing_firm = await session.execute(
            select(Firm).where(sa_func.lower(Firm.name) == firm_name.strip().lower())
        )
        if existing_firm.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="A firm with this name already exists. Please choose a different name.")

        firm = Firm(
            name=firm_name,
            owner_email=user.email,
            subscription_status=SubscriptionStatus.trialing,
            is_active=True,
            onboarding_status=OnboardingStatus.pending,
            address=address,
            firm_type=firm_type,
            contact_number=contact_number,
        )
        session.add(firm)

        user.firm_id = firm.id
        user.role = UserRole.firm_owner
        user.permissions = list(Permission.ALL)

        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(status_code=409, detail="Email already registered")
        await session.refresh(firm)
        await session.refresh(user)

        token = create_access_token(data={
            "sub": user.id,
            "firm_id": firm.id,
            "role": user.role,
        })

        return firm, token


async def get_firm(firm_id: str) -> Firm:
    """Fetch a firm by ID.

    Called by: GET /api/firms/me, GET /api/firms/onboarding-status (via routes.py)
    """
    async with UserAsyncSessionLocal() as session:
        result = await session.execute(select(Firm).where(Firm.id == firm_id))
        firm = result.scalar_one_or_none()
        if firm is None:
            raise HTTPException(status_code=404, detail="Firm not found")
        return firm


async def update_firm(
    firm_id: str,
    name: Optional[str] = None,
    address: Optional[str] = None,
    firm_type: Optional[str] = None,
    contact_number: Optional[str] = None,
) -> Firm:
    """Update firm profile fields. All parameters are optional (PATCH semantics).

    Called by: PATCH /api/firms/me (via routes.py)
    """
    async with UserAsyncSessionLocal() as session:
        result = await session.execute(select(Firm).where(Firm.id == firm_id))
        firm = result.scalar_one_or_none()
        if firm is None:
            raise HTTPException(status_code=404, detail="Firm not found")
        if name is not None:
            firm.name = name
        if address is not None:
            firm.address = address
        if firm_type is not None:
            firm.firm_type = firm_type
        if contact_number is not None:
            firm.contact_number = contact_number
        if firm.onboarding_status == OnboardingStatus.pending:
            firm.onboarding_status = OnboardingStatus.completed
        await session.commit()
        await session.refresh(firm)
        return firm


async def invite_member(
    firm_id: str,
    inviter_id: str,
    email: str,
    role: str,
    permissions: Optional[list[str]] = None,
) -> FirmInvitation:
    """Create a firm invitation and (later) send invite email.

    Called by: POST /api/firms/invite (via routes.py)
    """
    async with UserAsyncSessionLocal() as session:
        result = await session.execute(select(Firm).where(Firm.id == firm_id))
        firm = result.scalar_one_or_none()
        if firm is None:
            raise HTTPException(status_code=404, detail="Firm not found")

        result = await session.execute(select(User).where(User.id == inviter_id))
        inviter = result.scalar_one_or_none()
        if inviter is None:
            raise HTTPException(status_code=403, detail="Insufficient permissions to invite members")

        if inviter.role == UserRole.member:
            # Members can only invite if the firm has explicitly enabled it
            from ..settings.models import FirmSettings
            fs_result = await session.execute(
                select(FirmSettings).where(FirmSettings.firm_id == firm_id)
            )
            firm_settings = fs_result.scalar_one_or_none()
            if not firm_settings or not firm_settings.allow_member_invites:
                raise HTTPException(status_code=403, detail="Insufficient permissions to invite members")

        result = await session.execute(
            select(sa_func.count(User.id)).where(
                User.firm_id == firm_id,
                User.is_active == True,
            )
        )
        seat_count = result.scalar()
        if seat_count >= firm.seat_limit:
            raise HTTPException(status_code=403, detail="Firm has reached its seat limit")

        now = datetime.now(timezone.utc)
        normalized_email = email.lower().strip()

        # Expire any pending invitations for this email+firm so the old link
        # immediately shows "Invite is already expired" if the user tries it.
        old_result = await session.execute(
            select(FirmInvitation).where(
                FirmInvitation.firm_id == firm_id,
                FirmInvitation.email == normalized_email,
                FirmInvitation.accepted_at == None,  # noqa: E711
            )
        )
        for old_invite in old_result.scalars().all():
            old_invite.expires_at = now

        resolved_permissions = permissions if permissions else ROLE_DEFAULT_PERMISSIONS.get(role, [])

        invitation = FirmInvitation(
            firm_id=firm_id,
            email=normalized_email,
            role=role,
            permissions=resolved_permissions,
            invited_by=inviter_id,
            expires_at=now + timedelta(hours=48),
        )
        session.add(invitation)

        if firm.onboarding_status == OnboardingStatus.pending:
            firm.onboarding_status = OnboardingStatus.completed

        await session.commit()
        await session.refresh(invitation)

        await send_invite_email(
            to_email=normalized_email,
            inviter_name=f"{inviter.first_name or ''} {inviter.last_name or ''}".strip() or inviter.email,
            firm_name=firm.name,
            invite_token=invitation.token,
        )

        await log_audit_event(
            firm_id=firm_id,
            action="member.invited",
            user_id=inviter_id,
            resource_type="invitation",
            resource_id=invitation.id,
            metadata={"email": normalized_email, "role": role},
        )

        return invitation


async def accept_invitation(
    token: str,
    password: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> tuple[User, str, str]:
    """Accept an invitation. Creates or updates the user and returns a JWT for immediate login.

    Called by: POST /api/firms/invite/accept — public, no auth required (via routes.py)
    """
    async with UserAsyncSessionLocal() as session:
        now = datetime.now(timezone.utc)

        result = await session.execute(
            select(FirmInvitation).where(FirmInvitation.token == token)
        )
        invitation = result.scalar_one_or_none()
        if invitation is None:
            raise HTTPException(status_code=410, detail="Invite is already expired")
        if invitation.accepted_at is not None:
            raise HTTPException(status_code=409, detail="Invitation has already been used")

        expires_at = invitation.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < now:
            raise HTTPException(status_code=410, detail="Invitation has expired")

        result = await session.execute(select(Firm).where(Firm.id == invitation.firm_id))
        firm = result.scalar_one_or_none()
        if firm is None or not firm.is_active:
            raise HTTPException(status_code=400, detail="Firm is inactive or not found")

        result = await session.execute(
            select(User).where(User.email == invitation.email)
        )
        existing_user = result.scalar_one_or_none()

        if existing_user:
            if existing_user.firm_id is not None:
                raise HTTPException(status_code=409, detail="User already belongs to a firm")
            existing_user.firm_id = firm.id
            existing_user.role = UserRole(invitation.role) if not isinstance(invitation.role, UserRole) else invitation.role
            existing_user.permissions = invitation.permissions
            existing_user.invited_by = invitation.invited_by
            existing_user.invitation_accepted_at = now
            # Decision 3: invitation email proves email ownership — mark as verified
            existing_user.email_verified = True
            # Invited by an admin — pre-approved, no waitlist review needed
            existing_user.is_accepted = True
            user = existing_user
        else:
            if not password:
                raise HTTPException(status_code=400, detail="Password is required for new users")
            user = User(
                email=invitation.email,
                password_hash=get_password_hash(password),
                first_name=first_name,
                last_name=last_name,
                firm_id=firm.id,
                role=UserRole(invitation.role) if not isinstance(invitation.role, UserRole) else invitation.role,
                permissions=invitation.permissions,
                invited_by=invitation.invited_by,
                invitation_accepted_at=now,
                is_active=True,
                # Decision 3: invitation email proves email ownership — mark as verified
                email_verified=True,
                # Invited by an admin — pre-approved, no waitlist review needed
                is_accepted=True,
            )
            session.add(user)

        invitation.accepted_at = now

        await session.commit()
        await session.refresh(user)

        jwt_token = create_access_token(data={
            "sub": user.id,
            "firm_id": firm.id,
            "role": user.role,
        })
        refresh_token = await create_refresh_token(user.id, ip_address=ip_address, user_agent=user_agent)

        # Notify the inviter that the invitation was accepted
        result = await session.execute(
            select(User).where(User.id == invitation.invited_by)
        )
        inviter = result.scalar_one_or_none()
        if inviter:
            member_name = f"{user.first_name} {user.last_name}".strip() or user.email
            await send_invitation_accepted_email(
                to_email=inviter.email,
                new_member_name=member_name,
                firm_name=firm.name,
            )

        await log_audit_event(
            firm_id=firm.id,
            action="member.joined",
            user_id=user.id,
            resource_type="user",
            resource_id=user.id,
            metadata={"email": user.email, "role": invitation.role.value if hasattr(invitation.role, "value") else invitation.role},
        )

        return user, jwt_token, refresh_token


async def update_member_permissions(
    admin_id: str,
    target_id: str,
    permissions: list[str],
) -> User:
    """Update a firm member's permissions.

    Called by: PATCH /api/firms/members/{user_id}/permissions (via routes.py)
    """
    async with UserAsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == admin_id))
        admin = result.scalar_one_or_none()
        if admin is None or admin.role == UserRole.member:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        result = await session.execute(select(User).where(User.id == target_id))
        target = result.scalar_one_or_none()
        if target is None or target.firm_id != admin.firm_id:
            raise HTTPException(status_code=404, detail="Member not found")
        if target.role == UserRole.firm_owner:
            raise HTTPException(status_code=403, detail="Cannot edit firm owner permissions")

        target.permissions = permissions
        await session.commit()
        await session.refresh(target)
        return target


async def remove_member(admin_id: str, target_id: str) -> None:
    """Deactivate a firm member (soft delete).

    Called by: DELETE /api/firms/members/{user_id} (via routes.py)
    """
    async with UserAsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == admin_id))
        admin = result.scalar_one_or_none()
        if admin is None or admin.role == UserRole.member:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        result = await session.execute(select(User).where(User.id == target_id))
        target = result.scalar_one_or_none()
        if target is None or target.firm_id != admin.firm_id:
            raise HTTPException(status_code=404, detail="Member not found")
        if target.role == UserRole.firm_owner:
            raise HTTPException(status_code=403, detail="Cannot remove the firm owner")
        if admin_id == target_id:
            raise HTTPException(status_code=403, detail="Cannot remove yourself")

        target.is_active = False
        firm_id_for_audit = target.firm_id
        target_id_for_audit = target.id
        await session.commit()

    await log_audit_event(
        firm_id=firm_id_for_audit,
        action="member.removed",
        user_id=admin_id,
        resource_type="user",
        resource_id=target_id_for_audit,
    )


async def transfer_ownership(current_owner_id: str, new_owner_id: str) -> None:
    """Transfer firm_owner role to another active member.

    Called by: POST /api/firms/transfer-ownership (via routes.py)
    """
    async with UserAsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == current_owner_id))
        current_owner = result.scalar_one_or_none()
        if current_owner is None or current_owner.role != UserRole.firm_owner:
            raise HTTPException(status_code=403, detail="Only the firm owner can transfer ownership")

        result = await session.execute(select(User).where(User.id == new_owner_id))
        new_owner = result.scalar_one_or_none()
        if new_owner is None or new_owner.firm_id != current_owner.firm_id:
            raise HTTPException(status_code=404, detail="Member not found")
        if new_owner_id == current_owner_id:
            raise HTTPException(status_code=400, detail="Cannot transfer ownership to yourself")
        if not new_owner.is_active:
            raise HTTPException(status_code=400, detail="Cannot transfer ownership to an inactive member")

        current_owner.role = UserRole.admin
        new_owner.role = UserRole.firm_owner
        new_owner.permissions = list(Permission.ALL)
        await session.commit()


async def get_firm_members(firm_id: str) -> list[User]:
    """Return all active members of a firm ordered by join date.

    Called by: GET /api/firms/members (via routes.py)
    """
    async with UserAsyncSessionLocal() as session:
        result = await session.execute(
            select(User)
            .where(User.firm_id == firm_id, User.is_active == True)  # noqa: E712
            .order_by(User.created_at.asc())
        )
        return list(result.scalars().all())
