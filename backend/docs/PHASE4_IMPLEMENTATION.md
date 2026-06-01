# Phase 4 — Settings: Detailed Implementation Plan

**Branch:** `feat/phase-4-settings`
**Last Updated:** 2026-05-22
**Depends on:** Phase 3 (`feat/phase-3-firm-mgmt`) merged to main

> **Collaboration is already complete.**
> `src/collaboration/` (models, service, routes) and `migrations/add_collaboration_tables.py`
> all exist and are registered in `main.py`. Steps 9–15 from the original paywall plan are done.
> This document covers **Settings only**.

---

## Pre-Start Checklist

- [ ] Phase 3 branch merged and all firm management endpoints verified
- [ ] `src/firms/models.py` — `Firm`, `FirmInvitation`, `Plan` all present
- [ ] `src/notifications/email.py` — all 8 email functions present
- [ ] `src/billing/routes.py` — checkout, portal, subscription, plans registered
- [ ] `src/billing/service.py` — `get_subscription()`, `create_billing_portal_session()` callable
- [ ] `src/auth/models.py` — `RefreshSession` table present with `user_id`, `token_hash`, `expires_at`, `revoked_at`
- [ ] `src/permissions/constants.py` — `Permission`, `ROLE_DISPLAY_NAMES`, `ROLE_DEFAULT_PERMISSIONS` present
- [ ] `src/permissions/dependencies.py` — `require_permission()` dependency present
- [ ] `migrations/add_allowed_domain_to_firms.py` — already run against `user_db`

---

## What Is Already Done

| Item | Location |
|---|---|
| `RefreshSession` ORM model | `src/auth/models.py` |
| `revoke_refresh_token()` | `src/auth/auth.py` |
| `create_refresh_token()` | `src/auth/auth.py` |
| `verify_password()`, `get_password_hash()` | `src/auth/auth.py` |
| `Firm.allowed_domain` column | `src/firms/models.py` |
| `get_subscription()` service | `src/billing/service.py` |
| `create_billing_portal_session()` | `src/billing/service.py` |
| `Permission.ALL`, `MANAGE_MEMBERS` | `src/permissions/constants.py` |
| `require_permission()` dependency | `src/permissions/dependencies.py` |
| `send_motion_approved_email()` | `src/notifications/email.py` |
| `send_motion_rejected_email()` | `src/notifications/email.py` |
| `send_invite_email()` | `src/notifications/email.py` |
| `onboarding_status` on `Firm` | `src/firms/models.py` |
| `seat_limit` on `Firm` | `src/firms/models.py` |
| `FirmInvitation` with token/expiry | `src/firms/models.py` |

---

## Build Order

```
Step 1   →  migrations/add_settings_tables.py         (user_settings + firm_settings tables)
Step 2   →  migrations/add_session_metadata.py        (ip_address + user_agent on refresh_sessions)
Step 3   →  src/settings/__init__.py
Step 4   →  src/settings/models.py                    (UserSettings, FirmSettings)
Step 5   →  src/settings/schemas.py                   (all Pydantic request/response models)
Step 6   →  src/settings/service.py                   (all business logic)
Step 7   →  src/settings/routes.py                    (all 14 endpoints)
Step 8   →  src/main.py                               (register settings router)
────── Also required (auth updates for session metadata) ──────────────────
Step 2a  →  src/auth/models.py    — add ip_address, user_agent to RefreshSession
Step 2b  →  src/auth/auth.py      — create_refresh_token() accepts ip_address, user_agent
Step 2c  →  src/auth/routes.py    — /login, /refresh, /verify-email pass request metadata
```

---

## Step 1 — Migration: `add_settings_tables.py`

**File:** `migrations/add_settings_tables.py`
**Runs against:** `user_db`

### Tables to create

**`user_settings`**

| Column | Type | Notes |
|---|---|---|
| `user_id` | VARCHAR PK, FK → users | Primary key — one row per user |
| `notification_email` | BOOLEAN NOT NULL DEFAULT TRUE | Email notification toggle |
| `notification_inapp` | BOOLEAN NOT NULL DEFAULT TRUE | In-app notification toggle |
| `theme` | VARCHAR NOT NULL DEFAULT 'light' | UI theme preference |
| `updated_at` | TIMESTAMPTZ | Updated on every PATCH |

**`firm_settings`**

