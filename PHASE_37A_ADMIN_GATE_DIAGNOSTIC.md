# Phase 37A-DIAG — Admin Role & Gate Diagnostic

**Date:** 2026-06-20  
**Mode:** Diagnosis only (no code changes, no deploy)  
**Server:** 91.107.188.229 (`https://footballpredictor.it.com`)  
**Local:** Windows dev workspace (`c:\Users\kaman\Desktop\Footbal`)

---

## Executive Summary

| Symptom | Root cause |
|---------|------------|
| Admin Panel visible but gate fails | **Wrong key / key not in operator possession** (production keys exist but were auto-generated at Phase 37B deploy and never distributed). Locally: **`ADMIN_ACCESS_KEY` not set at all** → gate always denies. |
| Super Admin menu missing | **Wrong role** — no user in PostgreSQL has `super_admin`. Sidebar requires exact `role === "super_admin"`. Current admin account is `admin` only. |
| Not a frontend bug | Production bundle (`index-vJFZWUu8.js`) gates sidebar with `canSeeAdminNav` / `canSeeSuperAdminNav`. Backend role checks match source code. |
| Not an env-load bug (production) | `worldcup-api.service` loads `/opt/worldcup-predictor/.env.production`; keys present and `gate_configured=true`. |

---

## 1. Current Logged-In User

### Production (live evidence — operator IP `90.146.73.90`)

Most recent authenticated session on production:

| Field | Value |
|-------|-------|
| **User ID** | `bb409f11-a60e-4323-a926-5a1196f414ec` |
| **Username / full name** | `dianakamangar` |
| **Email** | `dianakamangar@gmail.com` |
| **Role** | `user` |
| **Subscription plan** | `free` |
| **Last login (UTC)** | `2026-06-20 18:15:18` (registered + logged in same request) |

**Earlier same-day session (same IP, likely operator before new registration):**

| Field | Value |
|-------|-------|
| **User ID** | `87b27844-b3a9-406f-97d0-78c2e2a3a65c` |
| **Email** | `admin` |
| **Full name** | `Administrator` |
| **Role** | `admin` |
| **Plan** | `free` |
| **Last login (UTC)** | `2026-06-20 15:22:32` |

**Workspace owner account (not the active session at time of gate attempts):**

| Field | Value |
|-------|-------|
| **User ID** | `3802d201-9dda-4c2a-aaae-adc41c3b330c` |
| **Email** | `kamangar.pedram@gmail.com` |
| **Role** | `user` |
| **Plan** | `free` |
| **Last login (UTC)** | `2026-06-18 22:28:05` |

### Local dev (PostgreSQL via `.env` `DATABASE_URL`)

| Field | Value |
|-------|-------|
| **User ID** | `0c1b25e3-1e41-4bda-8c20-b0ddd6c3df35` |
| **Email** | `admin` |
| **Role** | `admin` |
| **Plan** | `free` |

Local `.env` has `ADMIN_USERNAME=admin` / `ADMIN_PASSWORD` set, but **no** `ADMIN_ACCESS_KEY` or `SUPER_ADMIN_ACCESS_KEY`.

---

## 2. Role Source Chain

| Layer | Source | Value (production `admin` account) | Value (production `dianakamangar@gmail.com`) |
|-------|--------|-------------------------------------|-----------------------------------------------|
| **PostgreSQL** | `users.role` enum (`user`, `admin`, `super_admin`) | `admin` | `user` |
| **Backend `/api/auth/me`** | `resolve_bearer_token()` → DB lookup → `_to_web_user()` | `"admin"` | `"user"` |
| **Backend gate deps** | `user_has_admin_access(role)` / `user_has_super_admin_access(role)` | admin: **pass** / super: **fail** | admin: **fail** / super: **fail** |
| **Frontend AuthContext** | `fetchMe()` → `payload.user.role` | Same as API | Same as API |
| **Sidebar rendering** | `canSeeAdminNav(user)` → `role === "admin" \|\| role === "super_admin"` | **show Admin Panel** | **hide Admin Panel** |
| **Super Admin sidebar** | `canSeeSuperAdminNav(user)` → `role === "super_admin"` | **hidden** | **hidden** |

**Important:** JWT is not trusted for role at request time. `resolve_bearer_token()` always reloads role from PostgreSQL (`worldcup_predictor/api/web_auth.py`).

**Production bundle verification:** Active JS (`/assets/index-vJFZWUu8.js`) contains gated sidebar logic:

```text
l=canSeeAdminNav(user), d=canSeeSuperAdminNav(user), ...
sidebar=[...(l ? adminItems : []), ...(d ? superAdminItems : []), ...]
```

---

## 3. Admin Gate Diagnostic

### Endpoints

| Purpose | Method | Path |
|---------|--------|------|
| Admin gate status | `GET` | `/api/admin/gate/status` |
| Admin gate verify | `POST` | `/api/admin/gate/verify` |
| Super Admin gate status | `GET` | `/api/admin/gate/super-admin/status` |
| Super Admin gate verify | `POST` | `/api/admin/gate/super-admin/verify` |

### Validation logic (backend)

File: `worldcup_predictor/access/admin_gate.py`

1. Route handler checks JWT + **DB role** (`admin` or `super_admin` required).
2. `gate_configured(gate)` — true only if expected key non-empty in settings.
3. `verify_access_key()` — `hmac.compare_digest(provided, expected)`.
4. On success → short-lived JWT gate token (`X-Admin-Gate-Token` / `X-Super-Admin-Gate-Token`).
5. Failed attempts → lockout after 5 failures / 300s.

Expected key sources:

| Gate | Settings field | Environment variable |
|------|----------------|----------------------|
| Admin | `settings.admin_access_key` | `ADMIN_ACCESS_KEY` |
| Super Admin | `settings.super_admin_access_key` | `SUPER_ADMIN_ACCESS_KEY` |

**Note:** `ADMIN_PASSWORD` (login password) ≠ `ADMIN_ACCESS_KEY` (second-factor gate). Using the login password in the gate prompt will always fail.

### Environment / key status (secrets not printed)

#### Production (`/opt/worldcup-predictor/.env.production`)

| Check | Result |
|-------|--------|
| `ADMIN_ACCESS_KEY` exists in file | **yes** |
| `SUPER_ADMIN_ACCESS_KEY` exists in file | **yes** |
| Loaded by API process | **yes** (`EnvironmentFile=` in `deployment/systemd/worldcup-api.service`, `APP_ENV=production`) |
| `gate_configured("admin")` | **true** |
| `gate_configured("super_admin")` | **true** |
| Operator key comparison (live attempts) | **fail** — all live `POST /api/admin/gate/verify` from operator IP returned **403**; no `admin_gate_success` audit entries for real user IDs |

#### Local (`.env`)

| Check | Result |
|-------|--------|
| `ADMIN_ACCESS_KEY` exists | **no** |
| `SUPER_ADMIN_ACCESS_KEY` exists | **no** |
| `gate_configured("admin")` | **false** |
| Key comparison possible | **no** — gate denies before compare (`gate_not_configured`) |

### Live production gate attempts (journalctl)

| Time (UTC) | Request | HTTP | Interpretation |
|------------|---------|------|----------------|
| 18:03:19 | `POST /api/admin/gate/verify` | 403 | Gate rejected (admin role + wrong key **or** non-admin role) |
| 18:28:41 | `GET /api/admin/gate/status` | 403 | **Role check failed** — authenticated user was **not** `admin`/`super_admin` |
| 18:28:59 | `POST /api/admin/gate/verify` | 403 | Same session — non-admin role |

The 18:28 events align with session `dianakamangar@gmail.com` (`role=user`). A `user`-role account cannot pass the admin gate by design.

If the operator sees the Admin Panel **and** reaches the gate prompt while using the `admin` account (15:22 session), failure is because the **correct `ADMIN_ACCESS_KEY` was not supplied** (keys were generated on server at Phase 37B deploy; not in repo, not in operator docs).

---

## 4. Super Admin Visibility

| Check | Result |
|-------|--------|
| Current user role (`admin` account) | `admin` |
| Should Super Admin menu appear? | **no** |
| Why hidden | `canSeeSuperAdminNav()` requires **`role === "super_admin"`** exactly. `admin` is intentionally insufficient. |
| Any `super_admin` user in PostgreSQL? | **no** (all 10 production users checked) |

### Frontend condition

`base44-d/src/lib/roles.js`:

```javascript
export function canSeeSuperAdminNav(user) {
  return user?.role === "super_admin";
}
```

Used in `DashboardLayout.jsx`: `...(showSuperAdminNav ? superAdminItems : [])`.

### Backend condition

