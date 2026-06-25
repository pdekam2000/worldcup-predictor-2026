# HOTFIX — Temporarily Disable Email Verification Requirement

**Date:** 2026-06-21  
**Site:** https://footballpredictor.it.com  
**Status:** Deployed  
**Config:** `EMAIL_VERIFICATION_REQUIRED=false` (production)

---

## Summary

Users can **register and log in immediately** without email verification while SMTP/Brevo is not yet configured. The full verification system (tokens, resend endpoint, verify link) remains in place for re-enable later.

---

## Config flag

| Setting | Production value | Default (if unset) |
|---------|------------------|-------------------|
| `EMAIL_VERIFICATION_REQUIRED` | **`false`** | `true` |

Set in `/opt/worldcup-predictor/.env.production`:

```env
EMAIL_VERIFICATION_REQUIRED=false
```

Public API: `GET /api/auth/config` → `{ "email_verification_required": false }`

---

## Behavior when disabled (`false`)

| Flow | Behavior |
|------|----------|
| **Register** | User created with `email_verified=true`; **no verification email sent** |
| **Register response** | `email_verification_required=false`, `email_delivery_status="verification_disabled"` |
| **Login** | Normal login; no `verification_required` flag |
| **Predictions** | Allowed (verification gate bypassed) |
| **Resend / verify endpoints** | Still available (unchanged) |

## Behavior when re-enabled (`true`)

Restores prior flow: unverified users, verification emails (when SMTP configured), login `verification_required`, resend works.

---

## Files changed

| File | Change |
|------|--------|
| `worldcup_predictor/config/settings.py` | `EMAIL_VERIFICATION_REQUIRED` setting |
| `worldcup_predictor/auth/verification_config.py` | **New** — flag helper |
| `worldcup_predictor/api/web_auth.py` | Register auto-verify; login gate respects flag |
| `worldcup_predictor/api/deps.py` | Prediction/checkout gates respect flag |
| `worldcup_predictor/api/routes/auth.py` | Register messages; `GET /api/auth/config` |
| `worldcup_predictor/notifications/diagnostics.py` | Includes flag in diagnostics |
| `base44-d/src/pages/Register.jsx` | Redirect to login when verification disabled |
| `base44-d/src/pages/Login.jsx` | Hide resend when disabled |
| `base44-d/src/components/auth/EmailVerificationBanner.jsx` | Hidden when disabled |
| `base44-d/src/api/authApi.js` | `fetchAuthConfig()` |
| `scripts/validate_hotfix_disable_email_verification_requirement.py` | Validation (28 checks) |

**Not changed:** password hashing, verification token storage, resend endpoints, prediction engine, WDE, billing/Stripe.

---

## Validation results

### Local

```
Hotfix disable email verification validation: 28/28 PASS
DEPLOY_READY=YES
```

### Production (deployed)

- API validation: **28/28 PASS**
- `GET /api/auth/config` → `email_verification_required: false`
- Register smoke:
  - `email_verification_required: false`
  - `email_delivery_status: verification_disabled`
  - Message: **"Account created. You can now log in."**
- Login smoke: **200**, JWT issued, no `verification_required`

**Backup:** `/opt/worldcup-predictor/backups/deploy-hotfix-disable-email-verification-20260621-080627`

---

## How to re-enable later (Brevo/SMTP)

1. Configure SMTP in `.env.production`:

```env
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...
SMTP_FROM=noreply@footballpredictor.it.com
SMTP_USE_TLS=true
```

2. Re-enable verification:

```env
EMAIL_VERIFICATION_REQUIRED=true
```

3. Restart API:

```bash
systemctl restart worldcup-api
```

4. Verify: `GET /api/auth/config` → `email_verification_required: true`  
5. Test register → verification email sent; unverified login shows verify prompt.

**Note:** Users registered while verification was disabled already have `email_verified=true` and are unaffected.

---

## Rollback plan

```bash
BACKUP=/opt/worldcup-predictor/backups/deploy-hotfix-disable-email-verification-20260621-080627

# Restore code
cd /opt/worldcup-predictor
tar xzf "${BACKUP}/repo_snapshot_pre.tar.gz"

# Restore env (or set EMAIL_VERIFICATION_REQUIRED=true)
cp "${BACKUP}/env.production" .env.production

# Restore frontend
rm -rf /var/www/worldcup/frontend/dist/*
cp -a "${BACKUP}/frontend_dist/." /var/www/worldcup/frontend/dist/

systemctl restart worldcup-api
systemctl reload nginx
```

---

## Existing users

- **Previously unverified users** can now log in and use predictions while the flag is `false`.
- **Owner/admin accounts** unchanged.
- **Verification tokens** in DB are not deleted.
