# Paywall Implementation Plan

**Project:** bkdrafts-be
**Status:** Pre-Development (pending pre-conditions)
**Last Updated:** 2026-05-11

---

## Pre-Development Requirements

Do not begin implementation until all of the following are met:

1. All remaining non-AGT tickets are resolved and in the green
2. Green tasks are tested and verified bug-free
3. Full software sweep and stress test completed by each non-AGT developer
4. AGT feature is merged to main production branch

---

## Overview

The paywall introduces multi-tenancy (firm-level accounts), role-based access control, Stripe billing, collaboration tools, transactional email, and a settings module. All costs are placeholder `$0` until pricing is finalized. Stripe is the designated payment API.

---

## Account Structure

```
Firm Account (e.g. nickf@cvhlawgroup.com)
├── Admin Users
│   ├── user1@lawfirm.com — All access, can assign permissions
│   └── user2@lawfirm.com — All access, can assign permissions
└── Regular Users
    ├── user3@lawfirm.com — Analytics access only
    └── user4@lawfirm.com — Motion Studio access only
```

Permissions are malleable per user and assigned by admin accounts within the firm.

---

## Current State

| Area | Status |
|---|---|
| Auth | Basic JWT, single `User` model, no roles or firms |
| Multi-tenancy | None — no `firm_id` concept anywhere |
| Permissions | None — routes only check `is_authenticated` |
| Payments | No Stripe code |
| Collaboration | None — no cross-user sharing |
| Email | No transactional email service |
| Settings | No settings module |

---

## Database Layer Changes

### New `firms` Table (in `user_db`)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `name` | str | Firm display name |
| `owner_email` | str (unique) | Firm account email |
| `stripe_customer_id` | str (nullable) | Populated after Stripe onboarding |
| `subscription_status` | enum | `active`, `trialing`, `past_due`, `canceled` |
| `plan_id` | UUID FK → Plan | Current plan |
| `seat_limit` | int | Max users for the plan |
| `created_at` | datetime | |
| `is_active` | bool | Master kill switch |

### Extended `User` Model (`src/auth/models.py`)

New columns added to existing `users` table:

| Column | Type | Notes |
|---|---|---|
| `firm_id` | UUID FK → Firm | Tenant identifier |
| `role` | enum | `firm_owner`, `admin`, `member` |
| `permissions` | JSONB | `["analytics", "motion_studio", ...]` |
| `invited_by` | UUID FK → User (nullable) | Who sent the invitation |
| `invitation_accepted_at` | datetime (nullable) | When they joined |
| `stripe_subscription_item_id` | str (nullable) | Per-seat billing item |

### New `plans` Table

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `name` | str | Display name |
| `stripe_price_id` | str | Stripe Price ID |
| `price_cents` | int | `0` placeholder |
| `features` | JSONB | Feature flags for the plan |
| `is_active` | bool | |

### New `firm_invitations` Table

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `firm_id` | UUID FK → Firm | |
| `email` | str | Invitee email |
| `role` | enum | Role to assign on acceptance |
| `permissions` | JSONB | Permissions to assign |
| `invited_by` | UUID FK → User | |
| `token` | str (unique) | UUID v4, single-use |
| `expires_at` | datetime | 48-hour expiry |
| `accepted_at` | datetime (nullable) | |

---

## New Backend Modules