| Column | Type | Notes |
|---|---|---|
| `firm_id` | VARCHAR PK, FK → firms | Primary key — one row per firm |
| `allow_member_invites` | BOOLEAN NOT NULL DEFAULT FALSE | When TRUE, `member` role can also invite |
| `motion_approval_required` | BOOLEAN NOT NULL DEFAULT FALSE | When TRUE, motions need approval before finalization |
| `updated_at` | TIMESTAMPTZ | Updated on every PATCH |

**Run command:**
```bash
docker compose exec backend uv run python migrations/add_settings_tables.py
```

---

## Step 2 — Migration: `add_session_metadata.py`

**File:** `migrations/add_session_metadata.py`
**Runs against:** `user_db`

Adds two nullable columns to `refresh_sessions` so the sessions list in settings can show meaningful device/location info:

| Column | Type | Notes |
|---|---|---|
| `ip_address` | VARCHAR NULL | Populated from `request.client.host` on login/refresh |
| `user_agent` | VARCHAR NULL | Populated from `request.headers.get("user-agent")` |

**Also update:** `src/auth/auth.py` — `create_refresh_token()` to accept and store `ip_address` and `user_agent`.

**Also update:** `src/auth/routes.py` — `/login`, `/refresh`, `/verify-email` to pass `request.client.host` and `request.headers.get("user-agent")` into `create_refresh_token()`.

**Run command:**
```bash
docker compose exec backend uv run python migrations/add_session_metadata.py
```

---

## Step 3 — `src/settings/__init__.py`

```python
# intentionally empty — package marker
```

---

## Step 4 — `src/settings/models.py`

Import `Base` from `src/auth/models.py` (same `user_db`).

### `UserSettings`

```
__tablename__ = "user_settings"

user_id          String, PK, FK("users.id")
notification_email  Boolean, default=True, nullable=False
notification_inapp  Boolean, default=True, nullable=False
theme               String, default="light", nullable=False
updated_at          DateTime(timezone=True), onupdate=func.now()
```

### `FirmSettings`

```
__tablename__ = "firm_settings"

firm_id                  String, PK, FK("firms.id")
allow_member_invites     Boolean, default=False, nullable=False
motion_approval_required Boolean, default=False, nullable=False
updated_at               DateTime(timezone=True), onupdate=func.now()
```

---

## Step 5 — `src/settings/schemas.py`

### Request schemas

**`UserSettingsUpdate`**
```
notification_email:  Optional[bool]
notification_inapp:  Optional[bool]
theme:               Optional[str]      # "light" | "dark"
```

**`FirmSettingsUpdate`**
```
allow_member_invites:     Optional[bool]
motion_approval_required: Optional[bool]
allowed_domain:           Optional[str]   # updates Firm.allowed_domain (nullable)
```

**`PasswordChangeRequest`**
```
current_password: str
new_password:     str
```

### Response schemas

**`UserSettingsResponse`**
```
user_id:             str
notification_email:  bool
notification_inapp:  bool
theme:               str
updated_at:          Optional[datetime]

Config: from_attributes = True
```

**`FirmSettingsResponse`**
```
firm_id:                  str
allow_member_invites:     bool
motion_approval_required: bool
allowed_domain:           Optional[str]    # from Firm table, not FirmSettings
onboarding_status:        str              # from Firm table
updated_at:               Optional[datetime]

Config: from_attributes = True
```

**`UserPermissionsResponse`**
```
role:         Optional[str]   # internal value: "firm_owner" | "admin" | "member"
role_display: str             # "Superadmin" | "Admin" | "Member"
permissions:  list[str]       # e.g. ["analytics", "motion_studio", ...]
```

**`SessionItemResponse`**
```
id:           str
created_at:   datetime
expires_at:   datetime
ip_address:   Optional[str]
user_agent:   Optional[str]
is_current:   bool            # True if this session matches the current request token
```

**`SessionListResponse`**
```
sessions: list[SessionItemResponse]
```

**`BillingSummaryResponse`**
```
plan_name:           Optional[str]    # from Plan.name via Firm.plan_id
subscription_status: str              # from Firm.subscription_status
seat_used:           int              # COUNT(active users in firm)
seat_limit:          int              # from Firm.seat_limit
portal_url:          Optional[str]    # from create_billing_portal_session() — None if no Stripe customer
```

**`PendingInvitationResponse`**
```
id:         str
email:      str
role:       str
expires_at: datetime

Config: from_attributes = True
```

---

## Step 6 — `src/settings/service.py`

All functions use `UserAsyncSessionLocal` from `src/auth/database.py`.

