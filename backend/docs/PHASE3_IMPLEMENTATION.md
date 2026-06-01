# Phase 3 — Firm Management: Detailed Implementation Plan

**Branch:** `feat/paywall-phase3`
**Last Updated:** 2026-05-15
**Parallel with:** Phase 2 (no runtime imports between them)

---

## Pre-Start Checklist

- [x] All Phase 1 migrations run against `user_db` and `chat_db`
- [x] `firms`, `plans`, `firm_invitations` tables exist in `user_db`
- [x] `firm_id` on `sessions`, `pdf_documents`, `chat_threads`, `motion_draft_logs`, `user_activity_logs` in `chat_db`
- [x] `onboarding_status` column exists on `firms` table
- [x] `src/auth/models.py` — all User paywall columns present
- [x] `src/permissions/constants.py` — complete
- [x] `src/permissions/dependencies.py` — complete
- [x] `src/permissions/__init__.py` — exports filled
- [x] `src/firms/models.py` — Firm, Plan, FirmInvitation present
- [x] `src/firms/__init__.py` — exports filled
- [x] `src/common/__init__.py` — `get_current_firm_user` exported
- [x] `src/auth/routes.py /refresh` — includes `firm_id` + `role` in token

---

## What Is Already Done

| Item | Location |
|---|---|
| `firm_id` on all chatbot models | `src/chatbot/models.py` |
| JWT includes `firm_id` + `role` in login | `src/auth/service.py` |
| JWT includes `firm_id` + `role` in refresh | `src/auth/routes.py` |
| `get_current_firm_user()` dependency | `src/common/dependencies.py` |
| `get_current_firm_user` exported | `src/common/__init__.py` |
| `UserRole` enum (firm_owner, admin, member) | `src/auth/models.py` |
| All User paywall columns | `src/auth/models.py` |
| All Phase 1 DB migrations | `migrations/` |
| `Permission`, `Role`, `require_permission()` | `src/permissions/` |
| `Firm`, `Plan`, `FirmInvitation` ORM classes | `src/firms/models.py` |
| Firms mapper registered in app | `src/main.py:30` |

---

## Phase 2 Coordination

Phase 3 has **zero runtime imports from `src/billing/`**.

| Coordination point | Detail |
|---|---|
| `Plan` model ownership | Lives in `src/firms/models.py`; Phase 2 billing imports it from there |
| Phase 2 writes to `Firm` | Webhooks update `subscription_status`, `is_active`, `plan_id` — no Phase 3 code changes needed |
| Phase 2 calls Phase 3 email functions | `send_payment_failed_email()` and `send_subscription_canceled_email()` exist in Phase 3's `src/notifications/email.py` |

**Phase 2 safety:** All `Firm` fields Phase 2 owns (`stripe_customer_id`, `plan_id`, `stripe_price_id`) are nullable. Phase 3 routes work correctly with these as `None`. `subscription_status` defaults to `trialing`.

---

## Domain Policy Decision

**Decision: Option B — No domain restriction. Invite any email.**

Law firms may use Gmail, Outlook, or any email provider. Domain restriction would break these cases. The firm's identity is its **name** (set during firm creation), not its email domain.

Security is enforced by:
- Invitation token: UUID v4, single-use, 48h expiry
- `firm_id` isolation: every DB query scoped to `current_user.firm_id`
- `get_current_firm_user()` cross-validates JWT `firm_id` against DB on every request

**`allowed_domain` column added as nullable on `Firm`** (for Phase 4 opt-in):

If a firm later wants to enforce that only `@vanhornlawgroup.com` emails can be invited, they set `allowed_domain = "vanhornlawgroup.com"` via firm settings. Default is `None` — no restriction. This requires a migration now (see Migration section below) and enforcement logic in `invite_member()`.

---

## Migration Required Before Starting

`allowed_domain` is a new column added to `firms` — it does not exist in the DB yet. Run this before implementing service.py.

