# Phase 40A — Auth Database Reset + Super Admin User Management + Email Verification

**Date:** 2026-06-20  
**Mode:** Implement locally → Validate → Report  
**Production deploy:** NO (intentionally skipped)

---

## Executive Summary

Phase 40A fixes the authentication and user-management foundation before Stripe integration. It adds safe user reset + owner seeding, email verification on registration, password visibility toggles, super-admin user management (promote/demote/ban/kick), and session invalidation via `token_version`. Prediction engine, WDE, Stripe, and quota logic were not changed.

**Validation:** `33/33 PASS` (40A) + regressions 37A/38A/39A/39A-hotfix all pass.

---

## 1. Root Cause / Current Auth Gaps (Before 40A)

| Gap | Impact |
|-----|--------|
| `email_verified` column existed but was never enforced | Users could register and run predictions without verification |
| No email verification flow or tokens | No trust/security foundation for SaaS accounts |
| JWT-only sessions with no revocation | Admin “kick” impossible; logout client-side only |
| No ban metadata (`is_banned`, reason, timestamp) | Only manual `is_active` in DB |
| Super Admin UI read-only for users | No ban/kick/promote workflow |
| Register returned JWT immediately | Skipped verification step entirely |
| Dev auth bypass logout kept mock admin user | Confusing local/logout behavior |
| No safe owner seed / user reset tooling | Hard to establish single production owner account |

---

## 2. Files Changed

### Database

| File | Change |
|------|--------|
| `alembic/versions/005_auth_user_management.py` | **New** migration |
| `worldcup_predictor/database/postgres/models.py` | User ban fields, `token_version`, `updated_at`, `EmailVerificationToken` |
| `worldcup_predictor/database/postgres/schemas.py` | Extended `UserRecord` |
| `worldcup_predictor/database/postgres/repositories/users.py` | Ban, verify, kick, delete-all, counts |
| `worldcup_predictor/database/postgres/repositories/email_verification.py` | **New** token repo |
| `worldcup_predictor/database/postgres/uow.py` | Wire `email_verification` repo |

### Backend auth

| File | Change |
|------|--------|
| `worldcup_predictor/auth/email_verification.py` | **New** — tokens, SMTP/dev store, resend rate limit |
| `worldcup_predictor/auth/user_management.py` | **New** — role/ban guards, audit helpers |
| `worldcup_predictor/auth/jwt_tokens.py` | `token_version` (`tv`) in JWT payload |
| `worldcup_predictor/api/web_auth.py` | Verification on register, ban/verify checks, owner seed |
| `worldcup_predictor/api/routes/auth.py` | verify/resend endpoints; register returns pending response |
| `worldcup_predictor/api/deps.py` | `assert_prediction_access()` |
| `worldcup_predictor/api/routes/predictions.py` | Block unverified users on POST predict |
| `worldcup_predictor/api/routes/admin.py` | Ban/unban/kick; enriched user list |
| `worldcup_predictor/api/saas_serializers.py` | Admin user fields |

### Scripts

| File | Change |
|------|--------|
| `scripts/reset_users_seed_owner.py` | **New** safe reset + owner seed |
| `scripts/validate_phase40a_auth_user_management.py` | **New** validation |

### Frontend

| File | Change |
|------|--------|
| `base44-d/src/components/auth/PasswordInput.jsx` | **New** show/hide password |
| `base44-d/src/components/auth/EmailVerificationBanner.jsx` | **New** dashboard banner |
| `base44-d/src/pages/VerifyEmailPage.jsx` | **New** verify + resend UI |
| `base44-d/src/pages/Login.jsx` | Password eye; verification redirect |
| `base44-d/src/pages/Register.jsx` | Password eye; redirect to verify page |
| `base44-d/src/lib/AuthContext.jsx` | Register without token; dev logout fix |
| `base44-d/src/api/authApi.js` | verify/resend; login error codes |
| `base44-d/src/api/saasApi.js` | ban/unban/kick APIs |
| `base44-d/src/pages/SuperAdminPanel.jsx` | Full user management table |
| `base44-d/src/components/AdminGatePrompt.jsx` | Password eye on gate key |
| `base44-d/src/components/dashboard/DashboardLayout.jsx` | Verification banner |
| `base44-d/src/App.jsx` | `/verify-email` route |

**Not changed:** Prediction engine, WDE/adaptive/fusion, Stripe billing foundation (39B-1), subscription quota rules.

---

## 3. DB Migration

**Revision:** `005_auth_user_management` (after `004_stripe_billing_foundation`)

**Users table additions:**

- `is_banned` (bool, default false)
- `banned_at`, `banned_reason`
- `updated_at`
- `token_version` (int, default 0)

**New table:** `email_verification_tokens`

