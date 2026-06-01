# Phase 3 — Registration Update & Email Verification

**Branch:** `feat/phase-3-firm-mgmt`
**Last Updated:** 2026-05-21
**Status:** Pending review

---

## Overview

This plan covers three changes that all belong to Phase 3:

1. **Combined registration** — user creates their firm during sign-up (no separate `POST /api/firms` step)
2. **Email verification gate** — JWT is not issued until the user verifies their email
3. **Firm profile fields** — `address`, `firm_type`, `contact_number` added to firm at creation

---

## Confirmed Design Decisions

These are locked decisions that must be reflected in all implementation steps below.

### Decision 1 — Existing users are pre-verified
The migration sets `email_verified = TRUE` for all existing rows.
Existing users are never disrupted. Only users registered after this change must verify.

### Decision 2 — `login_user()` must check `email_verified`
If a user registers but does not verify their email, then attempts to log in directly
(they know their password), `login_user()` in `src/auth/service.py` must check
`user.email_verified` before issuing any JWT.

```
If user.email_verified is False → raise HTTP 401
  detail: "Email not verified. Please check your inbox."
```

This is required for the verification gate to actually hold. Without it, a user can
bypass verification entirely by just logging in.

**File:** `src/auth/service.py` — `login_user()`
**When:** Step 10 (same step as updating `register_new_user()`)

---

### Decision 3 — Invited users bypass email verification
`POST /api/firms/invite/accept` issues a JWT directly without any email
verification step. This is intentional — the invitation email itself serves
as proof of email ownership. Setting `email_verified = True` when accepting
an invitation is the correct behavior.

**File:** `src/firms/service.py` — `accept_invitation()`
**Change:** Set `user.email_verified = True` when creating or updating the invited user.

---

### Decision 4 — `firm_name` is optional at registration
A user can register with no `firm_name`, verify their email, and then call
`POST /api/firms` afterward. The existing endpoint remains valid for this path.

Registration without `firm_name`:
```
POST /api/auth/register  { email, password, first_name, last_name }
→ creates User (no Firm)
→ sends verification email
→ returns RegisterResponse

POST /api/auth/verify-email  { token }
→ sets email_verified = True
→ returns JWT (firm_id = null in token — user has no firm yet)

POST /api/firms  { firm_name, ... }
→ creates Firm, sets firm_id on user
→ returns new JWT with firm_id embedded
```

---

### Decision 5 — JWT from `create_firm()` is discarded during registration
`create_firm()` internally issues a JWT (this is what `POST /api/firms` returns
to the user when called directly). When `register_new_user()` calls `create_firm()`,
that token is thrown away. The real JWT is only issued after email verification
via `POST /api/auth/verify-email`.

**No change needed to `create_firm()`** — the caller (`register_new_user`) simply
ignores the second return value:
```python
firm, _token = await create_firm(owner_user_id=user.id, firm_name=...)
# _token is discarded — JWT comes from /verify-email instead
```

---

## New Registration Flow

```
POST /api/auth/register
  Body: { email, password, first_name, last_name,
          firm_name*, firm_address?, firm_type?, firm_contact_number? }

  1. Validate email not taken
  2. Create User (email_verified=False)
  3. If firm_name provided → create Firm (with address, firm_type, contact_number)
  4. Generate email_verification_token (UUID v4, expires 24h)
  5. Send verification email to user
  6. Return { message, user_id }   ← NO JWT yet

     ↓  user clicks link in email

GET  {FRONTEND_URL}/verify-email?token=xxx
     (frontend page — shows "Confirming your account..." UI)

     ↓  frontend calls backend

POST /api/auth/verify-email
  Body: { token: str }

  1. Find user by email_verification_token
  2. Check token not expired
  3. Set email_verified=True, clear token fields
  4. Issue JWT (with firm_id if user has a firm)
  5. Return { access_token, token_type, user }   ← user is now fully in
```

### What happens to `POST /api/firms`?

It stays as-is. It remains valid for edge cases where a user registered
without a firm name and needs to create one later. It is no longer
the primary onboarding path.

---

## Files Changed

### 1. Migrations (2 new files)

#### `migrations/add_email_verification_to_users.py`

Adds to the `users` table:

| Column | Type | Nullable | Default |
|---|---|---|---|
| `email_verified` | BOOLEAN | NOT NULL | `FALSE` (new users) / `TRUE` (existing rows) |
| `email_verification_token` | VARCHAR UNIQUE | NULL | — |
| `email_verification_expires_at` | TIMESTAMPTZ | NULL | — |

