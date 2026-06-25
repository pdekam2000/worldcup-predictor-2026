# BILLING PURCHASE ERROR AUDIT + FIX REPORT

**Date:** 2026-06-21  
**Status:** **CODE DEPLOYED — STRIPE PRICE IDs MUST BE UPDATED BY OPERATOR**  
**Backup:** `/opt/worldcup-predictor/backups/deploy-billing-purchase-20260621-*`

---

## Executive summary

A Free user attempting to buy Starter saw a checkout error because **Stripe checkout session creation failed** with:

```
InvalidRequestError: No such price: 'price_1Tkdfw2M4VnLWVPvq08GHKzz'
```

All Stripe **credentials are present** on production, but **`STRIPE_STARTER_PRICE_ID` / `STRIPE_PRO_PRICE_ID` do not exist in the Stripe account tied to `STRIPE_SECRET_KEY`**.

Before the fix, readiness incorrectly reported `checkout_enabled=true`, so the UI showed a Checkout button and users hit a **502** with `"Could not create checkout session"`.

After the fix, readiness reports `checkout_enabled=false` with **"This plan is not available yet."** and the UI shows that message instead of a crash.

---

## Root cause

| Layer | Finding |
|-------|---------|
| **Primary** | Invalid Stripe Price IDs in `.env.production` — IDs are set but not found in the configured Stripe test account |
| **Secondary** | `readiness()` did not validate price IDs against Stripe, so checkout appeared enabled |
| **Tertiary** | Generic 502 error message confused users; frontend showed "Checkout unavailable" without explaining plan/config issue |

**Not the cause:** Missing `STRIPE_SECRET_KEY`, wrong endpoint (frontend correctly uses `POST /api/billing/create-checkout-session`), auth bugs, or WDE/prediction changes.

---

## Purchase flow audit

| Step | Component | Status |
|------|-----------|--------|
| 1 | User clicks **Upgrade to Starter** on `/subscription` | OK |
| 2 | `UpgradeComingSoonDialog` opens with `planKey=starter` | OK |
| 3 | `GET /api/billing/readiness` | **Now returns `checkout_enabled=false`** when prices invalid |
| 4 | `POST /api/billing/create-checkout-session` `{plan:"starter"}` | **Was 502; now 503 with clear message** |
| 5 | Legacy `GET/POST /api/billing/checkout` | Returns placeholder JSON (no session URL) — **not used by current UI** |
| 6 | Success/cancel URLs | Configured: `/billing/success`, `/billing/cancel` |
| 7 | Stripe webhook | Configured (`STRIPE_WEBHOOK_SECRET` present) — inactive until valid prices + payments |

**Correct checkout endpoint:** `POST /api/billing/create-checkout-session`  
**Legacy paths preserved (no 404):** `/api/billing/checkout`, `/api/subscription/checkout`, `/api/stripe/create-checkout-session`

---

## Production config status (secrets not printed)

| Variable | Status |
|----------|--------|
| `STRIPE_SECRET_KEY` | **Present** |
| `STRIPE_WEBHOOK_SECRET` | **Present** |
| `STRIPE_STARTER_PRICE_ID` | **Present but INVALID in Stripe account** |
| `STRIPE_PRO_PRICE_ID` | **Present** (likely same issue — not fully verified) |
| `STRIPE_SUCCESS_URL` | **Present** |
| `STRIPE_CANCEL_URL` | **Present** |
| `STRIPE_MODE` | **test** |
| Stripe Python package | **Installed** |
| `checkout_enabled` (before fix) | **true** (misleading) |
| `checkout_enabled` (after fix) | **false** |
| Readiness message (after fix) | **"This plan is not available yet."** |

---

## Test user reproduction (production)

```
login_status 200
readiness.checkout_enabled false
readiness.message "This plan is not available yet."
create_checkout_status 503
create_checkout.detail.message "This plan is not available yet."
create_checkout.detail.code "stripe_price_invalid"
```