### User Settings

#### `get_or_create_user_settings(user_id: str) → UserSettings`
```
SELECT UserSettings WHERE user_id = user_id
If not found:
    INSERT UserSettings(user_id=user_id) with all defaults
    Commit
Return settings
```

#### `update_user_settings(user_id: str, data: UserSettingsUpdate) → UserSettings`
```
settings = await get_or_create_user_settings(user_id)
Apply only non-None fields from data (PATCH semantics)
Set updated_at = now
Commit, refresh, return
```

---

### Firm Settings

#### `get_or_create_firm_settings(firm_id: str) → tuple[FirmSettings, Firm]`
```
SELECT FirmSettings WHERE firm_id = firm_id
If not found:
    INSERT FirmSettings(firm_id=firm_id) with all defaults
    Commit
SELECT Firm WHERE id = firm_id
Return (settings, firm)
```

#### `update_firm_settings(firm_id: str, data: FirmSettingsUpdate) → tuple[FirmSettings, Firm]`
```
settings, firm = await get_or_create_firm_settings(firm_id)

# Update FirmSettings fields
Apply only non-None fields from data (PATCH semantics)
settings.updated_at = now

# allowed_domain lives on Firm, not FirmSettings
If data.allowed_domain is not None:
    firm.allowed_domain = data.allowed_domain or None
    (empty string → None means "remove restriction")

Commit, refresh both, return
```

---

### Security

#### `change_password(user_id: str, current_password: str, new_password: str) → None`
```
Load user by user_id
If not found: raise 404
If not verify_password(current_password, user.password_hash): raise 400 "Incorrect current password"
user.password_hash = get_password_hash(new_password)
Commit
```

#### `list_active_sessions(user_id: str) → list[RefreshSession]`
```
SELECT RefreshSession
WHERE user_id = user_id
  AND revoked_at IS NULL
  AND expires_at > now
ORDER BY created_at DESC
```

#### `revoke_session(user_id: str, session_id: str) → None`
```
Load RefreshSession by id
If not found or session.user_id != user_id: raise 404 "Session not found"
If already revoked: raise 400 "Session already revoked"
session.revoked_at = now
Commit
```

#### `revoke_all_sessions(user_id: str, current_token_hash: str) → int`
```
SELECT all active RefreshSessions for user_id
For each session where session.token_hash != current_token_hash:
    session.revoked_at = now
Commit
Return count of revoked sessions
```

---

### Billing Summary

#### `get_billing_summary(firm_id: str) → dict`
```
Load Firm by firm_id (raise 404 if not found)
Load Plan via firm.plan_id (nullable)
Count active users: COUNT(User WHERE firm_id=firm_id AND is_active=True)
Load portal_url:
    Try: portal_url = await create_billing_portal_session(firm_id)
    Except: portal_url = None   (no Stripe customer yet — new firm)

Return {
    plan_name:           plan.name if plan else None,
    subscription_status: firm.subscription_status.value,
    seat_used:           count,
    seat_limit:          firm.seat_limit,
    portal_url:          portal_url,
}
```

---

### Pending Invitations

#### `list_pending_invitations(firm_id: str) → list[FirmInvitation]`
```
SELECT FirmInvitation
WHERE firm_id = firm_id
  AND accepted_at IS NULL
  AND expires_at > now
ORDER BY expires_at ASC
```

#### `revoke_invitation(firm_id: str, invitation_id: str) → None`
```
Load FirmInvitation by id
If not found or invitation.firm_id != firm_id: raise 404
If invitation.accepted_at is not None: raise 400 "Invitation already accepted"
DELETE the row (or set expires_at = now to soft-expire)
Commit
```

#### `resend_invitation(firm_id: str, invitation_id: str, inviter: User) → FirmInvitation`
```
Load FirmInvitation by id
If not found or invitation.firm_id != firm_id: raise 404
If invitation.accepted_at is not None: raise 400 "Invitation already accepted"
Refresh: invitation.expires_at = now + 48h
Commit
await send_invite_email(
    to_email=invitation.email,
    inviter_name=inviter.first_name or inviter.email,
    firm_name=firm.name,
    invite_token=invitation.token,
)
Return invitation
```

---

## Step 7 — `src/settings/routes.py`

**Router prefix:** `/settings`
**Registered in main.py with:** `prefix="/api"` → final paths: `/api/settings/...`

### Full Endpoint Table