**Create:** `migrations/add_allowed_domain_to_firms.py`

```python
"""
Migration: add allowed_domain to firms table.

Adds nullable allowed_domain VARCHAR column to firms.
When set, invite_member() restricts invitations to that domain only.
Default: NULL (no restriction — any email can be invited).

Usage:
    docker compose exec backend uv run python migrations/add_allowed_domain_to_firms.py
"""

import asyncio, sys
from pathlib import Path
script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from sqlalchemy import text
from src.auth.database import user_engine, UserAsyncSessionLocal
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def run_migration():
    async with UserAsyncSessionLocal() as session:
        try:
            result = await session.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'firms' AND column_name = 'allowed_domain'
                )
            """))
            if result.scalar():
                logger.info("Column firms.allowed_domain already exists — skipping")
            else:
                logger.info("Adding column: firms.allowed_domain")
                await session.execute(text(
                    "ALTER TABLE firms ADD COLUMN allowed_domain VARCHAR"
                ))
            await session.commit()
            logger.info("Migration committed successfully.")
        except Exception as e:
            await session.rollback()
            logger.error(f"Migration failed: {e}")
            raise


async def main():
    logger.info("=" * 60)
    logger.info("Migration: add_allowed_domain_to_firms")
    logger.info("=" * 60)
    try:
        await run_migration()
        code = 0
    except Exception:
        code = 1
    finally:
        await user_engine.dispose()
    logger.info("=" * 60)
    sys.exit(code)


if __name__ == "__main__":
    asyncio.run(main())
```

**Run before implementing service.py:**
```bash
docker compose exec backend uv run python migrations/add_allowed_domain_to_firms.py
```

**Also update `src/firms/models.py` `Firm` class** — add after `seat_limit`:
```python
allowed_domain = Column(String, nullable=True)
# e.g. "vanhornlawgroup.com" — when set, invites restricted to this domain
# NULL = no restriction (default, works for Gmail and any provider)
```

---

## Build Order

```
Migration  →  add_allowed_domain_to_firms.py (run first)
Step 1     →  src/firms/models.py — add allowed_domain column
Step 2     →  src/firms/schemas.py — all Pydantic request/response models (NEW)
Step 3     →  src/firms/service.py — 7 functions (email stubbed)
Step 4     →  src/firms/routes.py — 10 endpoints
Step 5     →  src/main.py — register firms router
────── email infra (parallel with Steps 1–5) ──────────────────
Step 6     →  pyproject.toml — add resend>=0.6.0
Step 7     →  src/config.py — EMAIL_API_KEY, EMAIL_FROM_ADDRESS, FRONTEND_URL
Step 8     →  src/notifications/__init__.py
Step 9     →  src/notifications/email.py — 8 functions
Step 10    →  src/notifications/templates/ — 8 HTML + _base.html
────── wire email (after Steps 3 and 9 both done) ─────────────
Step 11    →  src/firms/service.py — replace email stubs
```

---

## Step 1 — Update `src/firms/models.py`

Add `allowed_domain` to the `Firm` class after `seat_limit`:

```python
allowed_domain = Column(String, nullable=True)
# When set: invite_member() rejects emails not matching this domain.
# NULL: no domain restriction (default). Works for Gmail, Outlook, custom domains.
```

---

## Step 2 — `src/firms/schemas.py`

**This file is not in the original plan docs but is required.** Every route needs Pydantic models for request validation and response serialization. This is consistent with how the rest of the project works (`src/schema.py` for auth).

