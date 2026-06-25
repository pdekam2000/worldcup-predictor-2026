# Phase 44F Step 1 — Stripe Live Readiness Audit

**Date:** 2026-06-21  
**Mode:** Audit only (no deploy, no code changes, no env changes)  
**Server:** 91.107.188.229 / https://footballpredictor.it.com  
**Artifact:** `/opt/worldcup-predictor/artifacts/phase44f_stripe_live_audit.json`

---

## Verdict

# NOT READY

The Stripe **account is activated** and capable of live charges, but the **production environment and live-mode Stripe objects are not configured**. Checkout currently runs in **test mode only** (Phase 44E).

---

## 1. Stripe account activation

Queried via Stripe API (read-only, no secrets printed):

| Check | Status |
|-------|--------|
| Business verification (`details_submitted`) | **Yes** |
| Charges enabled (`charges_enabled`) | **Yes** |
| Payouts enabled (`payouts_enabled`) | **Yes** |
| Pending requirements (`currently_due`) | **0** |
| Account type | `standard` |
| Country | `AT` (Austria) |
| Card payments capability | **active** |

**Conclusion:** Stripe account is **fully activated** for live business operations.

---

## 2. Live API access

| Check | Status |
|-------|--------|
| Live secret key in `.env.production` | **Missing** (only `sk_test_…` present) |
| Live API reachable from server | **No** — cannot query live catalog without `sk_live_…` |

**Missing:** `STRIPE_SECRET_KEY` must be switched from test to **live** secret key.

---

## 3. Live keys in environment

| Variable | Status |
|----------|--------|
| `STRIPE_SECRET_KEY` | **Test only** (`sk_test_…`) — live key **missing** |
| `STRIPE_PUBLISHABLE_KEY` | **Missing** entirely |
| `STRIPE_MODE` | **`test`** (not `live`) |

**Missing items:**

- Live secret key (`sk_live_…`)
- Live publishable key (`pk_live_…`)
- `STRIPE_MODE=live`

---

## 4. Live products

| Mode | Status |
|------|--------|
| Test mode | 2 recurring EUR products exist (Starter, Pro — Phase 44E) |
| Live mode | **Cannot verify** — no live API key on server |

**Missing:** Live-mode **Football Predictor Starter** and **Football Predictor Pro** products (must be created in Stripe Dashboard or via live API).

---

## 5. Live recurring prices

| Plan | Expected | Test mode | Live mode |
|------|----------|-----------|-----------|
| Starter | €5/month EUR | **Exists** | **Not verified / likely missing** |
| Pro | €19/month EUR | **Exists** | **Not verified / likely missing** |

Current env price IDs (`STRIPE_STARTER_PRICE_ID`, `STRIPE_PRO_PRICE_ID`) were **provisioned in test mode** (Phase 44E). They will **not work** after switching to live keys.

**Missing:**

- Live Starter price (`price_…` livemode=true, €5/month EUR recurring)
- Live Pro price (`price_…` livemode=true, €19/month EUR recurring)
- Update `.env.production` with live Price IDs

---

## 6. Taxes configured

| Check | Status |
|-------|--------|
| Stripe Tax settings (live) | **Not verified** — requires live API key |

**Action required before go-live:** Confirm EU/VAT tax handling for Austria (`AT`) and subscription sales. Either:

- Enable **Stripe Tax** in Dashboard and configure defaults, or
- Document manual tax compliance approach and confirm pricing is tax-inclusive/exclusive as intended.

**Missing:** Tax configuration audit in live mode (blocked until live key available).

---

## 7. Customer portal (live mode)

| Check | Status |
|-------|--------|
| Test mode portal | Enabled via API (`portal_enabled: True` in Phase 44E) |
| Live mode portal config | **Not verified** — requires live API key |

**Missing:** Confirm **Billing Portal configuration** exists in Stripe live mode (Dashboard → Settings → Billing → Customer portal).

---

## 8. Webhook (live mode)

| Mode | URL | Status |
|------|-----|--------|
| **Test** | `https://footballpredictor.it.com/api/billing/webhook` | **Configured** (1 endpoint, 6 events) |
| **Live** | Same URL | **Not configured** |

Current `STRIPE_WEBHOOK_SECRET` is tied to the **test-mode** webhook endpoint. Live mode requires a **separate live webhook endpoint** and a **new signing secret** (`whsec_…`).

**Missing:**

- Live-mode webhook endpoint at production URL
- Live `STRIPE_WEBHOOK_SECRET` in `.env.production`

Required events:

- `checkout.session.completed`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.payment_succeeded`
- `invoice.payment_failed`

---

## 9. Stripe warnings / restrictions

| Item | Detail |
|------|--------|
| Account restrictions | **None observed** — no `disabled_reason`, 0 pending requirements |
| Capabilities | Most payment methods **active**; `cartes_bancaires_payments` **pending** (non-blocking for EUR card subscriptions) |
| Test vs live split | All Phase 44E billing objects (prices, webhook secret) are **test-mode only** |
| Publishable key | Not set — optional for Hosted Checkout redirect, but recommended for future Stripe.js/Elements |

---

## Exact missing items checklist

Before switching to live mode, complete **all** of the following:

1. [ ] Add **`STRIPE_SECRET_KEY=sk_live_…`** to `.env.production` (from Stripe Dashboard → Developers → API keys)
2. [ ] Add **`STRIPE_PUBLISHABLE_KEY=pk_live_…`**
3. [ ] Set **`STRIPE_MODE=live`**
4. [ ] Create **live** Starter product + recurring price (€5/month EUR)
5. [ ] Create **live** Pro product + recurring price (€19/month EUR)
6. [ ] Update **`STRIPE_STARTER_PRICE_ID`** and **`STRIPE_PRO_PRICE_ID`** with live Price IDs
7. [ ] Create **live-mode webhook** at `https://footballpredictor.it.com/api/billing/webhook`
8. [ ] Update **`STRIPE_WEBHOOK_SECRET`** with the **live** endpoint signing secret
9. [ ] Confirm **Customer Portal** is configured in live Stripe Dashboard
10. [ ] Confirm **tax/VAT** handling for EU subscription sales
11. [ ] Restart `worldcup-api` after env update
12. [ ] Run live smoke test with a real card (small amount) and verify webhook activates subscription

---

## What is already ready

| Item | Status |
|------|--------|
| Stripe account verified | Yes |
| Charges & payouts enabled | Yes |
| Billing code & routes | Production-active (Phase 44E, test mode) |
| Test checkout flow | Working |
| Test webhook & subscription sync | Working |
| Success/cancel URLs | Configured |

---

## Summary

| Area | Ready? |
|------|--------|
| Stripe account activation | **Yes** |
| Live API keys in env | **No** |
| Live products/prices | **No** |
| Live webhook | **No** |
| Tax configuration (live) | **Unverified** |
| Customer portal (live) | **Unverified** |
| **Overall live readiness** | **NOT READY** |

**Next step (Phase 44F Step 2):** Obtain live keys from Stripe Dashboard, create live catalog + webhook, update `.env.production`, validate, then deploy.

---

*Audit performed read-only. No deployment, code changes, or environment changes were made.*
