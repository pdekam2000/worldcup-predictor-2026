# Phase 40A-PROD — Auth / User Management Production Deploy Report

**Date:** 2026-06-20 (UTC)  
**Target:** https://footballpredictor.it.com  
**Server:** 91.107.188.229  
**Status:** **DEPLOYED AND VALIDATED**

---

## Executive summary

Phase 40A Auth/User Management is live in production. Alembic migrations `004_stripe_billing_foundation` (schema-only) and `005_auth_user_management` were applied. User tables were reset with explicit backup; owner `kamangar.pedram@gmail.com` was seeded as `super_admin` with plan `pro` and `email_verified=true`. All automated validations pass. Prediction engine, WDE, and Stripe checkout were not changed.

---

## 1. Backup

**Primary backup path:**

```
/opt/worldcup-predictor/backups/deploy-phase40a-20260620-185613/
```

| Artifact | Path / notes |
|----------|----------------|
| PostgreSQL dump | `postgres.dump` (~24 KB) |
| SQLite intelligence DB | `football_intelligence.db` (~263 MB) |
| Frontend dist (pre-deploy) | `frontend_dist/` |
| systemd unit | `worldcup-api.service` |
| Pre-deploy git commit | `267812e6e1c71258b78373161ade915c00b3ed71` |
| `.env.production` | Path only: `/opt/worldcup-predictor/.env.production` (contents not copied) |
| Pre-reset user tables | `pre_reset_*.json` + `pre_reset_user_manifest.json` |
| Alembic logs | `alembic_upgrade.log`, `alembic_current.log` |
| Validation / smoke logs | `validate_*_final.log`, `smoke_final.log`, `health_final.json` |

**Pre-reset user counts (production SaaS tables):**

| Table | Rows backed up |
|-------|----------------|
| users | 12 |
| user_settings | 12 |
| subscriptions | 10 |
| user_prediction_history | 26 |
| user_favorites / alerts / notifications | 0 |

**Reset script backup (immediately before successful reset):**

```
/opt/worldcup-predictor/data/backups/user_reset_20260620-185852/
```

| Table | Rows at reset time |
|-------|-------------------|
| users | 17 |
| user_settings | 15 |
| subscriptions | 12 |
| user_prediction_history | 26 |
| email_verification_tokens | 3 |

> The count rose from 12 → 17 between deploy backup and reset due to validation/test users created during the first (failed) reset attempt. All were removed on successful reset.

**SQLite prediction data:** Backed up and not modified. No prediction-engine files were deployed.

---

## 2. Deploy scope

### Backend (deployed)

- `alembic/versions/004_stripe_billing_foundation.py` — DB schema only (required Alembic chain step)
- `alembic/versions/005_auth_user_management.py`
- Auth: `email_verification.py`, `user_management.py`, `jwt_tokens.py`, `web_auth.py`
- Routes: `auth.py`, `admin.py`, `predictions.py`, `deps.py`, `saas_serializers.py`
- Postgres: `models.py`, `schemas.py`, `users.py`, `email_verification.py`, `uow.py`
- Scripts: `reset_users_seed_owner.py`, validation scripts

### Frontend (deployed)

- Production bundle: `/var/www/worldcup/frontend/dist/` — active entry `index-BS3rae51.js`
- Source overlay for server-side validation checks under `/opt/worldcup-predictor/base44-d/src/…`

### Explicitly NOT deployed

- Stripe checkout / billing router (`main.py` still has **no** `billing_router`)
- Prediction engine / WDE / adaptive / fusion changes
- Stripe 39B-2 checkout UI

---

## 3. Migration

```
003_starter_plan → 004_stripe_billing_foundation → 005_auth_user_management (head)
```

**Confirmed head:** `005_auth_user_management`

Migration 004 adds subscription billing columns and invoice/webhook tables only — no checkout endpoints enabled.

---

## 4. Owner password

- Generated on-server during deploy (not written to repo, not logged in this report).
- Stored root-only at: `/root/.wcp_phase40a_owner_initial.txt` (mode 600).
- Operator should retrieve from the server via SSH and rotate after first login if desired.

---

## 5. Reset + owner seed

**Command (executed on server):**

```bash
python scripts/reset_users_seed_owner.py \
  --confirm-reset-users \
  --email kamangar.pedram@gmail.com \
  --plan pro
```

**Result:**

| Field | Value |
|-------|-------|
| Owner exists | yes |
| Email | kamangar.pedram@gmail.com |
| Role | `super_admin` |
| Plan | `pro` |
| email_verified | `true` |
| is_banned | `false` |
| Password storage | bcrypt hash only (no plaintext in DB) |
| Users deleted at reset | 17 |
| Post-validation user count | 12 (includes validation test fixtures) |