```
src/
├── firms/
│   ├── __init__.py
│   ├── models.py            — Firm, FirmInvitation, Plan
│   ├── routes.py            — /api/firms/* CRUD, invite, member management
│   └── service.py           — create_firm(), invite_member(), update_permissions()
│
├── billing/
│   ├── __init__.py
│   ├── models.py            — Subscription, Invoice (mirrors Stripe objects)
│   ├── routes.py            — /api/billing/*, /api/webhooks/stripe
│   ├── service.py           — create_checkout(), cancel_subscription()
│   └── webhooks.py          — handle subscription.created/updated/deleted
│
├── permissions/
│   ├── __init__.py
│   ├── constants.py         — Permission constants
│   ├── dependencies.py      — require_permission() FastAPI dependency
│   └── service.py           — check_permission(), assign_permissions()
│
├── collaboration/
│   ├── __init__.py
│   ├── models.py            — FirmChatRoom, FirmChatMessage, MotionComment
│   ├── routes.py            — /api/collab/* (SSE pattern, same as existing streams)
│   └── service.py
│
├── notifications/
│   ├── __init__.py
│   ├── email.py             — send_invite_email(), send_password_reset(), etc.
│   └── templates/           — HTML email templates
│
└── settings/
    ├── __init__.py
    ├── models.py            — UserSettings, FirmSettings
    ├── routes.py            — /api/settings/*
    └── service.py
```

---

## Permission System

### Permission Constants (`src/permissions/constants.py`)

```python
class Permission:
    ANALYTICS        = "analytics"
    MOTION_STUDIO    = "motion_studio"
    CASE_MANAGEMENT  = "case_management"
    ADMIN_DASHBOARD  = "admin_dashboard"
    APPROVE_MOTIONS  = "approve_motions"
    MANAGE_MEMBERS   = "manage_members"
```

### Role Hierarchy

| Role | Capabilities |
|---|---|
| `firm_owner` | All permissions implicitly; owns the Stripe subscription |
| `admin` | All permissions; can assign/revoke permissions for members |
| `member` | Only explicitly granted permissions |

### Usage in Routes

```python
@router.get("/dashboard/analytics")
async def get_analytics(
    user=Depends(require_permission(Permission.ANALYTICS))
):
    ...
```

---

## Tenant Isolation (Security Priority)

No session leakage between firms is an absolute requirement.

### Required Changes

1. Add `firm_id` column to all chatbot models in `src/chatbot/models.py`:
   - `Session`, `ChatThread`, `PDFDocument`, `MotionDraftLog`, `UserActivityLog`
2. Add `firm_id` to JWT payload in `src/auth/auth.py`
3. Add `get_current_firm_user()` dependency in `src/common/dependencies.py` — validates `firm_id` from JWT matches DB record on every request
4. All DB queries use `.filter(Model.firm_id == current_user.firm_id)` — no exceptions

### Migration for Existing Data

Create a default firm, assign all existing users to it, and backfill `firm_id` on all existing rows.

---

## Stripe Integration

### Flow

```
1. Firm owner registers
        ↓
2. POST /api/billing/checkout → Stripe Checkout Session (plan = $0 placeholder)
        ↓
3. Stripe webhook → subscription.created → activate firm in DB
        ↓
4. GET /api/billing/portal → Stripe Customer Portal (self-service upgrades/cancellations)
        ↓
5. Webhook → subscription.deleted → deactivate firm, notify all members
```

### Webhooks to Handle

| Event | Action |
|---|---|
| `customer.subscription.created` | Activate firm, set `subscription_status = active` |
| `customer.subscription.updated` | Sync plan/seat changes |
| `customer.subscription.deleted` | Deactivate firm |
| `invoice.payment_failed` | Set `subscription_status = past_due`, send alert email |

### Dependency to Add

```
stripe>=12.0.0
```

---

## Collaboration (Shared Chat)

Built on the existing SSE infrastructure (`src/routes/stream.py` pattern).

- **Firm chat rooms** scoped per case or motion, stored in `chat_db`, filtered by `firm_id`
- **Motion comments** attached to `MotionDraftLog` entries (new `comments` relation)
- **Real-time delivery** via existing SSE pattern — no WebSocket infrastructure needed
- Users can share motions, cases, and comments within their firm boundary

---

## Transactional Email

### Recommended Package

`sendgrid>=6.0.0` or `resend>=0.6.0`

### Required Email Events

