# PHASE 41C — Owner Login Password Reset + Auth Repair

**Date:** 2026-06-20  
**Mode:** Diagnose → Fix → Validate → Report  
**Owner:** `kamangar.pedram@gmail.com`  
**Production:** https://footballpredictor.it.com (`91.107.188.229`)

---

## Executive summary

Owner login was failing with **"Invalid email or password."** Production diagnosis showed the owner row was **missing** from PostgreSQL (only Phase 40A test `super_admin` users remained). A prior manual reset attempt failed because it imported the non-existent module `worldcup_predictor.auth.security` instead of `worldcup_predictor.auth.passwords`.

A safe single-user reset script was created, validated locally (**26/26 PASS**) and on production (**30/30 PASS**), then applied in production. Owner login now returns **HTTP 200** with a JWT and `role=super_admin`.

---

## Root cause

| Factor | Finding |
|--------|---------|
| **Primary** | `kamangar.pedram@gmail.com` **did not exist** in production PostgreSQL at diagnosis time. `login_with_password` → `verify_email_password` returned `None` → generic **"Invalid email or password."** |
| **Secondary** | Manual reset used wrong module path (`worldcup_predictor.auth.security`) — module does not exist. Correct hashing lives in `worldcup_predictor.auth.passwords`. |
| **Not the cause** | Ban, `email_verified`, or role checks — user row was absent before repair. |

**Auth flow (verified):**

1. `POST /api/auth/login` → `login_with_password()` in `worldcup_predictor/api/web_auth.py`
2. Email normalized via `normalize_user_identity()` (strip + lower)
3. Password verified with `bcrypt` via `verify_password()` in `worldcup_predictor/auth/passwords.py`
4. JWT issued with `token_version` from `users.token_version`; mismatched `tv` invalidates old tokens

---

## Files inspected

| File | Purpose |
|------|---------|
| `worldcup_predictor/api/web_auth.py` | `login_with_password`, `register_with_password`, `seed_owner_account`, JWT + `token_version` |
| `worldcup_predictor/auth/passwords.py` | `hash_password` / `verify_password` (bcrypt) |
| `worldcup_predictor/auth/password_reset.py` | `reset_password_with_token` — same hash + `bump_token_version` |
| `worldcup_predictor/database/postgres/repositories/users.py` | `verify_email_password`, `update_password_hash`, `bump_token_version`, role/ban/active |
| `worldcup_predictor/database/postgres/models.py` | `User.password_hash`, `User.token_version` |
| `worldcup_predictor/api/routes/auth.py` | Login endpoint, JWT issuance via `issue_access_token_for_record` |

---

## Scripts created

### `scripts/reset_owner_login_password.py`

- Args: `--email`, `--password-env` (default `OWNER_LOGIN_PASSWORD`)
- Uses `hash_password()` from `worldcup_predictor.auth.passwords` (same as register/reset)
- **Existing user:** updates hash, sets `email_verified=true`, `is_active=true`, clears ban, `role=super_admin`, bumps `token_version`, preserves/sets `pro` plan
- **Missing user (production repair):** seeds via `seed_owner_account()` then bumps `token_version`
- Never prints password; output:

```
PASSWORD_RESET_OK
<email>
<role>
<email_verified>
<is_active>
<is_banned>
```

### `scripts/validate_phase41c_owner_login_password_reset.py`

- Local: **26/26 PASS**
- Production (`PHASE41C_REQUIRE_OWNER=1`): **30/30 PASS**
- Covers: hash change, login success/failure, JWT, `/me`, old token invalidation, no password leak, role/plan preservation, create-if-missing path

### `scripts/deploy_phase41c_owner_login_hotfix.sh`

- Server-only helper: generates `/root/.wcp_phase41c_owner_login.txt` (mode 600) if absent, runs reset, restarts API, smoke-tests login (no password in logs)

---

## Validation results

### Local

```
Phase 41C validation: 26/26 PASS
```

### Production (after hotfix)

```
Phase 41C validation: 30/30 PASS
  owner_exists — kamangar.pedram@gmail.com
  owner_role_super_admin — super_admin
  owner_login_with_password
  owner_login_endpoint_jwt
  ...
```

### Production smoke (hotfix run)

```
PASSWORD_RESET_OK
kamangar.pedram@gmail.com
super_admin
true
true
false
login_http_status=200
login_has_jwt=True
login_role=super_admin
```

---

## Exact production command

```bash
export OWNER_LOGIN_PASSWORD='...'   # min 8 chars; do not log
cd /opt/worldcup-predictor
sudo -u www-data env OWNER_LOGIN_PASSWORD="$OWNER_LOGIN_PASSWORD" PYTHONPATH=/opt/worldcup-predictor bash -lc \
  'set -a && source .env.production && set +a && .venv/bin/python scripts/reset_owner_login_password.py \
    --email kamangar.pedram@gmail.com --password-env OWNER_LOGIN_PASSWORD'
sudo systemctl restart worldcup-api
```

**Applied in this phase** via `scripts/deploy_phase41c_owner_login_hotfix.sh` (password generated/stored at `/root/.wcp_phase41c_owner_login.txt`, mode 600).

---

## Final login status

| Check | Status |
|-------|--------|
| User exists | ✅ `kamangar.pedram@gmail.com` |
| Role | ✅ `super_admin` |
| `email_verified` | ✅ `true` |
| `is_active` / `is_banned` | ✅ active, not banned |
| Plan | ✅ `pro` |
| `POST /api/auth/login` | ✅ **200** + JWT |
| Wrong password | ✅ **401** |
| Old JWT after reset | ✅ **401** (token_version bump) |

**Operator:** Read the login password from `/root/.wcp_phase41c_owner_login.txt` on the server (SSH as root). Change it after first login if desired via the app or by re-running the reset command with a new `OWNER_LOGIN_PASSWORD`.

---

## Scope preserved

- No prediction engine changes
- No Stripe/billing changes
- No mass user reset or data deletion
- No plaintext passwords in database or logs
- `super_admin` role and `pro` plan preserved/ restored

---

**Phase 41C complete. STOP.**