Idempotent — safe to run multiple times.

#### `migrations/add_firm_profile_fields.py`

Adds to the `firms` table:

| Column | Type | Nullable |
|---|---|---|
| `address` | VARCHAR | NULL |
| `firm_type` | VARCHAR | NULL |
| `contact_number` | VARCHAR | NULL |

Idempotent — safe to run multiple times.

---

### 2. `src/auth/models.py` — 3 new columns on `User`

```python
email_verified = Column(Boolean, nullable=False, default=False)
email_verification_token = Column(String, nullable=True, unique=True)
email_verification_expires_at = Column(DateTime(timezone=True), nullable=True)
```

---

### 3. `src/firms/models.py` — 3 new columns on `Firm`

```python
address = Column(String, nullable=True)
firm_type = Column(String, nullable=True)
contact_number = Column(String, nullable=True)
```

---

### 4. `src/schema.py` — schema changes

**`UserCreate`** — add optional firm fields:
```python
firm_name: Optional[str] = None
firm_address: Optional[str] = None
firm_type: Optional[str] = None
firm_contact_number: Optional[str] = None
```

**`UserResponse`** — add verification status:
```python
email_verified: bool = False
```

**New `RegisterResponse`** (replaces `UserResponse` on register):
```python
class RegisterResponse(BaseModel):
    message: str    # "Verification email sent. Please check your inbox."
    user_id: str
```

**New `VerifyEmailRequest`**:
```python
class VerifyEmailRequest(BaseModel):
    token: str
```

---

### 5. `src/firms/schemas.py` — expand firm schemas

**`FirmCreateRequest`** gains:
```python
firm_address: Optional[str] = None
firm_type: Optional[str] = None
firm_contact_number: Optional[str] = None
```

**`FirmResponse`** gains:
```python
address: Optional[str]
firm_type: Optional[str]
contact_number: Optional[str]
```

**`FirmUpdateRequest`** gains:
```python
address: Optional[str] = None
firm_type: Optional[str] = None
contact_number: Optional[str] = None
```

---

### 6. `src/notifications/email.py` — 1 new function

```python
async def send_email_verification_email(
    to_email: str,
    verification_token: str,
) -> None:
    """Email verification on registration.

    Called by: src/auth/service.py register_new_user()
    """
```

Link in email:
```
{FRONTEND_URL}/verify-email?token={verification_token}
```

---

### 7. `src/notifications/templates/email_verification.html` — new template

Extends `_base.html`. Contains:
- Subject: "Verify your BKDrafts account"
- CTA button → verify link
- 24-hour expiry notice

---

### 8. `src/auth/service.py` — update `register_new_user()`

Current behavior: creates user → returns `UserResponse`

New behavior:
```
1. Normalize + check email uniqueness
2. Create User:
     email_verified = False
     email_verification_token = str(uuid4())
     email_verification_expires_at = now + 24h
3. If user_data.firm_name is set:
     call firms.service.create_firm(
         owner_user_id = user.id,
         firm_name = user_data.firm_name,
         address = user_data.firm_address,
         firm_type = user_data.firm_type,
         contact_number = user_data.firm_contact_number,
     )
     (create_firm sets user.firm_id + role + permissions + issues JWT internally
      but we discard the JWT here — verification comes first)
4. Send send_email_verification_email(user.email, user.email_verification_token)
5. Log "register" action
6. Return RegisterResponse(message=..., user_id=user.id)
```

**No JWT returned from register.**

---

### 9. `src/auth/routes.py` — 2 changes

**Update `POST /api/auth/register`:**
- Change `response_model` from `UserResponse` to `RegisterResponse`
- No other change needed (logic is in service)

**Add `POST /api/auth/verify-email`** (public — no auth):
```
Body:    VerifyEmailRequest { token: str }

Logic:
  1. Find User where email_verification_token == token
  2. Raise 400 if not found → "Invalid or expired verification token"
  3. Raise 400 if email_verification_expires_at < now → "Verification token has expired"
  4. Raise 400 if email_verified is already True → "Email already verified"
  5. Set email_verified = True
  6. Clear email_verification_token = None
  7. Clear email_verification_expires_at = None
  8. Issue JWT: create_access_token({ sub: user.id, firm_id: user.firm_id, role: user.role })
  9. Create refresh token
  10. Set auth cookies
  11. Return LoginResponse { access_token, token_type, user: UserResponse }
```

---