| Trigger | Template |
|---|---|
| Member invited | Invitation link with 48h token |
| Invitation accepted | Confirmation to inviter |
| Password reset | Reset link |
| Subscription activated | Welcome + plan details |
| Subscription canceled | Cancellation confirmation |
| Payment failed | Payment failure alert with portal link |
| Motion approved | Notification to motion creator |
| Motion rejected | Rejection with admin comments |

---

## Settings Module

Settings are built simultaneously with the paywall. Must include:

### User Settings
- Display name, email, password change
- Notification preferences (email, in-app)
- Personal permission visibility (read-only)
- Active sessions management

### Firm Settings (Admin only)
- Firm name, owner email
- Member list with role and permission management
- Seat usage vs. plan limit
- Subscription and billing management link (Stripe portal)
- Invitation management (pending, resend, revoke)

---

## Implementation Phases

### Phase 1 — Foundation (no UI impact)
1. Firm + User DB schema changes and migration script
2. `src/permissions/` module
3. Update JWT to include `firm_id` claim
4. Add `firm_id` filtering to all chatbot queries

### Phase 2 — Billing Skeleton
5. `src/billing/` with `$0` placeholder plans
6. Stripe webhook endpoint (idempotent, handles future events)
7. `/api/billing/` routes: checkout, portal, status

### Phase 3 — Firm Management
8. `src/firms/` — CRUD, invitations, member permission management
9. `src/notifications/` — invitation and subscription emails

### Phase 4 — Settings and Collaboration
10. `src/settings/` — user and firm settings endpoints
11. `src/collaboration/` — firm-scoped chat rooms and motion comments

### Phase 5 — Frontend

> To be handled by the frontend team separately.

---

## Risk Register

| Risk | Severity | Mitigation |
|---|---|---|
| Session leakage between firms | Critical | `firm_id` on every DB row; validated in `get_current_firm_user()` dependency on every request |
| Existing data has no `firm_id` | High | Migration creates a default firm and backfills all existing rows |
| Stripe webhooks arriving before DB is ready | Medium | Idempotent webhook handlers with Stripe event ID deduplication |
| Permission bypass via direct route access | High | All checks centralized in `require_permission()` dependency, never in route body |
| Invitation token brute force | Medium | UUID v4 tokens, 48h expiry, single-use, rate-limited endpoint |
| Admin accidentally removing their own access | Medium | Protect firm_owner role from demotion without ownership transfer |

---

## What Does NOT Change

The following modules require no structural changes — they only need `firm_id` passed through context, which flows automatically from the auth dependency:

- `src/gmail/` — all Gmail/motion extraction logic
- `src/motion_filling/` — all document generation
- `src/tasks/` — all Taskiq async workers
- `src/courtdrive/` — CourtDrive integration
- `src/routes/stream.py` and related SSE routes

---

## Detailed Task Breakdown

---

### Phase 1 — Foundation

#### Tasks 1–6: Database Changes

**Task 1 — Create `firms` table migration**
- New migration script in `migrations/`
- Columns: `id` (UUID), `name`, `owner_email` (unique), `stripe_customer_id` (nullable), `subscription_status` (enum: active/trialing/past_due/canceled), `plan_id` (FK → plans), `seat_limit`, `created_at`, `is_active`, `onboarding_status` (enum: `pending` / `completed`, default `pending`)
- `onboarding_status` is set to `completed` only after firm name is saved AND at least one member invitation is sent
- All protected app routes check `firm.onboarding_status == completed`; incomplete firms are redirected to the onboarding flow
- Runs against `user_db`

**Task 2 — Create `plans` table migration**
- New migration script in `migrations/`
- Columns: `id` (UUID), `name`, `stripe_price_id`, `price_cents` (set to `0` as placeholder), `features` (JSONB), `is_active`
- Seed with at least one default plan at `$0`
- Runs against `user_db`

**Task 3 — Create `firm_invitations` table migration**
- New migration script in `migrations/`
- Columns: `id` (UUID), `firm_id` (FK → firms), `email`, `role` (enum), `permissions` (JSONB), `invited_by` (FK → users), `token` (UUID v4, unique), `expires_at` (48h from creation), `accepted_at` (nullable)
- Runs against `user_db`

