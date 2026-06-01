# Phase 3 — Firm Management: Testing Guide

**Branch:** `feat/paywall-phase3`
**Base URL:** `http://localhost:8000`
**Swagger UI:** `http://localhost:8000/docs` → look for the **firms** tag

---

## Pre-Test Setup

### 1. Add env vars to `.env`
```env
EMAIL_API_KEY=re_xxxxxxxxxxxxxxxx
EMAIL_FROM_ADDRESS=noreply@yourdomain.com
FRONTEND_URL=http://localhost:3000
```

### 2. Sync dependencies and restart
```bash
docker compose exec backend uv sync
docker compose restart backend
```

### 3. Verify the firms router is loaded
Open `http://localhost:8000/docs` — confirm **firms** tag appears with 10 endpoints.

---

## All Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/firms` | Bearer (no firm yet) | Create firm for newly registered user |
| `GET` | `/api/firms/me` | Bearer | Get current firm details |
| `PATCH` | `/api/firms/me` | Bearer (admin+) | Update firm name |
| `GET` | `/api/firms/members` | Bearer (admin+) | List all active members |
| `POST` | `/api/firms/invite` | Bearer (admin+) | Send invitation email |
| `POST` | `/api/firms/invite/accept` | **Public** | Accept invitation, returns JWT |
| `PATCH` | `/api/firms/members/{user_id}/permissions` | Bearer (admin+) | Update member permissions |
| `DELETE` | `/api/firms/members/{user_id}` | Bearer (admin+) | Remove member (soft delete) |
| `POST` | `/api/firms/transfer-ownership` | Bearer (firm_owner) | Transfer firm_owner role |
| `GET` | `/api/firms/onboarding-status` | Bearer | Get firm onboarding status |

---

## Test Flows

### Flow 1 — Register → Create Firm → Verify

**Step 1: Register a new user**
```http
POST /api/auth/register
Content-Type: application/json

{
  "email": "owner@vanhornlaw.com",
  "password": "Test1234!",
  "first_name": "John",
  "last_name": "Van Horn"
}
```
Expected: `200 OK` with user object.

---

**Step 2: Login to get token**
```http
POST /api/auth/login
Content-Type: application/json

{
  "email": "owner@vanhornlaw.com",
  "password": "Test1234!"
}
```
Expected: `{ "access_token": "eyJ...", "token_type": "bearer" }`

> Copy this token — note it has **no firm_id** yet.

---

**Step 3: Create the firm**
```http
POST /api/firms
Authorization: Bearer <token from step 2>
Content-Type: application/json

{
  "firm_name": "Van Horn Law Group"
}
```
Expected:
```json
{
  "id": "uuid",
  "name": "Van Horn Law Group",
  "owner_email": "owner@vanhornlaw.com",
  "onboarding_status": "pending",
  "subscription_status": "trialing",
  "is_active": true,
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```
> **Important:** Swap to the new `access_token` from this response. The old token has no `firm_id` and will be rejected by all subsequent requests.

---

**Step 4: Verify firm details**
```http
GET /api/firms/me
Authorization: Bearer <new token from step 3>
```
Expected: firm object with `id`, `name`, `onboarding_status: "pending"`.

---

**Step 5: Check onboarding status**
```http
GET /api/firms/onboarding-status
Authorization: Bearer <token>
```
Expected: `{ "onboarding_status": "pending" }`

---

### Flow 2 — Invite → Accept → Member appears

**Step 6: Send an invitation**
```http
POST /api/firms/invite
Authorization: Bearer <owner token>
Content-Type: application/json

{
  "email": "member@gmail.com",
  "role": "member",
  "permissions": []
}
```
Expected: `{ "id": "uuid", "email": "member@gmail.com", "role": "member", "expires_at": "..." }`

Check: invitation email should arrive at `member@gmail.com`.
Check: `GET /api/firms/onboarding-status` should now return `"completed"`.

---

**Step 7: Get the invite token (from DB or email link)**
```sql
SELECT token FROM firm_invitations ORDER BY created_at DESC LIMIT 1;
```
Or extract the `?token=` param from the invite link in the email.

---

**Step 8: Accept invitation (new user)**
```http
POST /api/firms/invite/accept
Content-Type: application/json

{
  "token": "<token from step 7>",
  "password": "Member1234!",
  "first_name": "Jane",
  "last_name": "Smith"
}
```
Expected: `{ "access_token": "eyJ...", "token_type": "bearer" }`

