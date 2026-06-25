# PHASE 39B-4 — Billing Dashboard + Customer Portal Report

**Date:** 2026-06-20  
**Mode:** Implement locally → Validate → Report  
**Production deploy:** NO  

---

## Executive Summary

Phase **39B-4** gives users visibility and self-service control over Stripe subscriptions after checkout and webhook activation. New APIs expose billing status and invoice history; Stripe Customer Portal opens for paid users with a linked customer. The subscription page and Super Admin panel were updated accordingly.

**Validation:** `25/25 PASS` (`scripts/validate_phase39b4_billing_dashboard.py`)  
**Regressions:** 39B-3 PASS, 39B-2 PASS, 39B-1 `25/25`, 41B PASS, 38A `40/40`

---

## 1. Files Changed

### New — Backend

| File | Purpose |
|------|---------|
| `worldcup_predictor/billing/billing_serializers.py` | Status/history/admin serializers; Stripe ID masking |
| `scripts/validate_phase39b4_billing_dashboard.py` | Phase 39B-4 validation |

### Modified — Backend

| File | Change |
|------|--------|
| `worldcup_predictor/api/routes/billing.py` | `GET /status`, `GET /history`, `POST /customer-portal`; `Depends(get_billing_service)` |
| `worldcup_predictor/api/routes/admin.py` | `GET /api/admin/users/{id}/billing` |
| `worldcup_predictor/api/routes/user.py` | `billing_history` from DB invoices |
| `worldcup_predictor/billing/billing_service.py` | Status, history, portal, admin summary |
| `worldcup_predictor/billing/stripe_client.py` | `create_portal_session()` |
| `worldcup_predictor/billing/schemas.py` | `portal_enabled`, portal request/response |
| `worldcup_predictor/config/settings.py` | `STRIPE_PORTAL_RETURN_URL`, effective URL fallback |
| `worldcup_predictor/database/postgres/repositories/subscriptions.py` | `SubscriptionBillingDetail`, `get_billing_detail()` |
| `worldcup_predictor/database/postgres/repositories/billing_invoices.py` | `list_for_user()`, `count_for_user()` |
| `scripts/validate_phase39b2_stripe_checkout.py` | `dependency_overrides` for billing service |

### Modified — Frontend

| File | Change |
|------|--------|
| `base44-d/src/api/saasApi.js` | `fetchBillingStatus`, `fetchBillingHistory`, `createCustomerPortalSession`, `fetchAdminUserBilling` |
| `base44-d/src/pages/SubscriptionPage.jsx` | Billing status, history, portal button, pending/cancel banners |
| `base44-d/src/pages/BillingCheckoutSuccess.jsx` | Polls billing status until plan activates |
| `base44-d/src/pages/SuperAdminPanel.jsx` | Per-user Billing dialog |

---

## 2. API Behavior

### `GET /api/billing/status` (auth required)

Returns current user billing snapshot — no secrets or price IDs:

- `plan`, `subscription_status`, `billing_status`
- `current_period_start`, `current_period_end`
- `cancel_at_period_end`, `last_payment_status`, `last_payment_at`
- `provider`, `checkout_pending`, `portal_enabled`

### `GET /api/billing/history` (auth required)

Returns invoice list:

- `date`, `amount_paid`, `currency`, `status`
- `period_start`, `period_end`, `hosted_invoice_url`

### `POST /api/billing/customer-portal` (auth + email verified)

- Requires Stripe `external_customer_id` on subscription
- Creates Stripe Billing Portal session
- Returns `{ portal_url }`
- Optional body: `{ return_url }` (defaults to `STRIPE_PORTAL_RETURN_URL` or derived from success URL)

Errors: `409 stripe_customer_missing`, `503 portal_disabled`

### `GET /api/admin/users/{id}/billing` (super admin + gate)

Returns masked billing summary:

- `stripe_customer_id_masked` (e.g. `cus_***1234`)
- Plan, subscription/billing status, period end, last payment, `invoice_count`

---

## 3. Frontend Behavior

### Subscription page

- Loads billing status + history alongside quota/subscription
- Shows **checkout pending** banner when webhook not yet confirmed
- Shows **cancel at period end** warning with renewal date
- **Manage subscription** button → Customer Portal (when `portal_enabled` and paid plan)
- Billing history table with invoice links
- Upgrade options remain for free/starter users

### Checkout success page

- Polls `/api/billing/status` every 2.5s (max 15 attempts)
- Shows “Subscription activated” when plan is starter/pro and not pending
- Does **not** activate plan client-side

### Super Admin

- **Billing** button per user → dialog with masked Stripe customer ID, status, period end, payments, invoice count

---

## 4. Customer Portal Behavior

- Enabled when Stripe checkout config + portal return URL + SDK ready
- User must have completed checkout (Stripe customer ID stored)
- Portal handles cancel, payment method update, invoices (Stripe-hosted)
- Plan changes still authoritative via webhooks only

---

## 5. Security

- Users see only their own billing (JWT-scoped endpoints)
- Super Admin billing requires super-admin role + gate token
- No `STRIPE_SECRET_KEY`, webhook secret, or price IDs in API responses
- Stripe customer IDs masked in admin view
- Portal requires verified, non-banned user (`require_checkout_user`)
- Audit: `stripe_portal_created`, `stripe_portal_failed`

---

## 6. Environment Variables

| Variable | Purpose |
|----------|---------|
| `STRIPE_PORTAL_RETURN_URL` | Customer Portal return URL (optional; falls back from success URL) |
| Existing Stripe vars | Required for portal (secret key, prices, mode) |

---

## 7. Validation Results

```
Phase 39B-4 validation: 25/25 PASS
```

| Check | Result |
|-------|--------|
| Free user billing status | PASS |
| Pro user billing status | PASS |
| Invoice history rows | PASS |
| User-scoped billing (token isolation) | PASS |
| Portal requires Stripe customer | PASS |
| Portal session created when configured | PASS |
| No secrets in responses | PASS |
| Frontend billing UI wired | PASS |
| Super Admin billing view | PASS |
| Regression 39B-3 / 39B-2 / 39B-1 / 41B / 38A | PASS |

---

## 8. Known Limitations

1. **No production deploy** in this phase.
2. **Admin manual plan override** remains separate from Stripe (super-admin PATCH); Stripe remains authority for paid users who checkout.
3. **Portal return URL** must be configured (or derivable from success URL) for portal to enable.
4. **No in-app cancel** — cancellation via Stripe Customer Portal + webhook sync.
5. **Billing history** limited to 50 rows per request (paginated via offset).
6. **Super Admin billing** is a dialog summary, not a full invoice drill-down (invoices visible on user subscription page).

---

## 9. Next Phase

**PHASE 39B-5 — Stripe Production Deploy**

- Configure production Stripe keys, webhook URL, portal return URL
- Deploy backend + frontend
- Register Stripe webhook endpoint on production domain
- Smoke-test checkout → webhook → dashboard flow live

---

**STOP — No deploy. Billing dashboard ready for local/staging use.**