**Task 4 — Extend `users` table**
- New migration script in `migrations/`
- Add to existing `users` table: `firm_id` (FK → firms, nullable during migration), `role` (enum: firm_owner/admin/member, default `member`), `permissions` (JSONB, default `[]`), `invited_by` (FK → users, nullable), `invitation_accepted_at` (datetime, nullable), `stripe_subscription_item_id` (str, nullable)
- Update `src/auth/models.py` — add new columns to `User` class

**Task 5 — Add `firm_id` to chatbot models**
- New migration script in `migrations/`
- Add `firm_id` column (nullable during migration) to: `sessions`, `chat_threads`, `pdf_documents`, `motion_draft_logs`, `user_activity_logs`
- Update `src/chatbot/models.py` — add column to each affected class

**Task 6 — Backfill migration for existing data**
- New migration script in `migrations/`
- Steps:
  1. Insert one default firm row (owner_email = existing admin email)
  2. Set `firm_id` on all existing `users` rows → default firm; set admin user `role = firm_owner`
  3. Set `firm_id` on all existing `sessions`, `chat_threads`, `pdf_documents`, `motion_draft_logs`, `user_activity_logs` rows → default firm
  4. After backfill: make `firm_id` NOT NULL on all tables

---

#### Tasks 7–11: Permissions & Auth

**Task 7 — Create `src/permissions/constants.py`**
- Define `Permission` class with constants: `ANALYTICS`, `MOTION_STUDIO`, `CASE_MANAGEMENT`, `ADMIN_DASHBOARD`, `APPROVE_MOTIONS`, `MANAGE_MEMBERS`
- Define `Role` enum: `firm_owner`, `admin`, `member`
- Define role-to-default-permissions map (`firm_owner` and `admin` get all; `member` gets none by default)
- **Role naming alignment:** `firm_owner` = "Superadmin" in all UI labels and frontend-facing API responses. The internal DB/code value stays `firm_owner`; the display name returned by APIs is `"Superadmin"`. Document this mapping explicitly so frontend and backend teams stay aligned.

**Task 8 — Create `src/permissions/dependencies.py`**
- `require_permission(permission: str)` — FastAPI dependency factory
- Reads `user.permissions` (JSONB list) from DB
- `firm_owner` and `admin` roles bypass the check implicitly
- Raises `HTTP 403` with clear message if permission missing
- Usage: `Depends(require_permission(Permission.ANALYTICS))`

**Task 9 — Update JWT payload in `src/auth/auth.py`**
- In `create_access_token()` — add `firm_id` and `role` to token payload alongside existing `sub`
- In `get_current_user()` — extract and validate `firm_id` from payload; raise `401` if missing
- In `login_user()` in `src/auth/service.py` — pass `firm_id` and `role` when building token data dict

**Task 10 — Add `get_current_firm_user()` to `src/common/dependencies.py`**
- New dependency that wraps `get_current_user()`
- After resolving the user, re-validates that `user.firm_id` in DB matches `firm_id` in JWT
- Raises `HTTP 401` if mismatch (prevents token reuse across firms)
- Replace all existing `Depends(get_current_user)` usages in routes with this new dependency

**Task 11 — Add `firm_id` filtering to all chatbot queries**
- Audit every DB query in: `src/chatbot/routes.py`, `routes_chat.py`, `routes_pdf.py`, `routes_sessions.py`, `src/routes/dashboard/`
- Append `.filter(Model.firm_id == current_user.firm_id)` to every SELECT on tenant-scoped tables
- No query on `sessions`, `chat_threads`, `pdf_documents`, `motion_draft_logs`, `user_activity_logs` should ever be unfiltered

---

### Phase 2 — Billing Skeleton

#### Tasks 12–17: Stripe Integration