```python
"""Pydantic schemas for firms routes — request validation and response serialization."""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class FirmCreateRequest(BaseModel):
    firm_name: str


class FirmUpdateRequest(BaseModel):
    name: str


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: str                        # "firm_owner" | "admin" | "member"
    permissions: list[str] = []      # defaults to ROLE_DEFAULT_PERMISSIONS[role] in service


class AcceptInvitationRequest(BaseModel):
    token: str
    password: Optional[str] = None   # required for new users, ignored for existing


class UpdatePermissionsRequest(BaseModel):
    permissions: list[str]


class TransferOwnershipRequest(BaseModel):
    new_owner_id: str


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class FirmResponse(BaseModel):
    id: str
    name: str
    owner_email: str
    subscription_status: str
    plan_id: Optional[str]
    seat_limit: int
    onboarding_status: str
    is_active: bool
    allowed_domain: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class FirmCreateResponse(BaseModel):
    """Returned by POST /api/firms — includes fresh JWT with firm_id."""
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
    role_display: str                # "Superadmin" | "Admin" | "Member"
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


class AcceptInvitationResponse(BaseModel):
    """Returned by POST /api/firms/invite/accept — frontend stores immediately."""
    access_token: str
    token_type: str = "bearer"


class OnboardingStatusResponse(BaseModel):
    onboarding_status: str
```

---

## Step 3 — `src/firms/service.py`

All functions use `UserAsyncSessionLocal` from `src/auth/database.py`.
No imports from `src/billing/`.
Import `UserRole` from `src/auth/models` — not from `src/firms/models`.

```python
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import select, func as sa_func
from ..auth.database import UserAsyncSessionLocal
from ..auth.models import User, UserRole
from ..auth.auth import create_access_token, get_password_hash
from ..permissions.constants import Permission, ROLE_DEFAULT_PERMISSIONS
from .models import Firm, FirmInvitation, OnboardingStatus, SubscriptionStatus
```

---

### `create_firm(owner_user_id, firm_name) → tuple[Firm, str]`

```
1. Load user — raise 400 if user.firm_id is not None (already in a firm)
2. Create Firm:
     name = firm_name
     owner_email = user.email
     subscription_status = trialing
     is_active = True
     onboarding_status = pending
     allowed_domain = None  (no restriction by default)
3. Set user.firm_id = firm.id
       user.role = UserRole.firm_owner
       user.permissions = Permission.ALL
4. Commit
5. Issue JWT: create_access_token({"sub": user.id, "firm_id": firm.id, "role": user.role})
6. Return (firm, token)
```

**Why re-issue JWT:** `register_new_user()` creates users with `firm_id=None`.
`get_current_user()` raises 401 if `firm_id` is missing. Without a fresh token here,
the user cannot reach any protected route after firm creation.

---

### `invite_member(firm_id, inviter_user_id, email, role, permissions) → FirmInvitation`

```
1. Load firm — raise 404 if not found
2. Load inviter — raise 403 if inviter.role == "member"
3. Count active members — raise 400 if count >= firm.seat_limit
4. Domain check (only if firm.allowed_domain is set):
     invitee_domain = email.split("@")[-1]
     if invitee_domain != firm.allowed_domain → raise 400
       detail: f"Invitations restricted to @{firm.allowed_domain} addresses"
5. Check for existing unexpired invitation to this email — raise 400 if one exists
6. Create FirmInvitation:
     token = uuid4()
     expires_at = now + 48 hours
     permissions = permissions if provided, else ROLE_DEFAULT_PERMISSIONS[role]
7. If first invitation ever sent to this firm:
     set firm.onboarding_status = completed
8. Commit
9. # TODO Step 11: await send_invite_email(...)
10. Return invitation
```

---

### `accept_invitation(token, password) → tuple[User, str]`

```
1. Look up FirmInvitation by token — raise 404 if not found
2. Raise 400 if invitation.accepted_at is not None   (already used)
3. Raise 400 if invitation.expires_at < now           (expired)
4. Load firm — raise 400 if firm.is_active is False
5. Check if user with invitation.email already exists:

   EXISTING USER PATH:
     Raise 400 if existing_user.firm_id is not None  (already in a firm)
     Set user.firm_id = firm.id
         user.role = invitation.role
         user.permissions = invitation.permissions
         user.invited_by = invitation.invited_by
         user.invitation_accepted_at = now

   NEW USER PATH:
     Raise 400 if password is None or empty
     Create User:
         email = invitation.email (lowercased)
         password_hash = get_password_hash(password)
         firm_id = firm.id
         role = invitation.role
         permissions = invitation.permissions
         invited_by = invitation.invited_by
         invitation_accepted_at = now
         is_active = True

6. Mark invitation.accepted_at = now
7. Commit
8. Issue JWT: create_access_token({"sub": user.id, "firm_id": firm.id, "role": user.role})
9. # TODO Step 11: await send_invitation_accepted_email(to inviter)
10. Return (user, token)
```