Stripe diagnostic (message only):

```
error_type InvalidRequestError
user_message No such price: 'price_1Tkdfw2M4VnLWVPvq08GHKzz'
param line_items[0][price]
```

---

## Fix applied

### Backend

| File | Change |
|------|--------|
| `worldcup_predictor/billing/user_messages.py` | Central user-facing messages |
| `worldcup_predictor/billing/stripe_client.py` | `validate_price_id()`; map "No such price" → friendly error |
| `worldcup_predictor/billing/billing_service.py` | Readiness validates prices via Stripe API; disables checkout when invalid |
| `worldcup_predictor/api/routes/billing.py` | Consistent error responses via `message_for_code()` |

### Frontend

| File | Change |
|------|--------|
| `base44-d/src/lib/checkoutErrors.js` | Map API error codes to friendly messages |
| `base44-d/src/components/subscription/UpgradeComingSoonDialog.jsx` | Show readiness message; improved checkout error display |

### User-facing messages

| Condition | Message |
|-----------|---------|
| Stripe not configured / SDK missing | "Payment checkout is not active yet." |
| Price ID missing or invalid in Stripe | "This plan is not available yet." |
| Pro user tries Starter | "Cannot checkout for the same or lower plan tier." |
| Rate limited | "Too many checkout attempts. Please try again later." |

### Unchanged (per rules)

- Prediction engine, WDE, raw probabilities
- Stripe webhook verification flow
- Existing Pro users (no downgrades)
- `/api/predictions/{id}` fast 404 hotfix

---

## Validation

```bash
python scripts/validate_billing_purchase_error.py
```

**Local:** 20/20 PASS  
**Production backend:** 18/19 PASS (frontend source file check skipped on prod — expected)

**Production smoke:** SMOKE_ALL_PASS

---

## Deploy result

| Item | Result |
|------|--------|
| Backend billing modules | Deployed + restarted |
| Frontend dist | Deployed |
| `worldcup-api` | active |
| Legacy checkout routes | 200 (no 404) |
| `/api/predictions/{id}` typo route | 404 preserved |

---

## Operator action required — BEFORE live checkout works

Update `.env.production` on the server with **Price IDs from the same Stripe account** as `STRIPE_SECRET_KEY`:

1. Open [Stripe Dashboard → Products](https://dashboard.stripe.com/test/products) (test mode)
2. Create or locate **Starter (€5/mo)** and **Pro (€19/mo)** recurring prices
3. Copy each `price_...` ID
4. Update on server `/opt/worldcup-predictor/.env.production`:

```env
STRIPE_STARTER_PRICE_ID=price_<your_starter_price_id>
STRIPE_PRO_PRICE_ID=price_<your_pro_price_id>
```

5. Restart API:

```bash
systemctl restart worldcup-api
```

6. Verify:

```bash
curl -s -H "Authorization: Bearer <token>" https://footballpredictor.it.com/api/billing/readiness
# Expect: checkout_enabled=true
```

7. Test checkout with Stripe test card `4242 4242 4242 4242`

**Do not change `STRIPE_SECRET_KEY` unless switching Stripe accounts — key and price IDs must match the same account.**

---

## Rollback plan

1. `systemctl stop worldcup-api`
2. Restore from `/opt/worldcup-predictor/backups/deploy-billing-purchase-20260621-*/repo_snapshot_pre.tar.gz`
3. Restore frontend dist from backup if needed
4. `systemctl start worldcup-api`

---

## Final status

```
BILLING_PURCHASE_ERROR_AUDIT = COMPLETE
BILLING_CHECKOUT_FUNCTIONAL = BLOCKED (invalid Stripe Price IDs)
BILLING_ERROR_UX = FIXED (clear messages, no 502 crash)
```

Checkout will become fully functional once valid Price IDs are added — no further code deploy required.