**Task 12 — Add `stripe` to dependencies**
- Add `stripe>=12.0.0` to `pyproject.toml`
- Add `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PUBLIC_KEY` to `src/config.py`
- Add placeholder values to `.env.example`

**Task 13 — Create `src/billing/models.py`**
- `Subscription` table: `id`, `firm_id` (FK → firms), `stripe_subscription_id` (unique), `stripe_customer_id`, `plan_id` (FK → plans), `status`, `current_period_start`, `current_period_end`, `canceled_at` (nullable)
- `Invoice` table: `id`, `firm_id`, `stripe_invoice_id` (unique), `amount_cents`, `status`, `paid_at` (nullable), `created_at`
- Write migration script in `migrations/`

**Task 14 — Create `src/billing/service.py`**
- `create_stripe_customer(firm)` — creates Stripe Customer, saves `stripe_customer_id` to `Firm` row
- `create_checkout_session(firm, plan)` → returns Stripe Checkout URL (mode: `subscription`)
  - Must explicitly set `success_url` = `{FRONTEND_URL}/onboarding?session_id={CHECKOUT_SESSION_ID}`
  - Must explicitly set `cancel_url` = `{FRONTEND_URL}/pricing` (diagram: failed payment → redirect back to pricing)
- `create_billing_portal_session(firm)` → returns Stripe Customer Portal URL
- `get_subscription_status(firm_id)` → returns current subscription row
- `cancel_subscription(firm_id)` → cancels in Stripe + updates DB

**Task 15 — Create `src/billing/webhooks.py`**
- `handle_stripe_webhook(payload, sig_header)` — verifies signature using `STRIPE_WEBHOOK_SECRET`
- Event handlers:
  - `customer.subscription.created` → insert `Subscription` row, set `firm.subscription_status = active`
  - `customer.subscription.updated` → sync plan/status changes to DB
  - `customer.subscription.deleted` → set `firm.subscription_status = canceled`, `firm.is_active = False`
  - `invoice.payment_failed` → set `firm.subscription_status = past_due`, queue payment failure email
- All handlers are idempotent (check Stripe event ID before processing)

**Task 16 — Create `src/billing/routes.py`**
- `GET /api/billing/plans` — **public, no auth required** — returns list of active plans with name, features, price_cents (feeds the `/pricing` page)
- `POST /api/billing/checkout` — calls `create_checkout_session()`, returns `{ checkout_url }`
- `GET /api/billing/portal` — calls `create_billing_portal_session()`, returns `{ portal_url }`
- `GET /api/billing/status` — returns current `Subscription` row for the firm
- `POST /api/webhooks/stripe` — receives Stripe events, calls `handle_stripe_webhook()` (no auth — verified by signature only)

**Task 17 — Seed placeholder plans**
- One-time migration or seed script
- Insert at minimum one plan: `name = "Starter"`, `price_cents = 0`, `is_active = True`, `stripe_price_id = ""` (placeholder)

---

### Phase 3 — Firm Management

#### Tasks 18–20: Firm CRUD & Member Management

**Task 18 — Create `src/firms/models.py`**
- SQLAlchemy classes: `Firm`, `FirmInvitation`, `Plan` matching schema from Tasks 1–3
- `Firm` columns include: `id`, `name`, `plan_id`, `onboarding_status`, `stripe_customer_id`, `stripe_subscription_id`, `subscription_status`, `trial_ends_at`, `created_at`, and `allowed_domain` (nullable `String` — reserved for Phase 4 opt-in domain restriction; no enforcement in Phase 3)
- Re-export from `src/firms/__init__.py`
- **Run migration** `migrations/add_allowed_domain_to_firms.py` to add `allowed_domain` column if not already present

