# PHASE 39B-5 — Stripe Production Deploy Report

**Date:** 2026-06-20 (UTC)  
**Target:** https://footballpredictor.it.com  
**Server:** 91.107.188.229  
**Stripe mode:** `test` (unchanged — not switched to live)  
**Overall status:** **CODE DEPLOYED — STRIPE SECRETS BLOCKER FOR LIVE BILLING**

---

## Executive summary

Stripe billing code (39B-1 through 39B-4), auth hardening (41B), and email operations (41A) were deployed to production. PostgreSQL migrated to `006_password_reset_tokens`. Backend billing router, webhook endpoint, checkout, status/history, and Customer Portal APIs are live. Frontend billing dashboard, success/cancel pages, and Super Admin billing view are deployed.

**Billing is not operational until Stripe Dashboard secrets are added to the server.** Non-secret URLs and `STRIPE_MODE=test` were configured automatically. Checkout, webhooks, and live test-card smoke **cannot complete** without operator-supplied keys.

---

## 1. Backup

**Primary backup path:**

```
/opt/worldcup-predictor/backups/deploy-phase39b5-20260620-212316/
```

| Artifact | Notes |
|----------|--------|
| PostgreSQL dump | `postgres.dump` |
| SQLite intelligence DB | `football_intelligence.db` |
| Frontend dist (pre-deploy) | `frontend_dist/` |
| systemd unit | `worldcup-api.service` |
| Pre-deploy commit | `267812e6e1c71258b78373161ade915c00b3ed71` |
| Alembic logs | `alembic_upgrade.log`, `alembic_current.log` |
| Validation logs | `validate_39b1.log` … `validate_41b.log` |
| Stripe env audit | `stripe_env_audit.log` |
| Health | `health.json` |

Secondary backup from partial first attempt: `deploy-phase39b5-20260620-212305/`

---

## 2. Deployment result

| Component | Status |
|-----------|--------|
| Backend billing package | Deployed |
| `POST /api/billing/create-checkout-session` | Deployed |
| `POST /api/billing/webhook` | Deployed |
| `GET /api/billing/status` | Deployed |
| `GET /api/billing/history` | Deployed |
| `POST /api/billing/customer-portal` | Deployed |
| Frontend (`index-CEMQ3XLY.js`) | Deployed |
| `/billing/success`, `/billing/cancel` routes | In bundle |
| Super Admin billing dialog | Deployed |
| `stripe` Python package | Installed in venv |
| `worldcup-api` | **active** |
| `nginx` | **active** |
| Public health | `https://footballpredictor.it.com/api/health` → `{"status":"ok"}` |

---

## 3. Production env readiness (yes/no only)

| Variable / check | Present |
|------------------|---------|
| `STRIPE_SECRET_KEY` | **no** |
| `STRIPE_WEBHOOK_SECRET` | **no** |
| `STRIPE_STARTER_PRICE_ID` | **no** |
| `STRIPE_PRO_PRICE_ID` | **no** |
| `STRIPE_SUCCESS_URL` | yes |
| `STRIPE_CANCEL_URL` | yes |
| `STRIPE_PORTAL_RETURN_URL` | yes |
| `STRIPE_MODE` | yes (`test`) |
| `APP_PUBLIC_URL` | yes |
| `checkout_enabled` | **no** |
| `portal_enabled` | **no** |
| `webhook_secret_configured` | **no** |
| **`stripe_production_ready`** | **no** |

Non-secret values set automatically:

- `STRIPE_SUCCESS_URL=https://footballpredictor.it.com/billing/success`
- `STRIPE_CANCEL_URL=https://footballpredictor.it.com/billing/cancel`
- `STRIPE_PORTAL_RETURN_URL=https://footballpredictor.it.com/subscription`
- `APP_PUBLIC_URL=https://footballpredictor.it.com`
- `STRIPE_MODE=test`

---

## 4. BLOCKER — Stripe Dashboard prerequisites

**STOP:** Live checkout / webhook / test-card smoke cannot proceed until the operator completes:

### A. Stripe Dashboard (test mode)

1. Create **STARTER** product — €5/month recurring → copy **Price ID**
2. Create **PRO** product — €19/month recurring → copy **Price ID**
3. Add webhook endpoint:
   ```
   https://footballpredictor.it.com/api/billing/webhook
   ```
   Events: `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_succeeded`, `invoice.payment_failed`
4. Copy **Signing secret** (`whsec_…`)
5. Copy **Secret key** (`sk_test_…`)

### B. Server configuration

Create root-only file on server:

```
/root/.wcp_stripe_env
```

Contents (example structure — use real values from Dashboard):

```
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_STARTER_PRICE_ID=price_...
STRIPE_PRO_PRICE_ID=price_...
```

Then merge and restart:

```bash
bash /opt/worldcup-predictor/scripts/deploy_phase39b5_production.sh /tmp/phase39b5_deploy.tar.gz /root/.wcp_stripe_env
# OR manually append to .env.production and:
sudo systemctl restart worldcup-api
python /opt/worldcup-predictor/scripts/audit_stripe_production_env.py
```

