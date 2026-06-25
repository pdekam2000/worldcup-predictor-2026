# Phase 37A — Admin / Super Admin Security Hardening Report

**Date:** 2026-06-20  
**Mode:** Implement locally → Validate → Report  
**Production deploy:** NO (intentionally skipped)

---

## Summary

Phase 37A secures the Admin Panel, Super Admin Panel, and API Settings before deploying Phase 36C/36B. Normal users no longer see admin navigation items. Admin and super-admin routes require authentication, role checks, and a second-factor access key verified server-side. Backend admin APIs return 401/403 for unauthorized callers and never expose admin data without passing both role and gate checks.

---

## Files Changed

### Backend (new)

| File | Purpose |
|------|---------|
| `worldcup_predictor/access/admin_gate.py` | Gate verification, JWT gate tokens, brute-force lockout, audit log |
| `worldcup_predictor/api/routes/admin_gate.py` | `/api/admin/gate/*` status + verify endpoints |
| `alembic/versions/002_super_admin_role.py` | PostgreSQL `user_role` enum adds `super_admin` |

### Backend (modified)

| File | Change |
|------|--------|
| `worldcup_predictor/config/settings.py` | `ADMIN_ACCESS_KEY`, `SUPER_ADMIN_ACCESS_KEY`, `ADMIN_AUDIT_LOG_PATH` |
| `worldcup_predictor/database/postgres/enums.py` | `UserRole.SUPER_ADMIN` |
| `worldcup_predictor/api/deps.py` | `require_admin_user`, `require_super_admin_user`, generic 403 messages |
| `worldcup_predictor/api/main.py` | Registers `admin_gate` router |
| `worldcup_predictor/api/web_auth.py` | JWT role mapping for `super_admin` |
| `worldcup_predictor/api/routes/admin.py` | Role/plan mutations require `require_super_admin_user` |
| `worldcup_predictor/api/routes/predictions.py` | `is_admin` includes `super_admin` |
| `worldcup_predictor/subscription/quota_service.py` | Admin bypass includes `super_admin` |

### Frontend (new)

| File | Purpose |
|------|---------|
| `base44-d/src/lib/roles.js` | Role helpers for nav and route guards |
| `base44-d/src/lib/adminGate.js` | Gate token sessionStorage + verify/status API calls |
| `base44-d/src/components/AccessDenied.jsx` | Generic “Access denied.” screen |
| `base44-d/src/components/AdminGatePrompt.jsx` | Second-factor key entry UI |
| `base44-d/src/components/AdminRoute.jsx` | Admin route guard (role + gate) |
| `base44-d/src/components/SuperAdminRoute.jsx` | Super-admin route guard (role + gate) |

### Frontend (modified)

| File | Change |
|------|--------|
| `base44-d/src/components/dashboard/DashboardLayout.jsx` | Role-based sidebar; no disabled admin links for normal users |
| `base44-d/src/App.jsx` | Admin routes wrapped in `AdminRoute` / `SuperAdminRoute` |
| `base44-d/src/lib/AuthContext.jsx` | Clears gate tokens on logout |
| `base44-d/src/api/saasApi.js` | Admin fetches send `X-Admin-Gate-Token`; super-admin mutations send `X-Super-Admin-Gate-Token` |
| `base44-d/src/pages/SuperAdminPanel.jsx` | `super_admin` role in role picker |

### Validation

| File | Purpose |
|------|---------|
| `scripts/validate_phase37a_admin_security.py` | Automated Phase 37A checks |

---

## Frontend Route / Sidebar Changes

### Sidebar (`DashboardLayout.jsx`)

- **Normal user (`role=user`):** sees only standard nav (Dashboard, Match Center, etc.). No Admin Panel, Super Admin, or API Settings.
- **Admin (`role=admin` or `super_admin`):** sees Admin Panel, Accuracy Center, Learning Dashboard, API Settings.
- **Super Admin (`role=super_admin` only):** additionally sees Super Admin link.
- Admin section links are **omitted entirely** for unauthorized users — not shown as disabled.