**Task 19 — Create `src/firms/service.py`**
- `create_firm(owner_user, firm_name)` — creates `Firm` row, sets owner `role = firm_owner`
- `invite_member(firm, inviter, email, role, permissions)` — creates `FirmInvitation` row, queues invitation email; sets `firm.onboarding_status = completed` after first invite is sent
- `accept_invitation(token, password=None)` — validates token not expired/used; if new user (no existing account): requires `password`, creates `User` with hashed password, `firm_id`, and permissions; if existing user: updates `firm_id` and permissions; marks `accepted_at`; **returns a JWT access token in both cases for immediate auto-login** (no redirect to login page)
- `update_member_permissions(admin_user, target_user_id, permissions)` — validates admin role, updates `user.permissions`
- `remove_member(admin_user, target_user_id)` — sets `user.is_active = False`; cannot remove `firm_owner`
- `transfer_ownership(current_owner, new_owner_id)` — swaps `firm_owner` role between two users

**Task 19.5 — Create `src/firms/schemas.py`** *(required before routes)*
- Pydantic v2 schemas for all request bodies and response models used in Task 20
- Key schemas: `FirmCreate`, `FirmResponse`, `InviteMemberRequest`, `AcceptInvitationRequest`, `UpdatePermissionsRequest`, `MemberResponse`, `FirmCreateResponse` (includes `access_token`), `AcceptInvitationResponse` (includes `access_token`)
- All response models use `model_config = ConfigDict(from_attributes=True)`

**Task 20 — Create `src/firms/routes.py`**
- `POST /api/firms` — create firm for a newly registered user; uses `get_current_user` (not `get_current_firm_user`) since user has no `firm_id` yet; body: `{ firm_name: str }`; response: `{ firm_id, firm_name, onboarding_status, access_token, token_type }` — issues a fresh JWT with `firm_id` so the frontend swaps the stored token immediately. Required because `register_new_user()` creates users with `firm_id=None` and all protected routes require `firm_id` in the JWT.
- `GET /api/firms/me` — return current firm info (includes `onboarding_status`)
- `PATCH /api/firms/me` — update firm name (admin only)
- `GET /api/firms/members` — list all members with roles (returned as UI display name e.g. "Superadmin") and permissions (admin only)
- `POST /api/firms/invite` — send invitation (admin only)
- `POST /api/firms/invite/accept` — accept invitation via token (public, no auth required); body: `{ token, password? }`; response: `{ access_token, token_type }` for immediate auto-login
- `PATCH /api/firms/members/{user_id}/permissions` — update member permissions (admin only)
- `DELETE /api/firms/members/{user_id}` — remove member (admin only)
- `POST /api/firms/transfer-ownership` — transfer `firm_owner` role (firm_owner only)
- `GET /api/firms/onboarding-status` — returns `{ onboarding_status }` for the current firm (used by frontend to gate the onboarding wizard)

---

#### Tasks 21–23: Notifications & Email

**Task 21 — Add email package to dependencies**
- Add `resend>=0.6.0` to `pyproject.toml`
- Add `EMAIL_API_KEY`, `EMAIL_FROM_ADDRESS`, `FRONTEND_URL` to `src/config.py`
- Add placeholders to `.env.example`

**Task 22 — Create `src/notifications/email.py`**
- `send_invite_email(to_email, inviter_name, firm_name, invite_token)`
- `send_invitation_accepted_email(to_email, new_member_name, firm_name)`
- `send_password_reset_email(to_email, reset_token)`
- `send_subscription_activated_email(to_email, firm_name, plan_name)`
- `send_subscription_canceled_email(to_email, firm_name)`
- `send_payment_failed_email(to_email, firm_name, portal_url)`
- `send_motion_approved_email(to_email, motion_type, case_number)`
- `send_motion_rejected_email(to_email, motion_type, case_number, reason)`

**Task 23 — Create HTML email templates in `src/notifications/templates/`**
- One HTML file per email type (8 total, one per function in Task 22)
- Shared branded header and footer
- Plain-text fallback for each

---

### Phase 4 — Settings & Collaboration

#### Pre-Start: Domain Restriction Migration