| Method | Path | Auth | Service call | Notes |
|---|---|---|---|---|
| `GET` | `/settings/user` | `get_current_firm_user` | `get_or_create_user_settings` | User preferences |
| `PATCH` | `/settings/user` | `get_current_firm_user` | `update_user_settings` | PATCH semantics |
| `GET` | `/settings/firm` | `require_permission(MANAGE_MEMBERS)` | `get_or_create_firm_settings` | Includes `onboarding_status`, `allowed_domain` |
| `PATCH` | `/settings/firm` | `require_permission(MANAGE_MEMBERS)` | `update_firm_settings` | Can update `allowed_domain` |
| `GET` | `/settings/permissions` | `get_current_firm_user` | inline | Returns user's `role`, `role_display`, `permissions` |
| `POST` | `/settings/password` | `get_current_firm_user` | `change_password` | Validates current password |
| `GET` | `/settings/security/sessions` | `get_current_firm_user` | `list_active_sessions` | Marks current session with `is_current=True` |
| `DELETE` | `/settings/security/sessions/{session_id}` | `get_current_firm_user` | `revoke_session` | Cannot revoke current |
| `POST` | `/settings/security/sessions/revoke-all` | `get_current_firm_user` | `revoke_all_sessions` | Keeps current session alive |
| `GET` | `/settings/security/2fa` | `get_current_firm_user` | inline | Stub — returns `{ "enabled": false }` |
| `GET` | `/settings/billing-summary` | `require_permission(MANAGE_MEMBERS)` | `get_billing_summary` | No live Stripe call — DB only except portal URL |
| `GET` | `/settings/firm/invitations` | `require_permission(MANAGE_MEMBERS)` | `list_pending_invitations` | Unexpired + unaccepted only |
| `DELETE` | `/settings/firm/invitations/{id}` | `require_permission(MANAGE_MEMBERS)` | `revoke_invitation` | Cannot revoke accepted |
| `POST` | `/settings/firm/invitations/{id}/resend` | `require_permission(MANAGE_MEMBERS)` | `resend_invitation` | Resets 48h expiry, resends email |

### Identifying the current session

For `GET /settings/security/sessions` and `DELETE /settings/security/sessions/{id}`, the route needs the raw token hash to mark or protect the current session:

```python
# In the route, extract token from cookie or Bearer header
raw_token = request.cookies.get("access_token") or (credentials.credentials if credentials else None)
current_hash = hashlib.sha256(raw_token.encode()).hexdigest() if raw_token else None
```

Then `session.is_current = (session.token_hash == current_hash)` — note: this is the **access token** hash, not the refresh token hash. You may need to reconsider if you want to track the current **refresh** session instead (more accurate since access tokens are short-lived).

> **Design decision:** Store the current refresh token hash in the cookie and compare against `RefreshSession.token_hash` — this is more reliable since access tokens rotate less predictably.

---

## Step 8 — Register in `src/main.py`

```python
from .settings.routes import router as settings_router
app.include_router(settings_router, prefix="/api")
```

---

---

## Recommendations: Additional Settings (Based on Current Codebase)

These are not in the original plan but fit naturally with existing code:

### 1. `motion_approval_required` completes existing email infrastructure
`send_motion_approved_email()` and `send_motion_rejected_email()` in `notifications/email.py` are already written. Setting `FirmSettings.motion_approval_required = True` in Phase 4 gives the frontend a flag to surface. The actual approval workflow (a route that marks a motion as approved/rejected and fires the email) can be added in Phase 5 or separately — the email functions are ready.

### 2. `allow_member_invites` gates an existing code check
`invite_member()` in `firms/service.py` raises 403 when `inviter.role == UserRole.member`. Add a check: if `firm_settings.allow_member_invites is True`, skip the role check. Zero new infrastructure needed.

### 3. Pending invitation management (resend/revoke)
`FirmInvitation` has everything needed (`token`, `expires_at`, `accepted_at`). Adding the 3 invitation endpoints above covers a UX gap: admins currently have no way to see or cancel a pending invite after sending it.

### 4. `FirmSettingsResponse` should include `onboarding_status`
`Firm.onboarding_status` is already on the model. Including it in `GET /api/settings/firm` means the frontend only needs one call to get all firm configuration, instead of calling both `/api/firms/me` and `/api/settings/firm`.

### 5. Seat usage in billing summary is already queryable
The `COUNT(User WHERE firm_id=? AND is_active=True)` query is identical to the one in `invite_member()`. Reuse it — no new infrastructure, just one extra query in `get_billing_summary()`.