### 10. `src/firms/service.py` — update `create_firm()` signature

```python
async def create_firm(
    owner_user_id: str,
    firm_name: str,
    address: Optional[str] = None,
    firm_type: Optional[str] = None,
    contact_number: Optional[str] = None,
) -> tuple[Firm, str]:
```

Saves `address`, `firm_type`, `contact_number` to the `Firm` row.
Return value (`str` = JWT token) is used by `POST /api/firms` route
but discarded by `register_new_user()` (verification comes first).

---

### 11. `src/firms/routes.py` — update `PATCH /api/firms/me`

Extend to also update `address`, `firm_type`, `contact_number`
from the expanded `FirmUpdateRequest`. These three are `Optional` —
only updated if provided in the request body.

---

## Build Order

```
Step 1  →  migrations/add_email_verification_to_users.py   (create + run)
Step 2  →  migrations/add_firm_profile_fields.py            (create + run)
Step 3  →  src/auth/models.py                               (add 3 columns)
Step 4  →  src/firms/models.py                              (add 3 columns)
Step 5  →  src/schema.py                                    (expand schemas)
Step 6  →  src/firms/schemas.py                             (expand schemas)
Step 7  →  src/notifications/email.py                       (add 1 function)
Step 8  →  src/notifications/templates/email_verification.html  (new)
Step 9  →  src/firms/service.py                             (update create_firm)
Step 10 →  src/auth/service.py                              (update register_new_user)
Step 11 →  src/auth/routes.py                               (update /register + add /verify-email)
Step 12 →  src/firms/routes.py                              (update PATCH /me)
```

---

## New API Endpoints Summary

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/auth/register` | Public | Updated — now accepts firm fields, sends verification email, returns no JWT |
| `POST` | `/api/auth/verify-email` | Public | New — verifies token, returns JWT |

## Updated API Endpoints Summary

| Method | Path | Change |
|---|---|---|
| `POST` | `/api/auth/register` | Response changes to `RegisterResponse`; body gains firm fields |
| `PATCH` | `/api/firms/me` | Body gains `address`, `firm_type`, `contact_number` |

---

## Edge Cases

| Scenario | Response |
|---|---|
| Register with email already taken | `400 Email already registered` |
| Register without `firm_name` | User created, no firm created, verification email sent |
| Verify with invalid token | `400 Invalid or expired verification token` |
| Verify with expired token (>24h) | `400 Verification token has expired` |
| Verify token already used | `400 Email already verified` |
| Login before email verified | `401 Email not verified. Please check your inbox.` (login_user() must add this check) |
| `POST /api/firms` after registration without firm | Still works — issues JWT with firm_id |

> **Note:** `login_user()` in `src/auth/service.py` must also be updated to check
> `user.email_verified` and raise `401` if `False`. This prevents unverified
> users from logging in directly.

---

## What Does NOT Change

- `POST /api/firms` — remains as fallback for creating a firm post-registration
- `POST /api/firms/invite/accept` — unaffected (invited users have no verification step)
- All other auth routes (`/login`, `/refresh`, `/logout`, `/me`)
- All billing routes
- All chatbot/session routes

---

## Checklist

```
Migrations:
  [ ] migrations/add_email_verification_to_users.py — created and run
  [ ] migrations/add_firm_profile_fields.py — created and run

Model updates:
  [ ] src/auth/models.py — email_verified, email_verification_token, email_verification_expires_at
  [ ] src/firms/models.py — address, firm_type, contact_number

Schema updates:
  [ ] src/schema.py — UserCreate gains firm fields; RegisterResponse added; VerifyEmailRequest added
  [ ] src/firms/schemas.py — FirmCreateRequest, FirmResponse, FirmUpdateRequest expanded

Notifications:
  [ ] src/notifications/email.py — send_email_verification_email() added
  [ ] src/notifications/templates/email_verification.html — created

Service updates:
  [ ] src/firms/service.py — create_firm() accepts address, firm_type, contact_number
  [ ] src/auth/service.py — register_new_user() sends verification email, no JWT; discards JWT from create_firm()
  [ ] src/auth/service.py — login_user() checks user.email_verified → 401 if False (Decision 2)
  [ ] src/firms/service.py — accept_invitation() sets user.email_verified = True (Decision 3)

Route updates:
  [ ] src/auth/routes.py — POST /register response_model updated to RegisterResponse
  [ ] src/auth/routes.py — POST /verify-email added (public)
  [ ] src/firms/routes.py — PATCH /me handles new profile fields
```