- Hashed token, expiry, single-use `used_at`, FK to users

Apply locally:

```bash
python -m alembic upgrade head
```

---

## 4. Reset Script Behavior

**Script:** `scripts/reset_users_seed_owner.py`

| Rule | Behavior |
|------|----------|
| Safety flag | Requires `--confirm-reset-users` or exits |
| Backup | Exports user-related PG tables to `data/backups/user_reset_<timestamp>/` |
| Delete | Removes all users (CASCADE to settings/subscriptions/etc.) |
| Preserve | SQLite prediction data; admin audit logs not deleted |
| Owner email | Default `kamangar.pedram@gmail.com` |
| Owner role | `super_admin` |
| Owner plan | `pro` (default; `--plan` override) |
| Password | From `OWNER_INITIAL_PASSWORD` env or secure prompt — **never hardcoded** |
| Existing owner | Updates role/verified/password; no duplicate |

Example (production prep — run manually when approved):

```bash
export OWNER_INITIAL_PASSWORD='your-secure-password'
python scripts/reset_users_seed_owner.py --confirm-reset-users --email kamangar.pedram@gmail.com --plan pro
```

---

## 5. Email Verification Behavior

| Step | Behavior |
|------|----------|
| Register | User created `email_verified=false`; **no JWT** returned |
| Token | Secure random token; SHA-256 hash stored; 24h expiry; single-use |
| SMTP configured | Verification email sent |
| SMTP not configured | Dev-only record in `data/dev/email_verification_tokens.jsonl` (non-production) |
| Verify | `GET /api/auth/verify-email?token=...` |
| Resend | `POST /api/auth/resend-verification` — generic response (no email enumeration) |
| Rate limit | 3/hour, 60s min interval per email |
| Login (unverified) | JWT issued but `verification_required` flag; banner in app |
| Predictions | POST `/api/predict/*` blocked until verified (admins exempt) |

---

## 6. Super Admin User Tools

**Panel:** Super Admin → Users tab

| Column | Shown |
|--------|-------|
| email, role, plan | yes |
| email verified | yes |
| active/banned | yes |
| last login | yes |
| predictions this period | yes |

| Action | API | Gate |
|--------|-----|------|
| Promote/demote role | `PATCH /api/admin/users/{id}/role` | super_admin + gate |
| Ban / unban | `POST .../ban`, `POST .../unban` | super_admin + gate |
| Kick session | `POST .../kick` | Bumps `token_version` |
| Reset quota | existing endpoint | admin + gate |

**Protections:**

- At least one `super_admin` must remain
- Self ban/role change requires `confirm_self=true`
- Cannot kick own session
- All actions audited (`user_promoted`, `user_demoted`, `user_banned`, `user_unbanned`, `user_kicked`, `owner_seeded`, `user_reset_performed`)

---

## 7. Auth / Logout Fixes

- Dev auth bypass logout now clears tokens and redirects to login (no persistent mock admin)
- Logout clears admin gate tokens (existing)
- Sidebar admin links still gated by backend-confirmed role (37A preserved)
- `VITE_DEV_AUTH_BYPASS` must never be enabled in production builds

---

## 8. Validation Results

```bash
python scripts/validate_phase40a_auth_user_management.py
# Phase 40A validation: 33/33 PASS
```

| Suite | Result |
|-------|--------|
| Phase 40A | **33/33 PASS** |
| Phase 37A admin security | **32/32 PASS** |
| Phase 38A subscription | **40/40 PASS** |
| Phase 39A commercial | **27/27 PASS** |
| Phase 39A hotfix | **21/21 PASS** |

---

## 9. Production Deployment Checklist (when ready)

1. **Backup** PostgreSQL + `.env.production` path (no secrets in logs)
2. **Deploy** backend + frontend overlays
3. **Migrate:** `alembic upgrade head` (005)
4. **Configure SMTP** for verification emails (or accept dev token file only on staging)
5. **Set** `APP_PUBLIC_URL=https://footballpredictor.it.com`
6. **Run owner reset** (once, with `--confirm-reset-users` and `OWNER_INITIAL_PASSWORD`)
7. **Distribute** admin/super-admin gate keys securely
8. **Validate** on server: `validate_phase40a_auth_user_management.py` + regressions
9. **Smoke:** register → verify email → login → predict; super-admin user actions

---

## 10. Rollback Plan

1. `alembic downgrade 004_stripe_billing_foundation` (drops 005 columns/tables)
2. Restore PostgreSQL from pre-deploy backup if user data was reset
3. Redeploy previous backend/frontend bundle
4. Restart `worldcup-api`

Note: Downgrade removes ban/verification columns; users created under 40A rules may need re-verification after re-upgrade.

---

## STOP

Phase 40A complete locally. No production deploy performed.
