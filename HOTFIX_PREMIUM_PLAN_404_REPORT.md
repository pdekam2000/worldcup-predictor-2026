# HOTFIX — Premium Plan 5€ Button 404

**Date:** 2026-06-21  
**Site:** https://footballpredictor.it.com  
**Status:** Deployed  
**Validation:** 32/32 PASS (local full) · 32/32 PASS (production `--api-only` + smoke)

---

## Root cause

Two issues combined into a broken upgrade experience for Pro/Premium users:

1. **Frontend plan-tier logic was too narrow.** `SubscriptionPage` only disabled the plan card when `plan.key === currentPlan`. A Pro user (`currentPlan === "pro"`) could still click **Upgrade to Starter** (€5) because `starter !== pro`. That opened the checkout dialog and could call `POST /api/billing/create-checkout-session` for a lower tier.

2. **Legacy checkout paths returned HTTP 404.** Older or mistaken client paths (`/api/subscription/checkout`, `/api/stripe/create-checkout-session`) were never registered. Any client hitting those saw FastAPI `404 Not Found` instead of a safe JSON response.

3. **Error parsing masked real API errors.** `saasApi.js` did not read FastAPI `detail.message` objects, so users often saw generic `Request failed (404)` / `Request failed (409)` instead of actionable text.

Production billing routes (`/api/billing/readiness`, `/api/billing/create-checkout-session`) were already deployed and working; the primary user-facing bug was **Pro users being offered a Starter purchase** plus **404 on legacy paths**.

---

## Files changed

| File | Change |
|------|--------|
| `base44-d/src/lib/pricingPlans.js` | Added `normalizePlanKey`, `planRank`, `canUpgradeTo`, `isPremiumPlan` |
| `base44-d/src/pages/SubscriptionPage.jsx` | Premium Active badge; tier-aware buttons; block lower-tier checkout |
| `base44-d/src/components/subscription/UpgradeComingSoonDialog.jsx` | Block checkout for current/lower tiers; inactive checkout message |
| `base44-d/src/api/saasApi.js` | Parse FastAPI `detail.message` + error codes |
| `worldcup_predictor/billing/schemas.py` | `checkout_configured`, `message` on readiness |
| `worldcup_predictor/billing/billing_service.py` | Populate new readiness fields |
| `worldcup_predictor/api/routes/billing.py` | Legacy compat routes + `/billing/checkout` placeholder |
| `worldcup_predictor/api/main.py` | Register `billing_legacy_router` |
| `scripts/validate_hotfix_premium_plan_404.py` | Hotfix validation (full + `--api-only`) |
| `scripts/deploy_hotfix_premium_plan_404_production.sh` | Production deploy |
| `scripts/deploy_hotfix_premium_plan_404_smoke.sh` | Post-deploy smoke |

**Not changed:** prediction engine, WDE, auth core, Stripe charge logic.

---

## Endpoints / routes fixed

| Path | Before | After |
|------|--------|-------|
| `GET/POST /api/subscription/checkout` | 404 | 200 JSON `{ checkout_configured, checkout_enabled, message }` |
| `GET/POST /api/stripe/create-checkout-session` | 404 | 200 JSON (safe placeholder, no Stripe session) |
| `GET/POST /api/billing/checkout` | 404 | 200 JSON (safe placeholder) |
| `GET /api/billing/readiness` | 401 unauth / 200 auth | Unchanged + `checkout_configured`, `message` |
| `POST /api/billing/create-checkout-session` | Unchanged | Still real checkout when configured; 409 for Pro→Starter |

Frontend continues to use **`POST /api/billing/create-checkout-session`** (correct path).

---

## Pro / Premium user behavior

- Header shows **Premium Active** badge on subscription summary.
- Current plan card: **Current Plan** (disabled).
- Lower tiers (e.g. Starter when on Pro): **Included** (disabled) — **no dialog, no API call**.
- Top **Upgrade** button hidden when already on Pro.
- Backend still returns **409 `invalid_upgrade`** if checkout is attempted programmatically (defense in depth).

---

## Free user behavior

- Can open upgrade dialog only for **higher** tiers (`canUpgradeTo`).
- If Stripe checkout is configured (`checkout_enabled` / `checkout_configured`): redirects to Stripe checkout URL (HTTPS validated).
- If checkout is **not** configured: shows **“Payment checkout is not active yet.”** — no navigation to broken routes.
- Legacy paths no longer 404; they return JSON status instead.

---

## Validation results

### Local (full)

```
Hotfix premium plan 404 validation: 32/32 PASS
DEPLOY_READY=YES
```

### Production (deployed)

- Backup: `/opt/worldcup-predictor/backups/deploy-hotfix-premium-plan-404-20260621-073558`
- API validation on server: legacy routes 200, Pro→Starter blocked 409, login OK, subscription OK
- Smoke:
  - `/api/billing/checkout` → 200
  - `/api/subscription/checkout` → 200
  - `/api/stripe/create-checkout-session` → 200
  - Unauthenticated checkout → 401
  - `/api/health` → OK
- Frontend bundle contains `Premium Active` and `Payment checkout is not active yet.`

---

## Deploy steps (executed)

1. `npm run build` in `base44-d/`
2. Tarball: backend billing files + `_deploy_frontend_dist/` + scripts
3. `scp` → `91.107.188.229:/tmp/hotfix_premium_plan_404_deploy.tar.gz`
4. `bash scripts/deploy_hotfix_premium_plan_404_production.sh`
5. `systemctl restart worldcup-api` + nginx reload
6. Smoke tests

---

## Rollback plan

```bash
BACKUP=/opt/worldcup-predictor/backups/deploy-hotfix-premium-plan-404-20260621-073558

# Restore frontend
rm -rf /var/www/worldcup/frontend/dist/*
cp -a "${BACKUP}/frontend_dist/." /var/www/worldcup/frontend/dist/

# Restore backend snapshot (if needed)
cd /opt/worldcup-predictor
tar xzf "${BACKUP}/repo_snapshot_pre.tar.gz"

systemctl restart worldcup-api
systemctl reload nginx
```

Verify rollback: `curl -s -o /dev/null -w '%{http_code}' https://footballpredictor.it.com/api/health` → 200

---

## Summary

Pro users clicking the €5 Starter button no longer trigger checkout. Legacy billing URLs return safe JSON instead of 404. Free users see a clear message when checkout is inactive. No prediction engine, WDE, or auth changes. Production deploy completed successfully.