### Route guards (`App.jsx`)

| Route | Guard |
|-------|-------|
| `/admin`, `/admin/accuracy`, `/admin/learning`, `/api-settings` | `AdminRoute` |
| `/super-admin` | `SuperAdminRoute` |

### Unauthorized UX

- Unauthenticated → redirect to `/login`
- Authenticated but wrong role → `<AccessDenied />` with message **“Access denied.”** only
- No admin feature names or internal details exposed on denial screens

### Data loading order

`AdminRoute` / `SuperAdminRoute` render `AdminGatePrompt` **before** child pages. Admin page components (`AdminPanel`, etc.) mount only after role check and gate pass, so admin data is not fetched before authorization.

---

## Backend Endpoint Protection

### Dependency chain

1. **`get_current_user`** — Bearer JWT required → **401** if missing/invalid
2. **`require_admin_user`** — role ∈ `{admin, super_admin}` + valid `X-Admin-Gate-Token` → **403** otherwise
3. **`require_super_admin_user`** — role = `super_admin` + valid `X-Super-Admin-Gate-Token` → **403** otherwise

All responses use generic detail: `"Access denied."` (no feature enumeration).

### Protected routes

| Prefix | Dependency |
|--------|------------|
| `/api/admin/health`, `/stats`, `/users`, `/quota` | `require_admin_user` |
| `/api/admin/users/{id}/role`, `/subscription` | `require_super_admin_user` |
| `/api/admin/accuracy/*` | `require_admin_user` |
| `/api/admin/learning/*` | `require_admin_user` |
| `/api/admin/gate/status`, `/verify` | auth + admin role |
| `/api/admin/gate/super-admin/*` | auth + super_admin role |

Unauthorized attempts write audit events (see below).

---

## Admin Gate Behavior

### Configuration

```env
ADMIN_ACCESS_KEY=<secret>          # required for admin gate to pass
SUPER_ADMIN_ACCESS_KEY=<secret>    # required for super-admin gate to pass
ADMIN_AUDIT_LOG_PATH=data/logs/admin_audit.jsonl   # optional override
```

Keys are **never** sent to the frontend or logged.

### Flow

1. User logs in with JWT (role `admin` or `super_admin`).
2. User navigates to an admin route → `AdminGatePrompt` shown.
3. Frontend POSTs `{ access_key }` to `/api/admin/gate/verify`.
4. Backend compares key with `ADMIN_ACCESS_KEY` (constant-time `hmac.compare_digest`).
5. On success: returns short-lived JWT **gate token** (60 min TTL, bound to `user_id` + gate kind).
6. Frontend stores gate token in `sessionStorage`; subsequent admin API calls send `X-Admin-Gate-Token`.
7. Gate tokens cleared on logout.

If `ADMIN_ACCESS_KEY` is unset, gate is not configured and admin API calls return **403** (secure default).

---

## Super Admin Gate Behavior

Same pattern as admin gate, but:

- Requires `role=super_admin` (regular `admin` cannot access super-admin routes or mutations).
- Uses `SUPER_ADMIN_ACCESS_KEY` and `X-Super-Admin-Gate-Token`.
- Separate lockout counter and audit events.
- Super Admin sidebar link hidden unless `role=super_admin`.

---

## Brute-Force Protection

- **5 failed attempts** per `(user_id, gate, IP)` → **300s lockout**
- State held in-process (thread-safe dict); resets on API restart
- Failed attempts logged as `admin_gate_failed` / `super_admin_gate_failed` without secrets
- Lockout status returned in gate status/verify error payloads (`locked`, `retry_after_seconds`)

---

## Audit Log

**Path:** `data/logs/admin_audit.jsonl` (configurable via `ADMIN_AUDIT_LOG_PATH`)

**Events:**