### 6. Session IP + user agent makes the sessions list actionable
Without IP/user agent, the sessions list just shows datetimes — not useful enough for users to know which session to revoke. Adding `ip_address` and `user_agent` to `RefreshSession` (Step 2 migration) requires passing `request` into `create_refresh_token()` at the three call sites: `/login`, `/refresh`, `/verify-email`.

---

## Completion Checklist

```
Migrations:
  [ ] migrations/add_settings_tables.py — created and run
  [ ] migrations/add_session_metadata.py — created and run

Step 3 — Package init:
  [ ] src/settings/__init__.py

Step 4 — Models:
  [ ] src/settings/models.py — UserSettings
  [ ] src/settings/models.py — FirmSettings

Step 5 — Schemas:
  [ ] src/settings/schemas.py — UserSettingsUpdate
  [ ] src/settings/schemas.py — FirmSettingsUpdate
  [ ] src/settings/schemas.py — PasswordChangeRequest
  [ ] src/settings/schemas.py — UserSettingsResponse
  [ ] src/settings/schemas.py — FirmSettingsResponse
  [ ] src/settings/schemas.py — UserPermissionsResponse
  [ ] src/settings/schemas.py — SessionItemResponse
  [ ] src/settings/schemas.py — SessionListResponse
  [ ] src/settings/schemas.py — BillingSummaryResponse
  [ ] src/settings/schemas.py — PendingInvitationResponse

Step 6 — Service:
  [ ] src/settings/service.py — get_or_create_user_settings()
  [ ] src/settings/service.py — update_user_settings()
  [ ] src/settings/service.py — get_or_create_firm_settings()
  [ ] src/settings/service.py — update_firm_settings()
  [ ] src/settings/service.py — change_password()
  [ ] src/settings/service.py — list_active_sessions()
  [ ] src/settings/service.py — revoke_session()
  [ ] src/settings/service.py — revoke_all_sessions()
  [ ] src/settings/service.py — get_billing_summary()
  [ ] src/settings/service.py — list_pending_invitations()
  [ ] src/settings/service.py — revoke_invitation()
  [ ] src/settings/service.py — resend_invitation()

Step 7 — Routes:
  [ ] GET  /settings/user
  [ ] PATCH /settings/user
  [ ] GET  /settings/firm
  [ ] PATCH /settings/firm
  [ ] GET  /settings/permissions
  [ ] POST /settings/password
  [ ] GET  /settings/security/sessions
  [ ] DELETE /settings/security/sessions/{session_id}
  [ ] POST /settings/security/sessions/revoke-all
  [ ] GET  /settings/security/2fa
  [ ] GET  /settings/billing-summary
  [ ] GET  /settings/firm/invitations
  [ ] DELETE /settings/firm/invitations/{id}
  [ ] POST /settings/firm/invitations/{id}/resend

Step 8 — App registration:
  [ ] src/main.py — settings router registered

Collaboration (already complete — no action needed):
  [x] migrations/add_collaboration_tables.py
  [x] src/collaboration/__init__.py
  [x] src/collaboration/models.py
  [x] src/collaboration/service.py
  [x] src/collaboration/routes.py
  [x] src/main.py — collaboration router registered

Auth updates for session metadata:
  [ ] src/auth/auth.py — create_refresh_token() accepts ip_address, user_agent
  [ ] src/auth/routes.py — /login passes request metadata to create_refresh_token()
  [ ] src/auth/routes.py — /refresh passes request metadata to create_refresh_token()
  [ ] src/auth/routes.py — /verify-email passes request metadata to create_refresh_token()
  [ ] src/auth/models.py — RefreshSession: ip_address, user_agent columns added

Firms service update for allow_member_invites:
  [ ] src/firms/service.py — invite_member() checks firm_settings.allow_member_invites
      before raising 403 for member role

Phase 2 coordination (when Phase 2 merges):
  [ ] src/billing/webhooks.py — motion_approval_required flag respected if relevant

---

## Collaboration Status: Already Done

The following were implemented prior to Phase 4:

| File | Status |
|---|---|
| `migrations/add_collaboration_tables.py` | ✓ exists |
| `src/collaboration/models.py` | ✓ exists |
| `src/collaboration/service.py` | ✓ exists |
| `src/collaboration/routes.py` | ✓ exists |
| `src/collaboration/__init__.py` | ✓ exists |
```
