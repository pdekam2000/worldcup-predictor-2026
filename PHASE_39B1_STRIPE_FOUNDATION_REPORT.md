# PHASE 39B-1 — Stripe Foundation Report

**Date:** 2026-06-20  
**Mode:** Implement locally → Validate → Report  
**Production deploy:** NO  
**Checkout / webhooks:** NOT implemented (by design)

---

## Executive Summary

Phase **39B-1** adds the safe Stripe foundation for WorldCup Predictor SaaS: PostgreSQL billing schema, Settings/env loading, Stripe client + billing service skeleton, and a read-only readiness API. Upgrade buttons remain **“Payment system coming soon.”** No plan activation, no checkout, no webhook processing.

**Validation:** `25/25 PASS`  
**Regression:** Phase 39A `27/27 PASS`  
**Local Alembic:** `004_stripe_billing_foundation` applied successfully

---

## 1. Files Changed

### New — Backend

| File | Purpose |
|------|---------|
| `worldcup_predictor/billing/__init__.py` | Billing package exports |
| `worldcup_predictor/billing/schemas.py` | Pydantic schemas + plan mapping errors |
| `worldcup_predictor/billing/stripe_client.py` | Stripe SDK wrapper (import-only in this phase) |
| `worldcup_predictor/billing/billing_service.py` | Readiness + `plan_to_price_id` mapping |
| `worldcup_predictor/api/routes/billing.py` | `GET /api/billing/readiness` |
| `alembic/versions/004_stripe_billing_foundation.py` | DB migration |
| `scripts/validate_phase39b1_stripe_foundation.py` | Phase 39B-1 validation |

### Modified — Backend

| File | Change |
|------|--------|
| `worldcup_predictor/config/settings.py` | Stripe env fields + yes/no properties |
| `worldcup_predictor/config/provider_readiness.py` | Stripe diagnostic keys (yes/no only) |
| `worldcup_predictor/database/postgres/models.py` | Extended `Subscription`, `BillingInvoice`, `StripeWebhookEvent` |
| `worldcup_predictor/api/main.py` | Register billing router |
| `requirements.txt` | `stripe>=8.0.0` enabled |

### Modified — Frontend

| File | Change |
|------|--------|
| `base44-d/src/api/saasApi.js` | Added `fetchBillingReadiness()` (not wired to UI) |

### Unchanged (per rules)

- Prediction engine, WDE, adaptive/fusion, Sportmonks/xG
- `subscription/quota_service.py` logic
- Upgrade coming-soon dialog UX
- Legacy Streamlit `worldcup_predictor/access/stripe_checkout.py` (separate path)

---

## 2. Migration Summary

**Revision:** `004_stripe_billing_foundation`  
**Parent:** `003_starter_plan`

### Extended `subscriptions`

| Column | Type | Notes |
|--------|------|-------|
| `external_customer_id` | VARCHAR(255) | Stripe Customer ID |
| `external_price_id` | VARCHAR(255) | Active Stripe Price |
| `billing_status` | VARCHAR(64) | Stripe subscription status string |
| `current_period_start` | TIMESTAMPTZ | Billing period start |
| `current_period_end` | TIMESTAMPTZ | Billing period end |
| `cancel_at_period_end` | BOOLEAN | Default false |
| `last_payment_status` | VARCHAR(32) | e.g. paid, failed |
| `last_payment_at` | TIMESTAMPTZ | |
| `billing_updated_at` | TIMESTAMPTZ | Last webhook/sync |

**Preserved existing columns:** `provider`, `external_subscription_id`, `start_date`, `end_date` (quota anchor unchanged until 39B-3).

**Indexes:** `external_customer_id`, `external_subscription_id`, `billing_status`

### New table: `billing_invoices`

Full invoice history per user/subscription with Stripe `external_invoice_id` (unique), amounts, URLs, period dates, `paid_at`.

### New table: `stripe_webhook_events`

