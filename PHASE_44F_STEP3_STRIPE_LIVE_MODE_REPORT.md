# Phase 44F Step 3 — Stripe Live Mode Update Report

**Date:** 2026-06-21  
**Mode:** Config Update → Validate → Report  
**Server:** 91.107.188.229 / https://footballpredictor.it.com  
**Result:** **STOPPED — live Stripe values not available**

---

## Status

| Flag | Value |
|------|-------|
| **PHASE_44F_LIVE_STATUS** | **NOT APPLIED** |
| Env backup (`env.production.bak-phase44f-live`) | **Not created** (no update attempted) |
| `.env.production` modified | **No** |
| `worldcup-api` restarted | **No** |
| Production billing mode | **Unchanged — Stripe test mode** |

Per instructions: because required live values are missing, Step 3 was **stopped before any config change**. No restore was needed (production env untouched).

---

## Pre-flight audit (current production)

Read-only check of `/opt/worldcup-predictor/.env.production` (no secrets printed):

| Variable | Status |
|----------|--------|
| `STRIPE_MODE` | **test** (required: **live**) |
| `STRIPE_SECRET_KEY` | **test** (`sk_test_…`) — required: **live** (`sk_live_…`) |
| `STRIPE_PUBLISHABLE_KEY` | **missing** — required: **live** (`pk_live_…`) |
| `STRIPE_STARTER_PRICE_ID` | **present** — points to **test-mode** price (Phase 44E) |
| `STRIPE_PRO_PRICE_ID` | **present** — points to **test-mode** price (Phase 44E) |
| `STRIPE_WEBHOOK_SECRET` | **present** — tied to **test-mode** webhook |

No `.env.stripe.live` or other live credential file found on the server.

---

## Exact missing / invalid items

All of the following must be supplied before Step 3 can proceed:

1. **`STRIPE_MODE=live`** — currently `test`
2. **`STRIPE_SECRET_KEY`** — live secret key (`sk_live_…`) not in environment
3. **`STRIPE_PUBLISHABLE_KEY`** — missing entirely; live publishable key (`pk_live_…`) required
4. **`STRIPE_STARTER_PRICE_ID`** — must be a **live-mode** recurring EUR price at **€5/month** (`livemode=true`, 500 cents)
5. **`STRIPE_PRO_PRICE_ID`** — must be a **live-mode** recurring EUR price at **€19/month** (`livemode=true`, 1900 cents)
6. **`STRIPE_WEBHOOK_SECRET`** — must be the **live** signing secret for webhook at `https://footballpredictor.it.com/api/billing/webhook`
7. **Live webhook endpoint** — must exist in Stripe Dashboard (live mode) for the production URL

Current Starter/Pro Price IDs are **invalid for live mode** — they were created in test mode during Phase 44E and cannot be reused after switching to `sk_live_…`.

---

## What was NOT done (blocked)

| Task | Status |
|------|--------|
| Backup to `env.production.bak-phase44f-live` | Skipped |
| Update `.env.production` with live values | Skipped |
| `systemctl restart worldcup-api` | Skipped |
| Live checkout validation | Skipped |
| Production smoke (live) | Skipped |

---

## Operator checklist to unblock Step 3

### A. Stripe Dashboard (live mode)

1. Switch Stripe Dashboard to **Live** mode.
2. Create products + recurring prices:
   - **Football Predictor Starter** — €5/month EUR
   - **Football Predictor Pro** — €19/month EUR
3. Copy **live** Price IDs (`price_…` with livemode=true).
4. Developers → API keys → copy **live** `sk_live_…` and `pk_live_…`.
5. Developers → Webhooks → add endpoint:
   - URL: `https://footballpredictor.it.com/api/billing/webhook`
   - Events: `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_succeeded`, `invoice.payment_failed`
6. Copy the **live** signing secret (`whsec_…`).

### B. Provide credentials securely to server

Upload a file (example) **without committing to git**:

```bash
# On server only — /opt/worldcup-predictor/.env.stripe.live
STRIPE_MODE=live
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_STARTER_PRICE_ID=price_...
STRIPE_PRO_PRICE_ID=price_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

Then re-run Step 3 to merge into `.env.production`.

### C. Step 3 commands (when values are ready)

```bash
cp /opt/worldcup-predictor/.env.production /opt/worldcup-predictor/env.production.bak-phase44f-live
# merge live Stripe vars into .env.production
systemctl restart worldcup-api
# run validation + smoke
```

---

## Current production state (unchanged)

Test-mode billing from Phase 44E remains active:

- `checkout_enabled=true` (test mode)
- Test checkout sessions work
- Test webhook configured
- Prediction engine, WDE, auth, history, weather, performance center — **unchanged**

---

## Next action

**Provide live Stripe credentials and live Price IDs**, then re-request Phase 44F Step 3. Until then:

**PHASE_44F_LIVE_STATUS ≠ PRODUCTION_ACTIVE**

---

*No secrets printed. No secrets committed. No environment changes made.*