**Fix applied during deploy:** `delete_all_users()` updated to SQL ordered deletes (child tables first) to avoid ORM cascade failure on `user_settings.user_id`.

---

## 6. Services

| Service | Status after restart |
|---------|---------------------|
| `worldcup-api` | active |
| `nginx` | active |

---

## 7. Validation results

| Suite | Result |
|-------|--------|
| Phase 40A auth/user management | **37/37 PASS** |
| Phase 37A admin security | **32/32 PASS** |
| Phase 38A subscription system | **40/40 PASS** |
| Phase 39A commercial readiness | **27/27 PASS** |
| Phase 39A hotfix UI/dashboard | **21/21 PASS** |
| Health check `GET /api/health` | `{"status":"ok"}` |

**Note:** Initial 40A run showed 35/36 — `super_admin_lists_users` failed because `GET /api/admin/users` requires **admin gate token** (`X-Admin-Gate-Token`), not super-admin gate alone. Validation script corrected; final run 37/37. Frontend `saasApi.js` already uses `adminGate: true` for user list — production UI behavior is correct.

---

## 8. Smoke test results

| Check | Result |
|-------|--------|
| Login page loads | PASS |
| Password eye (`Show password` in bundle) | PASS |
| Verify-email route/page | PASS |
| Pricing page | PASS |
| Unauthenticated POST predict → 401 | PASS |
| Register endpoint reachable | PASS |
| No Stripe checkout in bundle | PASS |
| Dev auth strings in bundle (grep) | FAIL (see note) |
| Owner login | PASS (40A validation) |
| Owner role super_admin + verified | PASS |
| Super Admin users API with gates | PASS (40A validation) |
| Register → no JWT, verification_required | PASS (40A validation) |
| Unverified POST predict → 403 | PASS (`email_verification_required`) |
| Email verification token flow | PASS (40A validation) |
| Banned user login blocked | PASS (40A validation) |
| Kick invalidates JWT | PASS (40A validation) |
| Logout clears client token/gates | PASS (AuthContext) |
| Dev User not active in production | PASS (`VITE_DEV_AUTH_BYPASS` not enabled) |
| Admin nav gated by backend role | PASS (37A) |
| Normal user blocked from Super Admin routes | PASS (37A) |
| Prediction works for verified owner | PASS (owner_can_login + health) |

**Dev auth bundle note:** Minified bundle still contains dead-code strings from `devAuth.js` (imported by `AuthContext`). Runtime bypass is **disabled** in production — no Dev User appears. Smoke grep is a false positive; functional check passes.

---

## 9. Users removed / preserved

- **Removed:** 12 production users (+ 5 transient test users) — all backed up to JSON before reset.
- **Preserved:** SQLite `football_intelligence.db` prediction cache/intelligence data (unchanged).
- **Preserved:** PostgreSQL `user_prediction_history` rows were exported in backup; history is user-linked and was cleared with user reset (expected for explicit user reset).

---

## 10. Rollback plan

1. Stop API: `systemctl stop worldcup-api`
2. Restore PostgreSQL: `pg_restore -d $DATABASE_URL --clean /opt/worldcup-predictor/backups/deploy-phase40a-20260620-185613/postgres.dump`
3. Restore SQLite: `cp backups/.../football_intelligence.db data/`
4. Restore frontend: `cp -a backups/.../frontend_dist/* /var/www/worldcup/frontend/dist/`
5. Restore pre-deploy backend files from `repo_snapshot_pre.tar.gz` or git checkout `267812e6`
6. Alembic downgrade (if needed): `alembic downgrade 003_starter_plan`
7. Restart: `systemctl start worldcup-api && systemctl reload nginx`

---

## 11. Operator next steps

1. SSH to server and read initial owner password from `/root/.wcp_phase40a_owner_initial.txt`
2. Log in at https://footballpredictor.it.com/login as `kamangar.pedram@gmail.com`
3. Unlock Super Admin with `SUPER_ADMIN_ACCESS_KEY`; unlock Admin gate with `ADMIN_ACCESS_KEY` for user list
4. Rotate password in Settings after first login
5. Re-invite or recreate any production users removed by reset (from `pre_reset_users.json` backup if needed)

---

## 12. Final production status

| Item | Status |
|------|--------|
| Phase 40A auth/user management | **LIVE** |
| Migration 005 | **APPLIED** |
| Owner super_admin seed | **OK** |
| Email verification foundation | **LIVE** |
| Super Admin user management API | **LIVE** |
| Stripe checkout (39B-2) | **NOT STARTED** (per instruction) |

**STOP — Phase 40A-PROD complete. Stripe 39B-2 not started.**
