# PHASE 41D — User Change Password in Settings

**Date:** 2026-06-20  
**Mode:** Diagnose → Implement → Validate → Report  
**Deploy status:** **Not deployed** — awaiting approval

---

## Executive summary

Logged-in users (including `super_admin`) can now change their own password from **Settings → Security → Change Password**. The backend validates the current password, enforces existing rules, re-hashes with bcrypt, bumps `token_version` (invalidating the current JWT), and requires re-login. Local validation: **22/22 PASS**.

---

## Root cause / prior state

The Settings page had a disabled **Change Password** button with no backend support. Password changes were only possible via forgot/reset flow (email token) or admin scripts — not from in-app settings.

---

## Files changed

| File | Change |
|------|--------|
| `worldcup_predictor/auth/change_password.py` | **New** — core change-password logic |
| `worldcup_predictor/api/routes/auth.py` | **Added** `POST /api/auth/change-password` |
| `base44-d/src/api/authApi.js` | **Added** `changePassword()` |
| `base44-d/src/pages/SettingsPage.jsx` | **Added** Change Password form (current / new / confirm) |
| `base44-d/src/pages/Login.jsx` | **Added** info banner for post-change re-login message |
| `scripts/validate_phase41d_change_password.py` | **New** validation suite |

**Not changed:** prediction engine, subscription/billing logic, existing settings persistence, JWT structure, password reset flow.

---

## Backend endpoint

### `POST /api/auth/change-password`

**Auth:** Bearer JWT required (`get_current_user`)

**Request body:**

```json
{
  "current_password": "...",
  "new_password": "...",
  "confirm_password": "..."
}
```

**Validation & error codes:**

| Condition | HTTP | `code` |
|-----------|------|--------|
| Not logged in | 401 | (FastAPI auth) |
| Wrong current password | 400 | `current_password_invalid` |
| New ≠ confirm | 400 | `password_mismatch` |
| New &lt; 8 chars | 400 | `password_too_weak` |
| New = current | 400 | `password_same_as_old` |
| User missing | 401 | `unauthorized` |

**On success:**

```json
{
  "password_changed": true,
  "relogin_required": true,
  "message": "Password changed successfully."
}
```

**Side effects:**

- `users.password_hash` updated via `hash_password()` (`worldcup_predictor.auth.passwords`)
- `users.token_version` incremented (+1)
- `users.updated_at` touched (via repository)
- Auth audit events: `password_change_success` / `password_change_failed` (no secrets)

---

## Frontend settings UI

**Location:** `/settings` → **Security** section

**Fields:**

- Current password
- New password
- Confirm new password

**Button:** Change Password (with loading spinner)

**UX:**

- Inline error messages mapped from API `code`
- Success toast: “Password changed — Please log in again…”
- Fields cleared on success
- Session cleared (`logout(false)`) then redirect to `/login` with message: **“Password changed. Please log in again.”**
- Login page shows info banner when redirected from settings
- Uses existing `PasswordInput` component (show/hide toggle)

All other settings sections (language, timezone, notifications, appearance, 2FA preference) are unchanged.

---

## Validation result

```
Phase 41D validation: 22/22 PASS
```

| Test | Result |
|------|--------|
| Unauthenticated rejected | PASS |
| Wrong current password | PASS |
| Confirm mismatch | PASS |
| Weak password | PASS |
| Same as old password | PASS |
| Normal user change | PASS |
| super_admin change | PASS |
| token_version increments | PASS |
| Old password fails after change | PASS |
| New password works | PASS |
| Cannot change another user | PASS |
| Old JWT invalidated | PASS |
| No password in logs/audit tail | PASS |

**Run locally:**

```bash
python scripts/validate_phase41d_change_password.py
```

---

## Deploy steps (after approval)

1. **Backup** (production):
   ```bash
   BACKUP=/opt/worldcup-predictor/backups/deploy-phase41d-$(date +%Y%m%d-%H%M%S)
   mkdir -p "$BACKUP"
   pg_dump "$DATABASE_URL" -Fc -f "$BACKUP/postgres.dump"
   cp -a /opt/worldcup-predictor/worldcup_predictor/auth/change_password.py "$BACKUP/" 2>/dev/null || true
   cp -a /opt/worldcup-predictor/worldcup_predictor/api/routes/auth.py "$BACKUP/"
   ```

2. **Sync code** to `/opt/worldcup-predictor` (backend + `base44-d` frontend build).

3. **Restart services:**
   ```bash
   sudo systemctl restart worldcup-api
   # rebuild/redeploy frontend static assets per existing Phase 39B/40A pipeline
   sudo systemctl reload nginx
   ```

4. **Validate on server:**
   ```bash
   cd /opt/worldcup-predictor
   sudo -u www-data env PYTHONPATH=/opt/worldcup-predictor bash -lc \
     'set -a && source .env.production && set +a && .venv/bin/python scripts/validate_phase41d_change_password.py'
   ```

5. **Manual smoke:** Log in → Settings → change password → confirm redirect to login → log in with new password.

---

## Rollback plan

1. Restore backed-up files:
   ```bash
   cp "$BACKUP/auth.py" /opt/worldcup-predictor/worldcup_predictor/api/routes/auth.py
   rm -f /opt/worldcup-predictor/worldcup_predictor/auth/change_password.py
   ```

2. Restore previous frontend build from backup or prior deploy artifact.

3. Restart API + reload nginx:
   ```bash
   sudo systemctl restart worldcup-api
   sudo systemctl reload nginx
   ```

4. **No database migration required** — rollback is code-only. User password changes made after deploy remain valid (no schema change).

---

## Scope preserved

- Prediction engine untouched
- Subscription / Stripe logic untouched
- No mass password resets
- No password hashes exposed
- Existing JWT + `token_version` session invalidation pattern reused
- All prior Settings preferences preserved

---

**Phase 41D complete. STOP — awaiting deploy approval.**