Idempotency store: unique `stripe_event_id`, `event_type`, `processed`, `processing_error`, etc.

**Downgrade:** Reversible — drops new tables and subscription columns.

---

## 3. Config / Env Behavior

### New environment variables

| Variable | Required for checkout | Startup impact |
|----------|----------------------|----------------|
| `STRIPE_SECRET_KEY` | Yes (future) | None — optional, default empty |
| `STRIPE_WEBHOOK_SECRET` | Yes (webhooks) | None |
| `STRIPE_STARTER_PRICE_ID` | Yes | None |
| `STRIPE_PRO_PRICE_ID` | Yes | None |
| `STRIPE_SUCCESS_URL` | Yes | None |
| `STRIPE_CANCEL_URL` | Yes | None |
| `STRIPE_MODE` | Yes | `test` or `live`; invalid/missing → `missing` |

### Diagnostic output (yes/no only)

`provider_diagnostic()` and `stripe_env_diagnostic()` now include:

- `STRIPE_SECRET_KEY_present`
- `STRIPE_WEBHOOK_SECRET_present`
- `STRIPE_STARTER_PRICE_ID_present`
- `STRIPE_PRO_PRICE_ID_present`
- `STRIPE_MODE` → `test` | `live` | `missing`

**Never prints secret values or price IDs.**

---

## 4. Readiness Behavior

### `BillingService.readiness()`

Returns:

```json
{
  "status": "ok",
  "stripe_configured": false,
  "stripe_mode": "missing",
  "stripe_package_available": true,
  "starter_price_configured": false,
  "pro_price_configured": false,
  "webhook_secret_configured": false,
  "success_url_configured": false,
  "cancel_url_configured": false,
  "checkout_enabled": false
}
```

`stripe_configured=true` only when all required env vars present, Stripe package importable, and `STRIPE_MODE` is `test` or `live`.

### `GET /api/billing/readiness`

- **Auth:** JWT required (same as other user SaaS routes)
- **Unauthenticated:** 401
- **Response:** Readiness object above — no secrets, no price IDs

### Plan mapping (`plan_to_price_id`)

| Plan | Result |
|------|--------|
| `free` | Rejected (`free_plan`) |
| `starter` | `STRIPE_STARTER_PRICE_ID` |
| `pro` | `STRIPE_PRO_PRICE_ID` |
| Unknown | Rejected (`unknown_plan`) |

---

## 5. Validation Results

```bash
python scripts/validate_phase39b1_stripe_foundation.py
# Phase 39B-1 validation: 25/25 PASS
```

Covers: migration file, ORM tables, app startup without Stripe env, diagnostics, readiness, plan rejection/mapping, missing package graceful handling, API auth, frontend API helper, upgrade dialog unchanged.

**Regression:**

```bash
python scripts/validate_phase39a_commercial_readiness.py
# Phase 39A validation: 27/27 PASS
```

---

## 6. Known Limitations

1. **No checkout session endpoint** — Phase 39B-2
2. **No webhook endpoint or plan activation** — Phase 39B-3
3. **No billing history API** — Phase 39B-5
4. **`checkout_enabled` always `false`** until 39B-2+
5. **Quota billing anchor** still uses `start_date` / `created_at` — Stripe period sync in 39B-3
6. **Production migration not applied** — local only; run `alembic upgrade head` on deploy
7. **Legacy Streamlit Stripe** (`access/stripe_checkout.py`) coexists — SaaS billing is separate module
8. **`fetchBillingReadiness()`** added to frontend but not displayed in UI yet

---

## 7. Recommended Next Phase

### **PHASE 39B-2 — Stripe Checkout Session Creation**

- `POST /api/billing/create-checkout-session`
- Rate limiting
- Stripe Customer get/create
- Redirect URL flow
- Set `checkout_enabled=true` when configured
- Still no webhook plan activation (39B-3)

---

## STOP

Phase 39B-1 complete. No production deploy. No checkout. No webhook processing.