| Event | When |
|-------|------|
| `admin_gate_success` | Correct admin key |
| `admin_gate_failed` | Wrong admin key |
| `super_admin_gate_success` | Correct super-admin key |
| `super_admin_gate_failed` | Wrong super-admin key |
| `unauthorized_admin_route_attempt` | Non-admin or missing gate on admin endpoint |
| `unauthorized_super_admin_route_attempt` | Non-super-admin or missing gate on super-admin endpoint |

Records: `ts`, `event`, `user_id`, `ip`, optional `detail` — **never** access keys or gate tokens.

---

## Validation Results

```text
python scripts/validate_phase37a_admin_security.py
Phase 37A validation: 32/32 PASS
```

| Check | Result |
|-------|--------|
| Normal user sidebar hides admin/super-admin/API Settings | PASS |
| Admin route shows AccessDenied for non-admin | PASS |
| Super-admin route requires super_admin role | PASS |
| Admin fetch sends gate header | PASS |
| Super-admin mutations send super gate header | PASS |
| No keys in frontend bundle | PASS |
| Admin gate rejects wrong key | PASS |
| Admin gate accepts correct key | PASS |
| Super-admin key verification | PASS |
| Gate JWT validates | PASS |
| Brute-force lockout | PASS |
| Audit log written without secrets | PASS |
| `/api/admin/health` unauthenticated → 401 | PASS |
| Gate verify unauthenticated → 401 | PASS |
| Admin pages behind gate before render | PASS |

---

## Known Limitations

1. **Gate tokens in `sessionStorage`** — cleared on tab close; not HttpOnly. A stolen JWT + gate token within TTL could access admin APIs. For stronger security, consider server-side session store or embedding gate expiry in refresh-token rotation.
2. **Brute-force counters in-memory** — lockout state does not survive API process restart or span multiple workers without shared store (Redis).
3. **`VITE_DEV_AUTH_BYPASS=true`** — dev mock admin still bypasses real auth in local dev; do not enable in production builds.
4. **PostgreSQL migration** — run `alembic upgrade head` on production before assigning `super_admin` roles.
5. **No existing super_admin users** — must be promoted manually (DB or super-admin panel after first super_admin is seeded).

---

## Production Deployment Notes

**Deploy Phase 37A before or together with Phase 36C/36B.**

1. Set strong random values for `ADMIN_ACCESS_KEY` and `SUPER_ADMIN_ACCESS_KEY` in `.env.production` (never commit).
2. Run Alembic: `alembic upgrade head` (adds `super_admin` to `user_role` enum).
3. Promote at least one user to `super_admin` in PostgreSQL if role/plan management is needed.
4. Rebuild and deploy frontend so sidebar/route guards are active.
5. Restart API after env changes.
6. Verify: normal user cannot see admin nav; admin user prompted for key; wrong key → lockout after 5 tries.
7. Confirm audit log directory is writable: `data/logs/`.

**Not changed:** prediction engine, Phase 36C/36B env loading, subscription billing logic (only role bypass extended for `super_admin`).

---

## Rollback Plan

1. **Frontend:** revert `DashboardLayout.jsx`, `App.jsx`, route guard components, `roles.js`, `adminGate.js`, `saasApi.js` gate headers.
2. **Backend:** revert `deps.py` to prior `require_admin_user` (role-only); remove `admin_gate` router from `main.py`; remove gate headers requirement.
3. **Env:** remove `ADMIN_ACCESS_KEY` / `SUPER_ADMIN_ACCESS_KEY` (admin endpoints will 403 if gate deps remain — full revert requires code rollback).
4. **Database:** `super_admin` enum value can remain (harmless); downgrade migration is no-op by design.
5. **Audit:** optional — archive or delete `data/logs/admin_audit.jsonl`.

Rollback restores prior behavior: admin links visible to all logged-in users with “Admin access required” messaging.

---

## Sign-off

Phase 37A implementation and validation complete locally. **No production deploy performed** per scope. Ready to bundle with Phase 36C/36B production release after keys and migration are applied on server.
