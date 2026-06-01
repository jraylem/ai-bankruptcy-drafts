"""Admin routes for user management (list all users, approve/reject accounts)."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from ..schema import UserResponse
from .auth import get_current_user
from .database import UserAsyncSessionLocal
from .models import User
from . import service as auth_service

router = APIRouter(prefix="/admin", tags=["Admin"])


def _require_firm_owner(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "firm_owner":
        raise HTTPException(status_code=403, detail="Superadmin access required")
    return current_user


class UserAcceptUpdate(BaseModel):
    is_accepted: bool


class WaitlistUserResponse(BaseModel):
    id: str
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    created_at: datetime
    approval_token_expires_at: Optional[datetime] = None

    class Config:
        from_attributes = True


@router.get("/users", response_model=list[UserResponse])
async def list_users(_: User = Depends(_require_firm_owner)):
    """Return all registered users with their acceptance status."""
    async with UserAsyncSessionLocal() as session:
        result = await session.execute(select(User))
        return result.scalars().all()


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user_acceptance(
    user_id: str,
    body: UserAcceptUpdate,
    _: User = Depends(_require_firm_owner),
):
    """Set is_accepted for a user. Pass {"is_accepted": true} to approve."""
    async with UserAsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        user.is_accepted = body.is_accepted
        await session.commit()
        await session.refresh(user)
        return user


# ---------------------------------------------------------------------------
# Waitlist management
# ---------------------------------------------------------------------------

@router.get("/waitlist", response_model=list[WaitlistUserResponse])
async def list_waitlist(_: User = Depends(_require_firm_owner)):
    """Return all users pending approval — email verified but not yet accepted."""
    users = await auth_service.get_waitlist()
    return [WaitlistUserResponse.model_validate(u) for u in users]


@router.post("/waitlist/{user_id}/approve", response_model=WaitlistUserResponse)
async def approve_waitlist_user(
    user_id: str,
    _: User = Depends(_require_firm_owner),
):
    """Approve a waitlisted user. Sets is_accepted=True and sends approval email."""
    user = await auth_service.approve_user(user_id)
    return WaitlistUserResponse.model_validate(user)


@router.post("/waitlist/{user_id}/deny", response_model=WaitlistUserResponse)
async def deny_waitlist_user(
    user_id: str,
    _: User = Depends(_require_firm_owner),
):
    """Deny a waitlisted user. Sends rejection email."""
    user = await auth_service.deny_user(user_id)
    return WaitlistUserResponse.model_validate(user)
