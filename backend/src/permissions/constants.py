"""Permission constants and role definitions for the paywall / multi-tenancy system.

Internal DB/code values use the identifiers defined here.
UI display mapping:
  firm_owner → "Superadmin"
  admin      → "Admin"
  member     → "Member"
"""

import enum


class Permission:
    ANALYTICS       = "analytics"
    MOTION_STUDIO   = "motion_studio"
    CASE_MANAGEMENT = "case_management"
    ADMIN_DASHBOARD = "admin_dashboard"
    APPROVE_MOTIONS = "approve_motions"
    MANAGE_MEMBERS  = "manage_members"

    ALL = [
        ANALYTICS,
        MOTION_STUDIO,
        CASE_MANAGEMENT,
        ADMIN_DASHBOARD,
        APPROVE_MOTIONS,
        MANAGE_MEMBERS,
    ]


class Role(str, enum.Enum):
    firm_owner = "firm_owner"
    admin      = "admin"
    member     = "member"


# Display names returned by APIs (frontend-facing)
ROLE_DISPLAY_NAMES: dict[str, str] = {
    Role.firm_owner: "Superadmin",
    Role.admin:      "Admin",
    Role.member:     "Member",
}

# Roles that have implicit full access — no permission check needed
PRIVILEGED_ROLES: set[str] = {Role.firm_owner, Role.admin}

# Default permissions assigned per role on invitation acceptance.
# firm_owner and admin get all; member gets none by default.
ROLE_DEFAULT_PERMISSIONS: dict[str, list[str]] = {
    Role.firm_owner: Permission.ALL,
    Role.admin:      Permission.ALL,
    Role.member:     [],
}
