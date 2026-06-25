# PHASE 39B-3 — Stripe Webhook Processing Report

**Date:** 2026-06-20  
**Mode:** Implement locally → Validate → Report  
**Production deploy:** NO  

---

## Executive Summary

Phase **39B-3** implements verified Stripe webhook processing as the **sole authority** for paid plan activation, updates, cancellation, and billing invoice records. Checkout success redirects still do **not** activate plans.

**Validation:** `27/27 PASS` (`scripts/validate_phase39b3_stripe_webhooks.py`)  
**Regressions:** 39B-2 `30/30`, 39B-1 `25/25`, 41B PASS, 41A PASS, 38A `40/40`

---

## 1. Files Changed

### New — Backend

| File | Purpose |
|------|---------|
| `worldcup_predictor/billing/plan_mapping.py` | Server-side `price_id_to_plan()` + plan amounts |
| `worldcup_predictor/billing/webhook_handlers.py` | Event dispatch + subscription/invoice logic |
| `worldcup_predictor/billing/webhook_service.py` | Signature verify, idempotency, orchestration |
| `worldcup_predictor/database/postgres/repositories/webhook_events.py` | `stripe_webhook_events` CRUD |
| `worldcup_predictor/database/postgres/repositories/billing_invoices.py` | `billing_invoices` upsert |
| `scripts/validate_phase39b3_stripe_webhooks.py` | Phase 39B-3 validation |

### Modified — Backend

| File | Change |
|------|--------|
| `worldcup_predictor/api/routes/billing.py` | `POST /api/billing/webhook` (no JWT) |
| `worldcup_predictor/billing/stripe_client.py` | `construct_webhook_event()` |
| `worldcup_predictor/database/postgres/repositories/subscriptions.py` | Stripe sync, lookup by customer/subscription ID, downgrade |
| `worldcup_predictor/database/postgres/repositories/__init__.py` | Export new repos |
| `worldcup_predictor/database/postgres/uow.py` | Wire `webhook_events`, `billing_invoices` |

### Unchanged (per rules)

- Prediction engine, WDE, adaptive/fusion, Sportmonks/xG
- Quota counting logic (`quota_service.py`) — only reads `start_date` anchor synced from webhooks
- Production deployment
- Checkout session creation behavior (39B-2)

---

## 2. Webhook Endpoint Behavior

### `POST /api/billing/webhook`

| Requirement | Implementation |
|-------------|----------------|
| Raw body | `await request.body()` |
| Signature | `Stripe-Signature` header + `STRIPE_WEBHOOK_SECRET` |
| No JWT | Public endpoint; signature is auth |
| Invalid signature | HTTP 400, audit `stripe_webhook_invalid_signature` |
| Idempotency | Unique `stripe_event_id` in `stripe_webhook_events` |
| Duplicate event | HTTP 200 `{status: duplicate}` — no reprocessing |

**Response examples:**
```json
{"status": "processed", "event_id": "evt_..."}
{"status": "duplicate", "event_id": "evt_..."}
{"status": "processed_with_error", "event_id": "evt_..."}
```

No secrets, price IDs, or full payloads in API responses or audit detail strings.

---

## 3. Event Handling Matrix

| Stripe event | Primary actions |
|--------------|-----------------|
| `checkout.session.completed` | Link `external_customer_id` + `external_subscription_id`; set `billing_status=checkout_completed`; **no plan activation** |
| `customer.subscription.created` | Map price → plan; if `active`/`trialing` → activate starter/pro; sync period dates to `start_date`/`end_date` (quota anchor) |
| `customer.subscription.updated` | Same as created; supports upgrade (starter→pro) and Stripe-driven plan changes |
| `customer.subscription.deleted` | Downgrade to **free**; clear `external_subscription_id`; keep `external_customer_id` |
| `invoice.payment_succeeded` | Upsert `billing_invoices`; `last_payment_status=succeeded`; keep subscription active |
| `invoice.payment_failed` | Upsert invoice; `last_payment_status=failed`; `billing_status=past_due` or `payment_failed`; **no new paid activation** |

Unsupported event types are stored and marked processed without side effects.

---

## 4. Plan Activation Logic

**Price mapping (env allowlist only):**

| Env variable | Plan |
|--------------|------|
| `STRIPE_STARTER_PRICE_ID` | starter (€5/mo) |
| `STRIPE_PRO_PRICE_ID` | pro (€19/mo) |
| Unknown price | No paid activation; audit error; billing fields updated only |

**Activation conditions:**
- Only on `customer.subscription.created` / `updated` with Stripe status `active` or `trialing`
- Requires known price ID
- Sets `plan`, `status=active`, `provider=stripe`, period fields, `billing_updated_at`

