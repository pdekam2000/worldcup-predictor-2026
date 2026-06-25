# HOTFIX — Email Verification Not Sent On Register

**Date:** 2026-06-21  
**Site:** https://footballpredictor.it.com  
**Code deploy:** Completed  
**SMTP delivery:** **NOT CONFIGURED — emails will not send until SMTP env vars are set**

---

## Root cause

Registration **did create users and verification tokens correctly**, but verification emails were **silently dropped** in production:

1. **SMTP is not configured** on production (see audit below). `send_email()` returned `delivered=False` with channel `dev_log`, and in production the dev log path is disabled — **no email, no user-visible error**.

2. **Register API always returned a success message** implying the email was sent (`"Please verify your email. Check your inbox…"`) regardless of delivery outcome.

3. **No delivery status** was exposed to the frontend, so users had no way to know email was not configured or failed.

The verification token pipeline (`issue_verification_token`, DB storage, `/api/auth/verify-email`) was working; only **delivery + UX** were broken.

---

## Production email config audit (present/missing — no secrets)

| Variable | Status |
|----------|--------|
| `SMTP_HOST` | **MISSING** |
| `SMTP_PORT` | 587 (default) |
| `SMTP_USER` | **MISSING** |
| `SMTP_PASSWORD` | **MISSING** |
| `SMTP_FROM` | **MISSING** |
| `SMTP_USE_TLS` | true (default) |
| `smtp_configured` | **false** |
| `email_operations_ready` | **false** |

**Backup:** `/opt/worldcup-predictor/backups/deploy-hotfix-email-verification-20260621-075021`

---

## Files changed

| File | Change |
|------|--------|
| `worldcup_predictor/notifications/email_delivery.py` | Production-safe skip logging; `email_not_configured` / `send_failed` channels |
| `worldcup_predictor/auth/email_verification.py` | Delivery outcomes; safe logging; `reset_verification_rate_limits()` |
| `worldcup_predictor/api/web_auth.py` | Register returns delivery status |
| `worldcup_predictor/api/routes/auth.py` | Register/resend responses with delivery fields; `/resend-verification-email` alias |
| `base44-d/src/pages/Register.jsx` | Pass delivery state to verify page |
| `base44-d/src/pages/VerifyEmailPage.jsx` | Success/warning messages; resend handling |
| `base44-d/src/pages/Login.jsx` | Unverified message + resend action |
| `base44-d/src/api/authApi.js` | `resendVerificationEmail()` |
| `scripts/validate_hotfix_email_verification_register.py` | Hotfix validation (37 checks) |
| `scripts/deploy_hotfix_email_verification_production.sh` | Deploy + config audit |
| `scripts/deploy_hotfix_email_verification_smoke.sh` | Post-deploy smoke |

**Not changed:** prediction engine, WDE, billing/Stripe, password hashing, auth token logic.

---

## Endpoint behavior

### `POST /api/auth/register`

On success:

```json
{
  "status": "ok",
  "registration_success": true,
  "email_verification_required": true,
  "verification_required": true,
  "verification_email_sent": false,
  "email_delivery_status": "email_not_configured",
  "message": "Account created, but verification email could not be sent because email delivery is not configured…"
}
```

When SMTP works: `verification_email_sent: true`, `email_delivery_status: "sent"`.

On send failure: `email_delivery_status: "send_failed"` (registration still succeeds).

### `POST /api/auth/resend-verification` and `/api/auth/resend-verification-email`

Returns structured response:

- `verification_email_sent`, `email_delivery_status`, `already_verified`
- Unknown email: generic message (no enumeration)
- Already verified: `already_verified: true`
- Rate limited: safe message, no secrets in logs

### `GET /api/auth/verify-email?token=…`

Unchanged — marks user verified when token valid.

### Login (unverified user)

Still allowed (existing policy) but returns `verification_required: true` and message: **"Please verify your email before logging in."**

---

## Frontend behavior

| Screen | Behavior |
|--------|----------|
| **Register** | Redirects to verify page with delivery status |
| **Verify email** | Success text or yellow warning if email not sent; resend button |
| **Login** | Redirects unverified users to verify page; link to resend verification |

---

## Validation results

### Local (full)

```
Hotfix email verification register validation: 37/37 PASS
DEPLOY_READY=YES
```

### Production (deployed)

- API validation: **37/37 PASS** (`--api-only` on server)
- Smoke: `/api/health` OK, resend endpoints **200**
- Live register (no mock): `verification_email_sent=false`, `email_delivery_status=email_not_configured`

---

## Required next step — configure SMTP

Add to `/opt/worldcup-predictor/.env.production` (values from your provider):

```env
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your-smtp-user
SMTP_PASSWORD=your-smtp-password
SMTP_FROM=noreply@footballpredictor.it.com
SMTP_USE_TLS=true
```

Then:

```bash
systemctl restart worldcup-api
```

Verify with a test registration — response should show `verification_email_sent: true`.

Until SMTP is configured, users will see an honest message that verification email could not be sent, and can use **Resend verification email** (which will also report status).

---

## Rollback plan

```bash
BACKUP=/opt/worldcup-predictor/backups/deploy-hotfix-email-verification-20260621-075021

rm -rf /var/www/worldcup/frontend/dist/*
cp -a "${BACKUP}/frontend_dist/." /var/www/worldcup/frontend/dist/

cd /opt/worldcup-predictor
tar xzf "${BACKUP}/repo_snapshot_pre.tar.gz"

systemctl restart worldcup-api
systemctl reload nginx
```

---

## Summary

**Root cause:** SMTP not configured; failures were silent in production.  
**Fix:** Honest delivery status on register/resend, safe logging, improved frontend messaging.  
**Blocker for real emails:** Production still needs `SMTP_*` credentials — **STOP here for email delivery** until ops configures the provider.