---

### `update_member_permissions(admin_id, target_id, permissions) → User`

```
1. Load admin — raise 403 if admin.role == "member"
2. Load target — raise 404 if not found or target.firm_id != admin.firm_id
3. Raise 403 if target.role == "firm_owner"   (cannot edit owner permissions)
4. Set target.permissions = permissions
5. Commit, return target
```

---

### `remove_member(admin_id, target_id) → None`

```
1. Load admin — raise 403 if admin.role == "member"
2. Load target — raise 404 if not found or target.firm_id != admin.firm_id
3. Raise 400 if target.role == "firm_owner"   (cannot remove the owner)
4. Raise 400 if admin_id == target_id          (cannot remove yourself)
5. Set target.is_active = False
6. Commit
```

---

### `transfer_ownership(current_owner_id, new_owner_id) → None`

```
1. Load current owner — raise 403 if role != "firm_owner"
2. Load new owner — raise 404 if not found or different firm_id
3. Raise 400 if new_owner_id == current_owner_id
4. Raise 400 if new_owner.is_active is False
5. current_owner.role = UserRole.admin
   new_owner.role = UserRole.firm_owner
   new_owner.permissions = Permission.ALL
6. Commit
```

---

### `get_firm_members(firm_id) → list[User]`

```
Returns all active users where user.firm_id == firm_id, ordered by created_at asc.
```

---

## Step 4 — `src/firms/routes.py`

Router prefix: `/api/firms` — **no** `/api` prefix in `main.py` include (router owns its full path).

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from ..auth.auth import get_current_user
from ..auth.database import UserAsyncSessionLocal
from ..auth.models import User
from ..common.dependencies import get_current_firm_user
from ..permissions.constants import Permission, ROLE_DISPLAY_NAMES
from ..permissions.dependencies import require_permission
from .models import Firm
from .schemas import (
    FirmCreateRequest, FirmUpdateRequest, FirmCreateResponse, FirmResponse,
    InviteMemberRequest, InvitationResponse, AcceptInvitationRequest,
    AcceptInvitationResponse, UpdatePermissionsRequest, MemberResponse,
    TransferOwnershipRequest, OnboardingStatusResponse,
)
from . import service