**Run before Phase 4 firm settings work:**
- Create and run `migrations/add_allowed_domain_to_firms.py`
- Adds `allowed_domain VARCHAR NULL` to `firms` table
- Update `src/firms/models.py` `Firm` class: add `allowed_domain = Column(String, nullable=True)`
- When set by a firm admin, `invite_member()` should restrict invitations to that domain only
- Default `NULL` = no restriction (works for Gmail and any email provider)
- Expose via `PATCH /api/settings/firm` as an optional field

#### Tasks 24–25: Settings

**Task 24 — Create `src/settings/models.py`**
- `UserSettings` table: `user_id` (PK, FK → users), `notification_email` (bool, default True), `notification_inapp` (bool, default True), `theme` (str, default "light"), `updated_at`
- `FirmSettings` table: `firm_id` (PK, FK → firms), `allow_member_invites` (bool, default False), `motion_approval_required` (bool, default False), `updated_at`
- Write migration script in `migrations/`

**Task 25 — Create `src/settings/routes.py` and `src/settings/service.py`**

User settings:
- `GET /api/settings/user` — return current user settings
- `PATCH /api/settings/user` — update user settings

Firm settings (admin only):
- `GET /api/settings/firm` — return firm settings
- `PATCH /api/settings/firm` — update firm settings
- `GET /api/settings/permissions` — return current user's permissions (read-only)

Security settings (named group — maps to diagram's "Security settings" tab):
- `POST /api/settings/password` — change password (validates current password first)
- `GET /api/settings/security/sessions` — list active JWT sessions with device/IP metadata
- `DELETE /api/settings/security/sessions/{session_id}` — revoke a specific session
- `POST /api/settings/security/sessions/revoke-all` — revoke all sessions except current (force logout everywhere)
- *(placeholder)* `GET /api/settings/security/2fa` — stub endpoint for future 2FA setup; returns `{ enabled: false }` for now

Billing summary (feeds "Billing + plan usage" tab in settings):
- `GET /api/settings/billing-summary` — returns `{ plan_name, subscription_status, seat_used, seat_limit, portal_url }` aggregated from the `billing/` module; no Stripe API call — reads from DB only

---

#### Tasks 26–28: Collaboration

**Task 26 — Create `src/collaboration/models.py`**
- `FirmChatRoom` table: `id`, `firm_id`, `name`, `linked_case_number` (nullable), `linked_motion_id` (FK → motion_draft_logs, nullable), `created_by` (FK → users), `created_at`
- `FirmChatMessage` table: `id`, `room_id` (FK → firm_chat_rooms), `user_id` (FK → users), `content` (Text), `created_at`
- `MotionComment` table: `id`, `motion_draft_log_id` (FK → motion_draft_logs), `user_id` (FK → users), `content` (Text), `created_at`, `updated_at`
- Write migration script in `migrations/`

**Task 27 — Create `src/collaboration/routes.py`**
- `GET /api/collab/rooms` — list firm chat rooms (filtered by `firm_id`)
- `POST /api/collab/rooms` — create a new room
- `GET /api/collab/rooms/{room_id}/messages` — paginated message history
- `POST /api/collab/rooms/{room_id}/messages` — post a message
- `GET /api/collab/rooms/{room_id}/stream` — SSE real-time stream (same pattern as `src/routes/stream.py`)
- `GET /api/collab/motions/{motion_id}/comments` — list comments on a motion
- `POST /api/collab/motions/{motion_id}/comments` — add a comment
- `DELETE /api/collab/motions/{motion_id}/comments/{comment_id}` — delete own comment (admin can delete any)

**Task 28 — Add `comments` relation to `MotionDraftLog`**
- In `src/chatbot/models.py` — add `relationship("MotionComment", back_populates="motion_draft_log")`
- In `src/collaboration/models.py` — add back-reference on `MotionComment`
- No data migration needed

---

### Phase 5 — Frontend

> To be handled by the frontend team separately.
