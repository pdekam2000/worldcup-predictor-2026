# PHASE 39B-2 — Stripe Checkout Session Creation Report

**Date:** 2026-06-20  
**Mode:** Implement locally → Validate → Report  
**Production deploy:** NO  
**Webhook processing:** NOT implemented (by design)

---

## Executive Summary

Phase **39B-2** enables Stripe Checkout session creation for **STARTER** (€5/mo) and **PRO** (€19/mo) subscriptions. Authenticated, email-verified users can start checkout from the upgrade dialog. **No plan activation or quota changes occur at checkout creation** — activation remains webhook authority (Phase 39B-3).

**Validation:** `30/30 PASS` (`scripts/validate_phase39b2_stripe_checkout.py`)  
**Regressions:** 39B-1 `25/25`, 41B PASS, 41A PASS, 40A PASS, 38A `40/40`

---

## 1. Files Changed

### New — Backend

| File | Purpose |
|------|---------|
| `worldcup_predictor/billing/billing_audit.py` | Audit events: `stripe_checkout_created`, `stripe_checkout_failed`, `stripe_checkout_reused` |
| `worldcup_predictor/billing/checkout_rate_limit.py` | In-memory rate limits (5/hr, 30s min interval) |
| `scripts/validate_phase39b2_stripe_checkout.py` | Phase 39B-2 validation |

### Modified — Backend

| File | Change |
|------|--------|
| `worldcup_predictor/billing/billing_service.py` | `create_checkout_session()`, upgrade validation, session reuse cache, `checkout_enabled` in readiness |
| `worldcup_predictor/billing/stripe_client.py` | `create_customer()`, `create_checkout_session()` (Stripe SDK) |
| `worldcup_predictor/billing/schemas.py` | `CheckoutSessionRequest/Response`, `CheckoutValidationError`; plan validated server-side |
| `worldcup_predictor/api/routes/billing.py` | `POST /api/billing/create-checkout-session`; readiness includes `checkout_enabled` |
| `worldcup_predictor/api/deps.py` | `require_checkout_user` dependency |
| `worldcup_predictor/database/postgres/repositories/subscriptions.py` | `get_external_customer_id`, `set_external_customer_id`, `set_checkout_pending` |
| `scripts/validate_phase39b1_stripe_foundation.py` | `checkout_enabled` true when Stripe SDK + env configured |

### New — Frontend

| File | Purpose |
|------|---------|
| `base44-d/src/pages/BillingCheckoutSuccess.jsx` | “Payment received. Activating subscription…” |
| `base44-d/src/pages/BillingCheckoutCancel.jsx` | “Checkout cancelled.” |

### Modified — Frontend

| File | Change |
|------|--------|
| `base44-d/src/components/subscription/UpgradeComingSoonDialog.jsx` | Readiness gate; checkout redirect when enabled |
| `base44-d/src/api/saasApi.js` | `createCheckoutSession(plan)` |
| `base44-d/src/App.jsx` | Routes `/billing/success`, `/billing/cancel` |

### Unchanged (per rules)

- Prediction engine, WDE, adaptive/fusion, Sportmonks/xG
- Quota logic (`subscription/quota_service.py`)
- Webhook processing
- Production deployment

---

## 2. Endpoint Behavior

### `POST /api/billing/create-checkout-session`

**Auth:** `require_checkout_user` — authenticated, email verified, not banned.

**Request:**
```json
{ "plan": "starter" | "pro" }
```

**Response (200):**
```json
{
  "status": "ok",
  "checkout_url": "https://checkout.stripe.com/...",
  "session_id": "..."
}
```

**Rejections:**

| Condition | HTTP | Code |
|-----------|------|------|
| Unauthenticated | 401 | — |
| Unverified user | 403 | `email_verification_required` |
| Banned / inactive | 401 or 403 | `account_blocked` |
| `plan=free` | 400 | `free_plan` |
| Unknown plan | 400 | `unknown_plan` |
| Already active on same plan | 409 | `duplicate_active_plan` |
| Same/lower tier upgrade | 409 | `invalid_upgrade` |
| Checkout disabled (env) | 503 | `checkout_disabled` |
| Rate limited | 429 | `checkout_rate_limited` |
| Stripe API failure | 502 | varies |

**Does NOT:**

- Change `subscriptions.plan`
- Reset or bump quota
- Mark subscription `ACTIVE`
- Process payment success

**Does:**

- Create or reuse Stripe Customer (`external_customer_id`)
- Create Stripe Checkout Session (subscription mode)
- Set `billing_status = checkout_pending` only
- Attach metadata: `user_id`, `email`, `requested_plan`
- Reuse recent open session (15 min cache) when safe and upgrade still valid

### `GET /api/billing/readiness`

Extended with `checkout_enabled: bool` — `true` only when:

- `STRIPE_SECRET_KEY` present
- `STRIPE_STARTER_PRICE_ID` present
- `STRIPE_PRO_PRICE_ID` present
- `STRIPE_SUCCESS_URL` and `STRIPE_CANCEL_URL` present
- Stripe SDK import OK
- `STRIPE_MODE` is `test` or `live`
- Stripe client `sdk_ready()` passes

No price IDs or secrets in response.

---

## 3. Upgrade Rules

| Current plan | Allowed checkout |
|--------------|------------------|
| FREE | starter, pro |
| STARTER | pro |
| PRO (active) | none (409 duplicate) |
| PRO (inactive/cancelled) | pro (reactivation via webhook later) |

Price IDs resolved server-side from env — never accepted from client.

---

## 4. Stripe Customer Handling

1. Load subscription row for user.
2. If `external_customer_id` exists → reuse.
3. Else → `StripeClient.create_customer(email, metadata.user_id)` → persist on subscription row.
4. Customer creation does not change plan.

---

## 5. Idempotency / Duplicate Control

- **Rate limit:** max 5 checkout creations per user per hour; minimum 30 seconds between attempts.
- **Session reuse:** in-process cache keyed by `user_id:plan` for 15 minutes; upgrade validation runs before reuse so active-plan duplicates cannot slip through cache.
- **Active plan block:** user with active PRO cannot open another PRO checkout (409).

---

## 6. Security Rules

- Authenticated users only; email verification required.
- Banned/inactive users blocked.
- Server-side plan → price ID mapping; client cannot supply price IDs.
- Readiness and API responses expose yes/no flags only — no secrets, no raw price IDs.
- Audit log (`data/logs/billing_audit.jsonl`):
  - `stripe_checkout_created`
  - `stripe_checkout_failed`
  - `stripe_checkout_reused`

---

## 7. Frontend UX

| State | Behavior |
|-------|----------|
| `checkout_enabled=false` | “Payment system coming soon” (unchanged fallback) |
| `checkout_enabled=true` | Starter/Pro buttons call checkout API and redirect to `checkout_url` |
| Loading | Spinner on readiness fetch and checkout button |
| Error | Inline message + toast |
| Success URL page | “Payment received. Activating subscription…” (no plan change client-side) |
| Cancel URL page | “Checkout cancelled.” |

---

## 8. Validation Results

```
Phase 39B-2 validation: 30/30 PASS
```

| Check | Result |
|-------|--------|
| Missing Stripe env → checkout disabled | PASS |
| Readiness true when test env present | PASS |
| Unauthenticated blocked | PASS |
| Unverified user blocked | PASS |
| Banned user blocked | PASS |
| Free / unknown plan rejected (400) | PASS |
| Starter checkout created | PASS |
| Pro checkout created | PASS |
| Stripe customer stored & reused | PASS |
| No plan activation after checkout | PASS |
| Duplicate active PRO blocked (409) | PASS |
| No secrets in responses | PASS |
| Frontend coming-soon fallback | PASS |
| Frontend checkout when enabled | PASS |
| Regression 39B-1 | PASS |
| Regression 41B | PASS |
| Regression 41A | PASS |
| Regression 40A | PASS |
| Regression 38A | PASS |

---

## 9. Known Limitations

1. **No webhook processing** — payment success does not activate plan until Phase 39B-3.
2. **In-memory rate limits / session cache** — per-process only; not shared across workers (acceptable for local; 39B-3+ may need Redis).
3. **Banned users with valid JWT** receive 401 (token rejected at resolve) rather than explicit 403 — still blocked.
4. **`checkout_pending` billing status** is informational only until webhooks sync real Stripe subscription state.
5. **No proration or trial** — straight subscription Checkout Session.
6. **No production deploy** in this phase — Stripe test keys required locally.

---

## 10. Environment Variables

| Variable | Required for checkout |
|----------|----------------------|
| `STRIPE_SECRET_KEY` | Yes |
| `STRIPE_STARTER_PRICE_ID` | Yes |
| `STRIPE_PRO_PRICE_ID` | Yes |
| `STRIPE_SUCCESS_URL` | Yes (e.g. `https://yourdomain/billing/success`) |
| `STRIPE_CANCEL_URL` | Yes (e.g. `https://yourdomain/billing/cancel`) |
| `STRIPE_MODE` | `test` or `live` |
| `STRIPE_WEBHOOK_SECRET` | Not used until 39B-3 |

---

## 11. Next Phase

**PHASE 39B-3 — Stripe Webhook Processing**

- `POST /api/billing/webhook` with signature verification
- Idempotent event store (`stripe_webhook_events`)
- Activate plan + quota on `checkout.session.completed` / `customer.subscription.updated`
- Handle payment failures, cancellations, renewals
- Single authority for plan activation (replacing any redirect-based activation)

---

**STOP — No deploy. No webhook implementation in 39B-2.**
