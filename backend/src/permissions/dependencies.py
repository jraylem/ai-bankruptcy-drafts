"""Permission-checking FastAPI dependency factory.

Usage:
    from src.permissions.dependencies import require_permission
    from src.permissions.constants import Permission

    @router.get("/dashboard/analytics")
    async def get_analytics(
        user=Depends(require_permission(Permission.ANALYTICS))
    ):
        ...

firm_owner and admin roles bypass the permission check implicitly.
member role is evaluated against user.permissions (JSONB list).
"""

from fastapi import Depends, HTTPException
from ..auth.models import User
from ..common.dependencies import get_current_firm_user
from .constants import PRIVILEGED_ROLES


def require_permission(permission: str):
    """Return a FastAPI dependency callable that enforces the given permission."""

    async def _check(user: User = Depends(get_current_firm_user)) -> User:
        if user.role in PRIVILEGED_ROLES:
            return user
        user_perms: list = user.permissions or []
        if permission not in user_perms:
            raise HTTPException(
                status_code=403,
                detail=f"Permission required: {permission}",
            )
        return user

    return _check