- Route: `SuperAdminRoute` → `isSuperAdminUser(user)` → 403 if not `super_admin`.
- Gate: `POST /api/admin/gate/super-admin/verify` → `user_has_super_admin_access(user.role)`.
- Mutations (role/plan changes): `require_super_admin_user` in `worldcup_predictor/api/deps.py`.

**This is working as designed — not a bug.**

---

## 5. PostgreSQL Promotion Commands (DO NOT EXECUTE — for operator use)

### Promote workspace owner to `super_admin` (production)

```sql
UPDATE users
SET role = 'super_admin'
WHERE email = 'kamangar.pedram@gmail.com';
```

### Promote current bootstrap admin to `super_admin` (production)

```sql
UPDATE users
SET role = 'super_admin'
WHERE email = 'admin';
```

### Promote most recent session user (if that account should be operator)

```sql
UPDATE users
SET role = 'super_admin'
WHERE email = 'dianakamangar@gmail.com';
```

After promotion: user must **log out and log back in** (or hard refresh) so `/api/auth/me` returns the new role. Super Admin still requires **`SUPER_ADMIN_ACCESS_KEY`** at the second gate.

---

## 6. Root Cause Determination

| Hypothesis | Verdict | Evidence |
|------------|---------|----------|
| **Wrong role** | **YES (Super Admin)** | Zero `super_admin` rows in PostgreSQL; sidebar/backend require exact role. |
| **Wrong key** | **YES (Admin gate on production)** | Keys exist server-side; operator attempts return 403; Phase 37B report states keys were generated but not distributed. `ADMIN_PASSWORD` ≠ `ADMIN_ACCESS_KEY`. |
| **Env not loaded** | **NO (production)** | systemd `EnvironmentFile`, diagnostic `gate_configured=true`, keys exist. |
| **Env not loaded** | **YES (local only)** | Local `.env` missing both access keys → `gate_configured=false`. |
| **Frontend bug** | **NO** | Deployed bundle gates sidebar; role helpers match backend semantics. |
| **Backend bug** | **NO** | Role from DB on every request; gate logic matches Phase 37A spec; validation suite passed on deploy. |

### Exact root cause (plain language)

1. **Super Admin menu missing** because **no account has the `super_admin` role** — only `admin` exists for the bootstrap operator account.
2. **Admin gate failing** because the operator does **not have the correct `ADMIN_ACCESS_KEY`** (production) or the key is **not configured locally** (local `.env`). The login password is a separate credential and does not unlock the gate.
3. If testing as **`dianakamangar@gmail.com`** (role `user`), the backend correctly returns **403** on all admin gate endpoints — that account should not see admin sidebar on the current production frontend; any gate prompt in that session indicates a stale client session or manual `/admin` navigation with mismatched client state.

---

## 7. Recommended Remediation (operator actions — out of scope for this phase)

1. **Retrieve keys securely from production** (SSH, read `.env.production` on server — do not commit):
   - `ADMIN_ACCESS_KEY`
   - `SUPER_ADMIN_ACCESS_KEY`
2. **Promote designated operator** to `super_admin` using SQL above (one account only).
3. **Add keys to local `.env`** if testing admin gate locally (without committing secrets).
4. **Log out / clear site data** after role changes to refresh `AuthContext`.
5. Use **`admin` account** (or promoted `super_admin` account) — not a regular registered user — when testing admin features.

---

## 8. Files Inspected (read-only)

| Area | Path |
|------|------|
| Role helpers | `base44-d/src/lib/roles.js` |
| Sidebar | `base44-d/src/components/dashboard/DashboardLayout.jsx` |
| Route guards | `base44-d/src/components/AdminRoute.jsx`, `SuperAdminRoute.jsx` |
| Gate client | `base44-d/src/lib/adminGate.js`, `AdminGatePrompt.jsx` |
| Auth context | `base44-d/src/lib/AuthContext.jsx` |
| Gate backend | `worldcup_predictor/access/admin_gate.py` |
| Gate routes | `worldcup_predictor/api/routes/admin_gate.py` |
| Auth / role resolution | `worldcup_predictor/api/web_auth.py`, `worldcup_predictor/api/deps.py` |
| Settings | `worldcup_predictor/config/settings.py` |
| systemd | `deployment/systemd/worldcup-api.service` |
| Deploy context | `PHASE_37B_PRODUCTION_DEPLOY_REPORT.md` |

---

**Diagnostic complete. No code changes. No deploy.**