**Grace / non-activation:**
- `past_due`: preserve paid access if already on paid plan; record `billing_status=past_due`
- `incomplete`: `billing_status=incomplete`; no activation
- `cancel_at_period_end=true` with future period end: keep plan until period ends
- `canceled` / `unpaid` / `incomplete_expired`: downgrade to free (or at period end when applicable)

**User resolution order:**
1. Subscription metadata `user_id`
2. `external_subscription_id` lookup
3. `external_customer_id` lookup

Missing user metadata does not crash — event stored, error audited.

---

## 5. Invoice Logic

- Upsert by unique `external_invoice_id`
- Stores amounts (cents→decimal), currency, status, period dates, hosted URL
- Links to local `user_id` and `subscription_id` when resolvable
- `payment_succeeded` → `last_payment_at`, `last_payment_status=succeeded`
- `payment_failed` → failed status; existing paid users marked `past_due`; free users stay free

---

## 6. Idempotency Behavior

1. Verify signature
2. Insert row in `stripe_webhook_events` (or detect duplicate by `stripe_event_id`)
3. If duplicate → return success, skip handler
4. Dispatch handler inside DB transaction
5. Mark `processed=true`, set `processed_at`, optional `processing_error`
6. Commit

Duplicate Stripe deliveries never reapply subscription or invoice changes.

---

## 7. Audit Events

| Event | When |
|-------|------|
| `stripe_webhook_received` | Valid event accepted |
| `stripe_webhook_duplicate` | Duplicate `stripe_event_id` |
| `stripe_webhook_invalid_signature` | Signature verification failed |
| `stripe_subscription_activated` | Paid plan activated (created) |
| `stripe_subscription_updated` | Subscription state sync |
| `stripe_subscription_canceled` | Downgrade / deletion |
| `stripe_invoice_paid` | Invoice payment succeeded |
| `stripe_invoice_failed` | Invoice payment failed |
| `stripe_webhook_processing_error` | Handler error (missing user, unknown price, etc.) |

Log path: configured `subscription_audit_log_path` (JSONL).

---

## 8. Quota / Billing Anchor Sync

On paid activation or renewal via subscription webhooks:

```
subscriptions.start_date = stripe.current_period_start
subscriptions.end_date   = stripe.current_period_end
```

`quota_service._resolve_subscription()` uses `start_date` as monthly billing anchor — no quota logic changes required.

---

## 9. Validation Results

```
Phase 39B-3 validation: 27/27 PASS
```

| Check | Result |
|-------|--------|
| Invalid signature rejected | PASS |
| Valid signature accepted | PASS |
| Duplicate event ignored | PASS |
| checkout.session.completed stored (no activation) | PASS |
| subscription.created activates starter | PASS |
| subscription.updated upgrades to pro | PASS |
| Unknown price does not activate paid plan | PASS |
| subscription.deleted → free | PASS |
| invoice.payment_succeeded creates invoice | PASS |
| invoice.payment_failed no new activation | PASS |
| Missing user metadata no crash | PASS |
| No JWT required | PASS |
| No secrets in responses | PASS |
| Billing anchor dates synced | PASS |
| Regression 39B-2 / 39B-1 / 41B / 41A / 38A | PASS |

---

## 10. Known Limitations

1. **No production deploy** in this phase — configure `STRIPE_WEBHOOK_SECRET` and Stripe Dashboard webhook URL in a future deploy phase.
2. **Single price per subscription** — first line item price used for plan mapping.
3. **Grace period** for `past_due` preserves access while Stripe status remains `active`/`trialing`/`past_due`; hard downgrade follows Stripe `canceled`/`deleted`/`unpaid`.
4. **No Customer Portal** — cancel/manage flows deferred to 39B-4.
5. **No billing status API** for frontend polling — success page still shows “Activating subscription…” until user refreshes.
6. **Webhook processing errors** mark event processed with error (prevents infinite Stripe retries on bad data).
7. **In-memory checkout session cache** (39B-2) unaffected; webhooks are DB-authoritative.

---

## 11. Environment Variables

| Variable | Required for webhooks |
|----------|----------------------|
| `STRIPE_WEBHOOK_SECRET` | Yes |
| `STRIPE_SECRET_KEY` | Yes (SDK verify) |
| `STRIPE_STARTER_PRICE_ID` | Yes (plan mapping) |
| `STRIPE_PRO_PRICE_ID` | Yes (plan mapping) |
| `DATABASE_URL` | Yes (event + subscription storage) |

---

## 12. Next Phase

**PHASE 39B-4 — Billing Dashboard + Customer Portal**

- User-facing billing status (`GET /api/billing/status`)
- Invoice history in UI
- Stripe Customer Portal session for self-service cancel/update payment method
- Success page polling for activation confirmation

---

**STOP — No deploy. Webhook endpoint ready for local/staging Stripe CLI testing.**
