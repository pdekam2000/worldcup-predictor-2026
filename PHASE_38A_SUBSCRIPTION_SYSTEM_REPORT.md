# Phase 38A — Subscription System V1 Report

**Date:** 2026-06-20  
**Mode:** Implement → Validate → Report  
**Status:** **COMPLETE (local)** — not deployed to production in this phase

---

## Summary

Phase 38A implements production subscription tiers **FREE**, **STARTER**, and **PRO** with monthly prediction quotas, billing-cycle usage tracking, server-side market gating, subscription UI, admin quota tools, and a **Message Admin** contact flow. No Sportmonks/xG expansion work was started.

| Plan | Price | Monthly predictions | Markets |
|------|-------|---------------------|---------|
| **FREE** | €0 | 4 | 1X2 only |
| **STARTER** | €5/mo | 28 | 1X2, BTTS, Over/Under |
| **PRO** | €19/mo | 60 | All markets (incl. future premium) |

Legacy plans `elite` and `unlimited` map to **PRO** limits and market access.

---

## Files Changed / Added

### Backend — new

| File | Purpose |
|------|---------|
| `worldcup_predictor/subscription/billing_period.py` | Monthly billing cycle from subscription anchor |
| `worldcup_predictor/subscription/market_gating.py` | Plan-based payload market filtering |
| `worldcup_predictor/subscription/contact_admin.py` | Message store, email, rate limit, audit |
| `alembic/versions/003_starter_plan.py` | PostgreSQL `subscription_plan` adds `starter` |

### Backend — modified

| File | Change |
|------|--------|
| `worldcup_predictor/database/postgres/enums.py` | `SubscriptionPlan.STARTER` |
| `worldcup_predictor/subscription/plan_limits.py` | Monthly limits, prices, market tiers, features |
| `worldcup_predictor/subscription/quota_service.py` | Monthly quota, billing period, reset, usage detail |
| `worldcup_predictor/subscription/usage_store.py` | `user_prediction_usage` table (monthly) |
| `worldcup_predictor/config/settings.py` | `ADMIN_CONTACT_EMAIL`, SMTP, audit path |
| `worldcup_predictor/api/display_helpers.py` | Market gating on enriched predictions |
| `worldcup_predictor/api/routes/predictions.py` | Pass user role to enrichment |
| `worldcup_predictor/api/routes/user.py` | Monthly quota fields, `POST /contact-admin` |
| `worldcup_predictor/api/routes/admin.py` | `GET /users/{id}/usage`, `POST /users/{id}/quota/reset`, starter in plan patch |

### Frontend — modified

| File | Change |
|------|--------|
| `base44-d/src/pages/SubscriptionPage.jsx` | FREE/STARTER/PRO plans, usage display, Message Admin |
| `base44-d/src/pages/AdminPanel.jsx` | View usage + reset quota per user |
| `base44-d/src/pages/SuperAdminPanel.jsx` | `starter` in plan dropdown |
| `base44-d/src/api/saasApi.js` | `contactAdmin`, `fetchAdminUserUsage`, `resetAdminUserQuota` |

### Validation

| File | Purpose |
|------|---------|
| `scripts/validate_phase38a_subscription_system.py` | 40 automated checks |

---

## Usage Tracking

- **Storage:** SQLite `user_prediction_usage` (`user_id`, `billing_period`, `fixture_id`)
- **Period:** Anchored to subscription `start_date` or `created_at`; rolls monthly
- **Counting rules:**
  - Only **successful** pipeline runs recorded (after POST `/api/predict/{id}` succeeds)
  - **Failed** predictions (422/500) are not counted
  - **Blocked** quota/auth requests (401/402) never reach record step
  - **Cache hits** (GET or POST cache reuse) do not consume quota
  - Re-running the **same fixture** in the same period does not double-count

---

## Market Gating

Applied in `enrich_prediction_payload` via `apply_plan_market_gate`:

| Plan | Visible markets |
|------|-----------------|
| FREE | `match_winner` / 1X2 probabilities only |
| STARTER | + BTTS, Over/Under 2.5 |
| PRO | All (halftime, first goal, goalscorer, premium, etc.) |

Unauthenticated users see **FREE** market scope. Admins see **PRO** scope.

Response includes `plan_markets: { tier, restricted, allowed }` for debugging (no secrets).

---

## UI

**Subscription page (`/subscription`):**
- Current plan name and price
- Used / remaining predictions this billing period
- Upgrade button (routes to Message Admin until Stripe)
- Three plan cards (Free / Starter / Pro)
- **Message Admin** form → `"Message sent successfully"`

**Admin panel:**
- **Usage** button → toast with plan usage summary
- **Reset** button → clears current period usage for user

**Super Admin panel:**
- Plan dropdown includes `starter`

---

## Admin Tools

| Endpoint | Auth | Action |
|----------|------|--------|
| `PATCH /api/admin/users/{id}/subscription?plan=` | Super admin + gate | Change plan |
| `GET /api/admin/users/{id}/usage` | Admin + gate | View period usage |
| `POST /api/admin/users/{id}/quota/reset` | Admin + gate | Reset current period |

Audit events: `admin_quota_reset`, `contact_admin_sent`, `contact_admin_stored`, `contact_admin_rate_limited` → `data/logs/subscription_audit.jsonl`

---

## Message Admin

| Config | Purpose |
|--------|---------|
| `ADMIN_CONTACT_EMAIL` | Recipient (never exposed to users) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | Optional email delivery |

**Flow:**
1. User POSTs `{ subject, message }` to `/api/user/contact-admin`
2. Message stored in SQLite `admin_contact_messages`
3. Email sent if SMTP configured; otherwise stored-only
4. User sees: **"Message sent successfully"**

**Security:**
- Max 3 messages/hour per user+IP
- Min 60s between messages
- No admin email in API responses or frontend

---

## Validation Results

```text
python scripts/validate_phase38a_subscription_system.py
Phase 38A validation: 40/40 PASS
```

Covers: free/starter/pro quotas, market restrictions, billing period, quota reset, contact admin, rate limits, email hidden, admin API auth, UI wiring.

---

## Known Limitations

1. **No Stripe/billing integration** — plan changes are manual (Super Admin) or via Message Admin
2. **Usage in SQLite** — not replicated to PostgreSQL (same pattern as Phase 34 daily usage)
3. **SMTP optional** — messages persist locally if email not configured
4. **Phase 34 regression script** still references daily FREE=1 limit in `PLAN_DAILY_PREDICTION_LIMITS` (kept for backward compat); live enforcement is monthly per 38A
5. **Landing `PricingSection.jsx`** not updated in this phase (subscription page is canonical)

---

## Production Deployment Notes

1. Run `alembic upgrade head` (adds `starter` to `subscription_plan` enum)
2. Set `ADMIN_CONTACT_EMAIL` in `.env.production`
3. Optionally configure SMTP for email delivery
4. Rebuild and deploy frontend
5. Restart `worldcup-api`
6. Run `python scripts/validate_phase38a_subscription_system.py` on server

**Unchanged:** prediction engine, WDE weights, adaptive/fusion formulas, Sportmonks/xG phases.

---

## Rollback Plan

1. Revert `plan_limits.py`, `quota_service.py`, `usage_store.py`, `market_gating.py`, `contact_admin.py`
2. Revert API routes and `display_helpers.py`
3. Revert frontend Subscription/Admin pages
4. PostgreSQL `starter` enum value can remain (harmless)
5. SQLite `user_prediction_usage` table can remain empty

---

## Sign-off

Phase 38A subscription V1 is implemented and validated locally. Ready for production deploy approval when combined with frontend build and env configuration.

**Stopped after report** — no Sportmonks/xG work started.
