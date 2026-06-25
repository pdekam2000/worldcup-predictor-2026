# Phase 44C — Billing Purchase Error Audit + Fix Report

**Date:** 2026-06-21  
**Status:** PHASE_44C_STATUS = **CODE_VALIDATED** (operator Stripe Price IDs may still block live checkout)

## Problem

User reported checkout/purchase error when buying a plan — generic failures, possible 404 on legacy routes, invalid Stripe Price IDs in production.

## Purchase flow traced

### Frontend

| Step | Component |
|------|-----------|
| Subscription page | `base44-d/src/pages/SubscriptionPage.jsx` |
| Plan cards / checkout | Plan selection → POST checkout session |
| Error mapping | `base44-d/src/lib/checkoutErrors.js` |

### Backend

| Step | Route / service |
|------|-----------------|
| Readiness | `GET /api/billing/readiness` |
| Checkout | `POST /api/billing/create-checkout-session` |
| Legacy (no 404) | `/api/billing/checkout`, `/api/subscription/checkout`, `/api/stripe/create-checkout-session` |
| Price mapping | `BillingService.plan_to_price_id()` |
| Validation | `_stripe_prices_valid()`, `validate_checkout_upgrade()` |

## Production config audit

Script: `scripts/audit_stripe_production_env.py` (reports present/missing only — no secret values)

| Variable | Required |
|----------|----------|
| `STRIPE_SECRET_KEY` | present / missing |
| `STRIPE_WEBHOOK_SECRET` | present / missing |
| `STRIPE_STARTER_PRICE_ID` | present / missing |
| `STRIPE_PRO_PRICE_ID` | present / missing |

**Known production issue:** Prior audit found Stripe Price IDs set to placeholder/invalid values. Code now blocks checkout gracefully with user-facing messages instead of generic Stripe errors.

## Fixes (already in codebase)

| Condition | User message |
|-----------|--------------|
| Checkout unavailable | "Payment checkout is not active yet." |
| Invalid/missing price | "This plan is not available yet." |
| Already on plan | Upgrade validation blocks safely |
| Legacy routes | Return structured JSON, not 404 |

Modules: `billing_service.py`, `user_messages.py`, `checkoutErrors.js`, `billing.py` routes.

## Validation

Script: `scripts/validate_phase44c_billing_checkout.py`  
Wraps: `scripts/validate_billing_purchase_error.py`

**Result: 7/7 PASS**

Artifact: `artifacts/phase44c_billing_validation.json`

## Operator action (non-blocking for deploy)

Update production `.env.production`:

```
STRIPE_STARTER_PRICE_ID=price_…   # valid live/test price from Stripe dashboard
STRIPE_PRO_PRICE_ID=price_…
```

Until fixed, checkout returns clear "plan not available" — not silent failure or 404.
