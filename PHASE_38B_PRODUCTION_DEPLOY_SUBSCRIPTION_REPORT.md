# Phase 38B — Production Deploy Subscription System V1 Report

**Date:** 2026-06-20  
**Server:** 91.107.188.229  
**App path:** `/opt/worldcup-predictor`  
**Frontend path:** `/var/www/worldcup/frontend/dist`  
**Status:** **DEPLOY OK**

---

## Executive Summary

Phase **38A Subscription System V1** was deployed to production. Monthly quotas (FREE 4 / STARTER 28 / PRO 60), plan-based market gating, Message Admin, and admin usage tools are live. All validation suites passed on production. Market gating smoke test confirms unauthenticated/free-tier users see **1X2 only** on cached predictions.

**Not deployed:** Sportmonks/xG, Goal Minute expansion, Stripe billing.

---

## 1. Backup Paths

| Asset | Location |
|-------|----------|
| **Deploy bundle** | `/opt/worldcup-predictor/backups/deploy-phase38b-20260620-162610/` |
| SQLite DB | `.../football_intelligence.db` |
| PostgreSQL | `.../postgres.dump` |
| Frontend dist (pre-deploy) | `.../frontend_dist/` |
| Repo snapshot (subscription subset) | `.../repo_snapshot_pre.tar.gz` |
| systemd unit | `.../worldcup-api.service` |
| `.env.production` path only | `.../env_production_path.txt` |
| Pre-deploy git commit | `267812e6e1c71258b78373161ade915c00b3ed71` |

---

## 2. Files Deployed

### Backend

| Path | Purpose |
|------|---------|
| `worldcup_predictor/subscription/` | plan_limits, quota_service, usage_store, billing_period, market_gating, contact_admin |
| `worldcup_predictor/config/settings.py` | ADMIN_CONTACT_EMAIL, SMTP settings |
| `worldcup_predictor/database/postgres/enums.py` | `SubscriptionPlan.STARTER` |
| `worldcup_predictor/api/display_helpers.py` | Plan-based market gating on predictions |
| `worldcup_predictor/api/routes/predictions.py` | Role passed to enrichment |
| `worldcup_predictor/api/routes/user.py` | Monthly quota API, contact-admin |
| `worldcup_predictor/api/routes/admin.py` | Usage view, quota reset, starter in plan patch |
| `alembic/versions/003_starter_plan.py` | PostgreSQL enum migration |
| `scripts/validate_phase38a_subscription_system.py` | Production validation |

### Frontend

| Path | Purpose |
|------|---------|
| `base44-d/src/pages/SubscriptionPage.jsx` | FREE/STARTER/PRO, usage, Message Admin |
| `base44-d/src/pages/AdminPanel.jsx` | Usage + reset quota |
| `base44-d/src/pages/SuperAdminPanel.jsx` | Starter in plan dropdown |
| `base44-d/src/api/saasApi.js` | contactAdmin, fetchAdminUserUsage, resetAdminUserQuota |
| Built dist → `/var/www/worldcup/frontend/dist` | Production static assets |

---

## 3. Migration Result

```
alembic upgrade head
Running upgrade 002_super_admin_role -> 003_starter_plan
```

**PostgreSQL `subscription_plan` enum:**

```
free
pro
elite
unlimited
starter
```

Legacy `elite` / `unlimited` map to **PRO** limits (60/month, all markets) in application code.

---

## 4. Environment Configuration (yes/no — no secrets)

| Key | Production status |
|-----|-------------------|
| ADMIN_CONTACT_EMAIL | yes (placeholder added on deploy — **update to real ops email**) |
| SMTP_PORT | yes (587) |
| SMTP_USE_TLS | yes |
| SMTP_HOST | no (optional — messages stored locally until configured) |
| SMTP_USER | optional, not set |
| SMTP_PASSWORD | optional, not set |
| APP_ENV | production (unchanged) |
| API_FOOTBALL_KEY | yes (unchanged, Phase 36C) |
| DATABASE_URL | yes (unchanged) |

No secret values were printed in deploy logs or this report.

**Action required:** Replace placeholder `ADMIN_CONTACT_EMAIL` with the real operations inbox and configure SMTP if email delivery is desired.

---

## 5. Validation Results (production)

| Suite | Result |
|-------|--------|
| Phase 38A subscription | **40/40 PASS** |
| Phase 37A admin security | **32/32 PASS** |
| Phase 36C env wiring | **9/9 PASS** |
| `/api/health` | **200 OK** |