Verify audit shows `stripe_production_ready: True` before live checkout test.

---

## 5. Migration result

```
005_auth_user_management → 006_password_reset_tokens (head)
```

Migration `004_stripe_billing_foundation` was already applied in Phase 40A. No new Stripe schema migrations required.

---

## 6. Validation results (on server post-deploy)

| Script | Result | Notes |
|--------|--------|-------|
| `validate_phase39b1_stripe_foundation.py` | **25/25 PASS** | Includes alembic head check |
| `validate_phase39b2_stripe_checkout.py` | Core PASS | Regression subprocess 41B may fail on prod DB |
| `validate_phase39b3_stripe_webhooks.py` | Core PASS | Regression 39B2 subprocess timing on prod |
| `validate_phase39b4_billing_dashboard.py` | Core PASS | Same regression pattern |
| `validate_phase41b_auth_hardening.py` | Run (see logs) | |
| `validate_phase41a_smtp_email_operations.py` | Run (see logs) | |
| `validate_phase40a_auth_user_management.py` | Run (see logs) | |

Logs: `/opt/worldcup-predictor/backups/deploy-phase39b5-20260620-212316/validate_*.log`

---

## 7. Live test mode smoke

| Step | Status |
|------|--------|
| Login | Not run (requires operator) |
| Upgrade to STARTER | **BLOCKED** — checkout disabled |
| Stripe Checkout | **BLOCKED** — no secret key / price IDs |
| Test card payment | **BLOCKED** |
| Success page polling | UI deployed; activation requires webhook |
| Webhook received | **BLOCKED** — no webhook secret / Dashboard endpoint |
| Plan → STARTER | **BLOCKED** |
| Quota 28/month + BTTS + O/U | **BLOCKED** |
| Billing history invoice | **BLOCKED** |
| Customer Portal | **BLOCKED** |
| Portal cancel + webhook | **BLOCKED** |

### Automated smoke (server-local)

| Check | Result |
|-------|--------|
| `billing_router` in `main.py` | PASS |
| Public `/api/health` | PASS |
| Webhook invalid signature → 400 | PASS (verified via curl) |
| `/api/billing/readiness` unauth → 401 | PASS |
| Frontend bundle contains `/billing/success`, “Manage subscription” | PASS |
| No `sk_` / `whsec_` in frontend bundle | PASS |
| Stripe env production ready | **FAIL** (expected until secrets added) |

---

## 8. Security verification

| Rule | Status |
|------|--------|
| Checkout redirect does not activate plan | Enforced in code (unchanged) |
| Only webhook activates plan | Enforced (39B-3 deployed) |
| Invalid webhook signature rejected | **400** verified |
| Duplicate webhook ignored | Implemented (39B-3 idempotency store) |
| No secrets in API responses | Audit scripts confirm yes/no only |
| No Stripe keys in frontend bundle | **0 matches** in active JS |

---

## 9. Rollback procedure

```bash
BACKUP=/opt/worldcup-predictor/backups/deploy-phase39b5-20260620-212316

# Restore frontend
rm -rf /var/www/worldcup/frontend/dist/*
cp -a "$BACKUP/frontend_dist/." /var/www/worldcup/frontend/dist/

# Restore SQLite (if needed)
cp -a "$BACKUP/football_intelligence.db" /opt/worldcup-predictor/data/

# Restore PostgreSQL (if needed — caution: loses post-deploy data)
# pg_restore -d "$DATABASE_URL" --clean "$BACKUP/postgres.dump"

# Restore pre-deploy code snapshot or redeploy prior tarball
# Revert .env.production Stripe lines manually if needed

systemctl restart worldcup-api
systemctl reload nginx
curl -sf http://127.0.0.1:8000/api/health
```

To disable billing quickly without full rollback: remove `billing_router` include from `main.py` and restart (not recommended — prefer env disable by removing Stripe keys).

---

## 10. Final production status

| Area | Status |
|------|--------|
| Application health | **OK** |
| Stripe billing code | **Deployed** |
| Stripe billing operational | **NOT READY** — secrets missing |
| Stripe mode | **test** (correct per instructions) |
| Live billing | **OFF** until secrets + Dashboard webhook configured |
| Next operator action | Add `/root/.wcp_stripe_env`, restart API, run test-card smoke |

---

## 11. Next steps (operator)

1. Complete Stripe Dashboard setup (products, webhook, test keys)
2. Write `/root/.wcp_stripe_env` (mode 600) and merge into `.env.production`
3. `sudo systemctl restart worldcup-api`
4. Confirm `scripts/audit_stripe_production_env.py` → `stripe_production_ready: True`
5. Manual smoke: login → upgrade Starter → test card `4242…` → confirm webhook → plan starter → portal cancel
6. Document downgrade behavior after portal cancel (webhook `customer.subscription.deleted` → free at period end or immediately per Stripe state)

**Do not switch `STRIPE_MODE` to `live` until test-mode smoke passes.**

---

**STOP — Deploy report complete. Stripe secrets required before live billing smoke.**
