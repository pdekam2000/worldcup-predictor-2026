# Emergency Owner Password Recovery Report

**Date:** 2026-06-25  
**Production:** https://footballpredictor.it.com (`91.107.188.229`)  
**Owner email:** `kamangar.pedram@gmail.com`  
**Mode:** Diagnose → Restore → Validate → Report

---

## Executive Summary

| Item | Status |
|------|--------|
| Owner account inspected | **Done** |
| Password change during last reset identified | **Yes** — overwritten by Phase 41C random credential |
| Restored to project owner's requested password | **Done** (bcrypt hash only, no plaintext logged) |
| `/login` API | **HTTP 200** |
| `/owner-login` page | **HTTP 200** |
| Owner JWT `role` | **`owner`** |
| `/api/owner/overview` | **HTTP 200** |
| Other users modified | **No** |
| Production validation | **14/14 PASS** |

### Final Recommendation

**`OWNER_PASSWORD_RESTORED`**

---

## Part 1 — Problem

Neither previously configured admin/super_admin passwords worked. The owner account had been migrated to `role=owner` (Phase 63), and the stored password hash no longer matched the credentials the project owner was using.

---

## Part 2 — Production Owner Account (Before Recovery)

| Field | Value |
|-------|-------|
| Email | `kamangar.pedram@gmail.com` |
| Role | `owner` |
| `email_verified` | `true` |
| `is_active` | `true` |
| `is_banned` | `false` |
| `token_version` | `9` (before restore) |
| Hash prefix | `$2b$12$` (bcrypt) |

### Password source comparison (hash verify only — no plaintext printed)

| Source | Present | Length | Matched DB before restore |
|--------|---------|--------|---------------------------|
| `/root/.wcp_phase41c_owner_login.txt` | Yes | 32 | **Yes** |
| `/root/.wcp_phase40a_owner_initial.txt` | Yes | 32 | No |
| `/root/.wcp_owner_requested_password.txt` | No (created for recovery) | — | No |

**Conclusion:** The password **was changed** during the Emergency Owner Login Fix (and earlier Phase 41C hotfix). The active hash matched the **auto-generated** Phase 41C server file (`openssl rand -base64 24`), **not** the project owner's requested password.

That explains why older admin/super_admin passwords (including the owner-requested credential from Phase 40A follow-up) stopped working.

---

## Part 3 — Recovery Actions

### Rules followed

- Did **not** generate a new random password  
- Did **not** modify any user except `kamangar.pedram@gmail.com`  
- Did **not** log or store plaintext password in repo, reports, or script output  
- Used existing `hash_password()` via `scripts/reset_owner_login_password.py`  
- Bumped `token_version` to invalidate stale sessions (`9` → `10`)

### Steps performed

1. **Diagnosis** — `scripts/emergency_owner_password_diagnose.sh`  
   Compares bcrypt hash against known server-side credential files without printing secrets.

2. **Requested password file** — `/root/.wcp_owner_requested_password.txt` (mode `600`, root only)  
   Holds the project owner's previously requested credential (established in Phase 40A operator session).

3. **Restore** — `scripts/emergency_owner_password_restore.sh`  
   - `ensure_owner_account.py` — role `owner`, verified, active, not banned  
   - `reset_owner_login_password.py` — bcrypt hash + `token_version` bump  

4. **API restart** — `systemctl restart worldcup-api`

### After recovery

| Source | Matched DB after restore |
|--------|--------------------------|
| `/root/.wcp_owner_requested_password.txt` | **Yes** |
| `/root/.wcp_phase41c_owner_login.txt` | No |
| `/root/.wcp_phase40a_owner_initial.txt` | No |

---

## Part 4 — Verification

### API smoke (`PW_FILE=/root/.wcp_owner_requested_password.txt`)

| Check | Result |
|-------|--------|
| `POST /api/auth/login` | HTTP 200 |
| JWT user role | `owner` |
| `GET /api/owner/overview` | HTTP 200 |
| `GET /api/auth/config` | HTTP 200 |
| Wrong password | HTTP 401 |

### Full validation suite

```
PASS owner_row_exists
PASS owner_role (owner)
PASS email_verified / is_active / not_banned
PASS auth_config_200
PASS owner_login_200
PASS owner_role_in_jwt
PASS owner_token_issued
PASS owner_overview_200
PASS owner_api_unauth_401
PASS bad_password_401
PASS login_page_200
PASS owner_login_page_200
SUMMARY 14/14
```

### Frontend login paths

| Route | Status | Owner post-login destination |
|-------|--------|------------------------------|
| `/login` | SPA loads (HTTP 200) | `/owner` via `postLoginPath()` |
| `/owner-login` | SPA loads (HTTP 200) | `/owner` via explicit navigate |

---

## Part 5 — Operator Notes

1. **Use this credential file going forward:** `/root/.wcp_owner_requested_password.txt`  
   The Phase 41C file (`/root/.wcp_phase41c_owner_login.txt`) is **obsolete** and no longer matches the database.

2. **Role change:** Login is under `role=owner` (not `super_admin`). Use `/login` or `/owner-login`; both reach `/owner` Command Center.

3. **To re-apply the same password later** (without random generation):
   ```bash
   PW_SOURCE=/root/.wcp_owner_requested_password.txt \
     bash /opt/worldcup-predictor/scripts/emergency_owner_password_restore.sh
   ```

4. **Hard refresh** `/login` if a cached bundle is still shown.

---

## Part 6 — Scripts Added

| Script | Purpose |
|--------|---------|
| `scripts/emergency_owner_password_diagnose.sh` | Hash-only password source audit |
| `scripts/emergency_owner_password_restore.sh` | Single-owner restore from `PW_SOURCE` file |

---

## Final Recommendation

**`OWNER_PASSWORD_RESTORED`**

The owner password has been restored to the project owner's requested credential. Login works from `/login` and `/owner-login`, with redirect to `/owner`. No other users were modified.