Logs: `/opt/worldcup-predictor/backups/deploy-phase38b-20260620-162610/validate_phase*.log`

---

## 6. Plan Smoke Tests

### Logic smoke (on-server Python)

| Check | Result |
|-------|--------|
| FREE quota = 4/month | PASS |
| STARTER quota = 28/month | PASS |
| PRO quota = 60/month | PASS |
| `elite` → PRO normalization | PASS |
| FREE blocks BTTS | PASS |
| STARTER allows BTTS | PASS |
| STARTER blocks Goal Minute | PASS |
| PRO allows premium markets | PASS |

### Live API — market gating (fixture 1489393, unauthenticated = FREE tier)

| Field | Result |
|-------|--------|
| `plan_markets.tier` | `free` |
| `match_winner` present | yes |
| `btts` present | **no** |
| `over_under_25` present | **no** |
| `first_goal` present | **no** |
| `plan_markets.restricted` | `true` |

### Auth / admin smoke

| Endpoint | Expected | Result |
|----------|----------|--------|
| `POST /api/user/contact-admin` (no auth) | 401 | PASS |
| `GET /api/user/quota` (no auth) | 401 | PASS |
| `GET /api/admin/users/{id}/usage` (no auth) | 401 | PASS |

### Quota behavior (validated in Phase 38A suite on production)

| Rule | Validated |
|------|-----------|
| Successful prediction consumes quota | yes (unit tests on server) |
| Cache hit does not consume quota | yes (design + Phase 34/38A logic) |
| Failed prediction does not consume quota | yes (record only after success) |
| Same fixture in period does not double-count | yes |
| Admin quota reset clears period usage | yes |

Tier-specific quota UI (28/60) requires authenticated users on STARTER/PRO plans — assign via Super Admin panel.

---

## 7. Message Admin Test

| Check | Result |
|-------|--------|
| Message stored in SQLite `admin_contact_messages` | PASS (38A validation) |
| Audit event written | PASS |
| Admin email not in API responses | PASS |
| Admin email not in frontend bundle | PASS |
| Rate limit (3/hour) | PASS |
| User success message | `"Message sent successfully"` |

Email delivery pending until `SMTP_HOST` and credentials are configured. Messages are persisted locally regardless.

---

## 8. Admin Tools (production)

| Capability | Endpoint | Status |
|------------|----------|--------|
| View user usage | `GET /api/admin/users/{id}/usage` | Deployed (admin gate required) |
| Reset quota | `POST /api/admin/users/{id}/quota/reset` | Deployed |
| Change plan | `PATCH /api/admin/users/{id}/subscription?plan=` | Deployed (super admin + gate; includes `starter`) |

---

## 9. Known Limitations

1. **ADMIN_CONTACT_EMAIL** set to deploy placeholder — update before relying on Message Admin email delivery.
2. **SMTP not configured** — contact messages stored in SQLite only.
3. **No Stripe** — plan upgrades via Super Admin or Message Admin request.
4. **Usage tracking in SQLite** — same as Phase 38A design.
5. **Landing page pricing** (`PricingSection.jsx`) not updated — subscription page is canonical.

---

## 10. Rollback Plan

1. Stop API: `systemctl stop worldcup-api`
2. Restore SQLite: `cp .../football_intelligence.db /opt/worldcup-predictor/data/`
3. Restore frontend: `cp -a .../frontend_dist/. /var/www/worldcup/frontend/dist/`
4. Restore repo snapshot: `tar xzf .../repo_snapshot_pre.tar.gz -C /opt/worldcup-predictor`
5. Optional PostgreSQL restore from `postgres.dump`
6. Restart: `systemctl restart worldcup-api nginx`

PostgreSQL `starter` enum value is safe to leave after rollback.

---

## 11. Final Production Status

| Component | Status |
|-----------|--------|
| FREE / STARTER / PRO plans | Live |
| Monthly quota enforcement | Live |
| Market gating on predictions | Live (verified fixture 1489393) |
| Message Admin | Live (store + audit; email pending SMTP) |
| Admin usage / reset tools | Live |
| Super Admin plan controls (incl. starter) | Live |
| Prediction engine / WDE / adaptive / fusion | Unchanged |
| Sportmonks/xG | Not started |

**Deploy completed:** 2026-06-20 16:26 UTC  
**Services:** `worldcup-api` active, `nginx` active

---

## Sign-off

Phase 38B production deploy complete. Subscription System V1 is operational. Update `ADMIN_CONTACT_EMAIL` and optional SMTP when ready for live email delivery.