router = APIRouter(prefix="/api/firms", tags=["firms"])
```

### Endpoints

| Method | Path | Auth | Response Schema |
|---|---|---|---|
| `POST` | `/api/firms` | `get_current_user` | `FirmCreateResponse` |
| `GET` | `/api/firms/me` | `get_current_firm_user` | `FirmResponse` |
| `PATCH` | `/api/firms/me` | `require_permission(MANAGE_MEMBERS)` | `FirmResponse` |
| `GET` | `/api/firms/members` | `require_permission(MANAGE_MEMBERS)` | `list[MemberResponse]` |
| `POST` | `/api/firms/invite` | `require_permission(MANAGE_MEMBERS)` | `InvitationResponse` |
| `POST` | `/api/firms/invite/accept` | Public | `AcceptInvitationResponse` |
| `PATCH` | `/api/firms/members/{user_id}/permissions` | `require_permission(MANAGE_MEMBERS)` | `MemberResponse` |
| `DELETE` | `/api/firms/members/{user_id}` | `require_permission(MANAGE_MEMBERS)` | `{"message": str}` |
| `POST` | `/api/firms/transfer-ownership` | `get_current_firm_user` | `{"message": str}` |
| `GET` | `/api/firms/onboarding-status` | `get_current_firm_user` | `OnboardingStatusResponse` |

**Key notes:**
- `POST /api/firms` uses `get_current_user` (not `get_current_firm_user`) — user has no firm yet
- `GET /api/firms/members` maps `role` → `role_display` using `ROLE_DISPLAY_NAMES`
- `POST /api/firms/invite/accept` is public — no auth header required
- `POST /api/firms/transfer-ownership` — firm_owner check is enforced inside `service.transfer_ownership()`

---

## Step 5 — Register Router in `src/main.py`

```python
from .firms.routes import router as firms_router
app.include_router(firms_router)  # no prefix= — router owns /api/firms
```

---

## Step 6–10 — Email Infrastructure

### Step 6 — `pyproject.toml`

Add to `dependencies`:
```toml
"resend>=0.6.0",
```

### Step 7 — `src/config.py`

Add:
```python
# Email / Notifications (Resend)
EMAIL_API_KEY: str
EMAIL_FROM_ADDRESS: str   # onboarding@resend.dev for dev; verified domain for prod
FRONTEND_URL: str
```

Add to `.env`:
```
EMAIL_API_KEY=re_xxxxxxxxxxxx
EMAIL_FROM_ADDRESS=onboarding@resend.dev
FRONTEND_URL=http://localhost:3000
```

**Note on `onboarding@resend.dev`:** No domain verification required.
Emails deliver only to the Resend account owner's address — enough for dev testing.
Swap `EMAIL_FROM_ADDRESS` when domain is verified. Zero code changes needed.

### Step 8 — `src/notifications/__init__.py`

```python
from .email import (
    send_invite_email,
    send_invitation_accepted_email,
    send_password_reset_email,
    send_subscription_activated_email,
    send_subscription_canceled_email,
    send_payment_failed_email,
    send_motion_approved_email,
    send_motion_rejected_email,
)
```

### Step 9 — `src/notifications/email.py`

Jinja2 is already available via `docxtpl` — no new package needed.

```python
import resend
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from ..config import settings

resend.api_key = settings.EMAIL_API_KEY

_jinja_env = Environment(
    loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
    autoescape=True,
)

def _render(template_name: str, context: dict) -> str:
    return _jinja_env.get_template(template_name).render(**context)
```

**8 functions:**

| Function | Subject | Template | Called by |
|---|---|---|---|
| `send_invite_email(to, inviter_name, firm_name, token)` | `You've been invited to {firm_name}` | `invite.html` | Phase 3 `invite_member()` |
| `send_invitation_accepted_email(to, member_name, firm_name)` | `{member_name} joined your firm` | `invite_accepted.html` | Phase 3 `accept_invitation()` |
| `send_password_reset_email(to, reset_token)` | `Reset your BKDrafts password` | `password_reset.html` | Phase 4 auth |
| `send_subscription_activated_email(to, firm_name, plan_name)` | `Subscription active` | `subscription_activated.html` | Phase 2 webhook |
| `send_subscription_canceled_email(to, firm_name)` | `Subscription canceled` | `subscription_canceled.html` | Phase 2 webhook |
| `send_payment_failed_email(to, firm_name, portal_url)` | `Action required: payment failed` | `payment_failed.html` | Phase 2 webhook |
| `send_motion_approved_email(to, motion_type, case_number)` | `Motion approved` | `motion_approved.html` | Phase 4 collaboration |
| `send_motion_rejected_email(to, motion_type, case_number, reason)` | `Motion rejected` | `motion_rejected.html` | Phase 4 collaboration |

### Step 10 — `src/notifications/templates/`

```
src/notifications/templates/
├── _base.html                   ← shared branded header + footer
├── invite.html
├── invite_accepted.html
├── password_reset.html
├── subscription_activated.html
├── subscription_canceled.html
├── payment_failed.html
├── motion_approved.html
└── motion_rejected.html
```