> This token is the new member's JWT — use it to verify they're in the firm.

---

**Step 9: Verify member is in the firm**
```http
GET /api/firms/members
Authorization: Bearer <owner token>
```
Expected: list of 2 members — owner (Superadmin) and Jane (Member).

---

**Step 10: Accept invitation (existing user)**

If the invited email already has an account (e.g. previously registered), omit `password`:
```http
POST /api/firms/invite/accept
Content-Type: application/json

{
  "token": "<token>",
  "first_name": "Existing",
  "last_name": "User"
}
```

---

### Flow 3 — Member Management

**Update permissions**
```http
PATCH /api/firms/members/<member_user_id>/permissions
Authorization: Bearer <owner or admin token>
Content-Type: application/json

{
  "permissions": ["analytics", "motion_studio", "case_management"]
}
```
Expected: updated member object.

---

**Remove a member**
```http
DELETE /api/firms/members/<member_user_id>
Authorization: Bearer <owner or admin token>
```
Expected: `{ "message": "Member removed successfully" }`

Verify: `GET /api/firms/members` — removed member no longer appears.

---

**Update firm name**
```http
PATCH /api/firms/me
Authorization: Bearer <owner or admin token>
Content-Type: application/json

{
  "name": "Van Horn Law Group LLC"
}
```
Expected: updated firm object.

---

### Flow 4 — Transfer Ownership

**Step 1: Add an admin first (invite + accept)**

**Step 2: Transfer ownership**
```http
POST /api/firms/transfer-ownership
Authorization: Bearer <firm_owner token>
Content-Type: application/json

{
  "new_owner_id": "<admin user_id>"
}
```
Expected: `{ "message": "Ownership transferred successfully" }`

Verify: `GET /api/firms/members` — original owner now shows as Admin, new owner shows as Superadmin.

---

## Edge Cases to Verify

| Scenario | Endpoint | Expected Response |
|----------|----------|-------------------|
| Create firm when user already has one | `POST /api/firms` | `400 User already belongs to a firm` |
| Use old token (no firm_id) on protected route | Any `/api/firms/me` | `401 Could not validate credentials` |
| Member calls invite endpoint | `POST /api/firms/invite` | `403 Forbidden` |
| Accept already-used token | `POST /api/firms/invite/accept` | `400 Invitation has already been used` |
| Accept expired token | `POST /api/firms/invite/accept` | `400 Invitation has expired` |
| Remove the firm owner | `DELETE /api/firms/members/<owner_id>` | `400 Cannot remove the firm owner` |
| Remove yourself | `DELETE /api/firms/members/<own_id>` | `400 Cannot remove yourself` |
| Edit firm owner's permissions | `PATCH /api/firms/members/<owner_id>/permissions` | `403 Cannot edit firm owner permissions` |
| Transfer ownership to yourself | `POST /api/firms/transfer-ownership` | `400 Cannot transfer ownership to yourself` |
| Transfer ownership to inactive member | `POST /api/firms/transfer-ownership` | `400 Cannot transfer ownership to an inactive member` |
| Non-owner calls transfer-ownership | `POST /api/firms/transfer-ownership` | `403 Only the firm owner can transfer ownership` |
| Invite beyond seat limit (default 5) | `POST /api/firms/invite` | `400 Firm has reached its seat limit` |
| Invite same email twice (active invite exists) | `POST /api/firms/invite` | `400 An active invitation already exists for this email` |

---

## DB Verification Queries

```sql
-- Check firms
SELECT id, name, owner_email, onboarding_status, subscription_status FROM firms;

-- Check users in a firm
SELECT id, email, role, firm_id, is_active, invitation_accepted_at FROM users WHERE firm_id IS NOT NULL;

-- Check invitations
SELECT id, email, role, accepted_at, expires_at, token FROM firm_invitations ORDER BY created_at DESC;
```

---

## Permissions Reference

| Permission value | Description |
|---|---|
| `analytics` | Access analytics dashboard |
| `motion_studio` | Access motion drafting |
| `case_management` | Access case management |
| `admin_dashboard` | Access admin dashboard |
| `approve_motions` | Approve/reject motions |
| `manage_members` | Invite and manage firm members |

| Role | Display name | Default permissions |
|---|---|---|
| `firm_owner` | Superadmin | All |
| `admin` | Admin | All |
| `member` | Member | None (explicitly granted) |