`_base.html` wraps all templates via Jinja2 `{% extends "_base.html" %}`.

---

## Step 11 — Wire Email Into Service

After Step 9 is done, replace stubs in `src/firms/service.py`:

**In `invite_member()`:**
```python
from ..notifications.email import send_invite_email

send_invite_email(
    to_email=email,
    inviter_name=f"{inviter.first_name or ''} {inviter.last_name or ''}".strip() or inviter.email,
    firm_name=firm.name,
    invite_token=invitation.token,
)
```

**In `accept_invitation()`:**
```python
from ..notifications.email import send_invitation_accepted_email

inviter = await session.get(User, invitation.invited_by)
if inviter:
    send_invitation_accepted_email(
        to_email=inviter.email,
        new_member_name=f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email,
        firm_name=firm.name,
    )
```

---

## When Phase 2 Lands

No Phase 3 files change. Phase 2 integrates by:

```python
# src/billing/service.py
from ..firms.models import Plan   # ← only coordination needed

# src/billing/webhooks.py
from ..notifications.email import send_payment_failed_email, send_subscription_canceled_email
```

---

## Completion Checklist

```
Migration:
  [ ] migrations/add_allowed_domain_to_firms.py — created and run

Step 1 — Model update:
  [ ] src/firms/models.py — allowed_domain column added

Step 2 — Schemas (NEW):
  [ ] src/firms/schemas.py — all 10 Pydantic models

Step 3 — Service:
  [ ] src/firms/service.py — create_firm()
  [ ] src/firms/service.py — invite_member() (email stubbed)
  [ ] src/firms/service.py — accept_invitation() (email stubbed)
  [ ] src/firms/service.py — update_member_permissions()
  [ ] src/firms/service.py — remove_member()
  [ ] src/firms/service.py — transfer_ownership()
  [ ] src/firms/service.py — get_firm_members()

Step 4 — Routes:
  [ ] src/firms/routes.py — POST /api/firms
  [ ] src/firms/routes.py — GET /api/firms/me
  [ ] src/firms/routes.py — PATCH /api/firms/me
  [ ] src/firms/routes.py — GET /api/firms/members
  [ ] src/firms/routes.py — POST /api/firms/invite
  [ ] src/firms/routes.py — POST /api/firms/invite/accept
  [ ] src/firms/routes.py — PATCH /api/firms/members/{id}/permissions
  [ ] src/firms/routes.py — DELETE /api/firms/members/{id}
  [ ] src/firms/routes.py — POST /api/firms/transfer-ownership
  [ ] src/firms/routes.py — GET /api/firms/onboarding-status

Step 5 — App registration:
  [ ] src/main.py — firms router registered

Step 6–10 — Email infrastructure:
  [ ] pyproject.toml — resend>=0.6.0
  [ ] src/config.py — EMAIL_API_KEY, EMAIL_FROM_ADDRESS, FRONTEND_URL
  [ ] .env — placeholder values
  [ ] src/notifications/__init__.py
  [ ] src/notifications/email.py — 8 functions
  [ ] src/notifications/templates/_base.html
  [ ] src/notifications/templates/invite.html
  [ ] src/notifications/templates/invite_accepted.html
  [ ] src/notifications/templates/password_reset.html
  [ ] src/notifications/templates/subscription_activated.html
  [ ] src/notifications/templates/subscription_canceled.html
  [ ] src/notifications/templates/payment_failed.html
  [ ] src/notifications/templates/motion_approved.html
  [ ] src/notifications/templates/motion_rejected.html

Step 11 — Wire email:
  [ ] src/firms/service.py invite_member() — replace TODO stub
  [ ] src/firms/service.py accept_invitation() — replace TODO stub

Phase 2 coordination (when Phase 2 merges):
  [ ] src/billing/service.py — import Plan from src.firms.models
  [ ] src/billing/webhooks.py — import email functions from src.notifications.email
```
