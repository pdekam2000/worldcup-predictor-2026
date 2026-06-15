# Deployment Guide — WorldCup Predictor Pro (Phase 49)

Analytical football prediction GUI. **Not betting advice.**

## Requirements

- Python 3.11+
- Dependencies: `pip install -r requirements.txt`
- API keys in environment (never in Git)

## Local development

```bash
pip install -r requirements.txt
cp .env.example .env   # if present
# PUBLIC_ACCESS_ENABLED=false  (default) — no paywall locally
python main.py gui
```

## Environment variables

| Variable | Purpose |
|----------|---------|
| `API_FOOTBALL_KEY` | Primary match data (server-side only) |
| `OPENAI_API_KEY` | Optional reasoning |
| `PUBLIC_ACCESS_ENABLED` | `true` enables login, limits, paywall |
| `PUBLIC_ACCESS_CODE` | Shared invite code required for user login |
| `FREE_DAILY_PREDICTION_LIMIT` | Default `2` for unpaid users |
| `PAID_UNLOCK_PRICE_EUR` | Display price (default `5`) |
| `ADMIN_USERNAME` | Developer Mode admin login |
| `ADMIN_PASSWORD` | Developer Mode admin password |
| `STRIPE_PAYMENT_LINK` | Easiest: Stripe Payment Link URL |
| `STRIPE_SECRET_KEY` | Or Checkout API |
| `STRIPE_PRICE_ID` | Price ID for Checkout |
| `STRIPE_WEBHOOK_SECRET` | Optional webhook verification |
| `APP_AUTH_ENABLED` | Optional site-wide password (legacy) |

See `.streamlit/secrets.example.toml` for Streamlit Cloud format.

## Streamlit Cloud

1. Push repo to GitHub.
2. [share.streamlit.io](https://share.streamlit.io) → New app.
3. Main file: `worldcup_predictor/ui/gui_app.py`  
   Or entry: `python main.py gui` via `packages.txt` + custom command if needed.
4. **Recommended:** set `Main file path` to `worldcup_predictor/ui/gui_app.py`.
5. Add secrets from `.streamlit/secrets.example.toml` in app Settings → Secrets.
6. Set `PUBLIC_ACCESS_ENABLED=true` for production paywall.
7. Set `APP_PUBLIC_URL` to your Streamlit app URL.

## Hugging Face Spaces

1. Create a **Streamlit** Space.
2. Upload `requirements.txt` and project files (or connect Git).
3. `app.py` at repo root can delegate:

```python
from worldcup_predictor.ui.gui_app import main
main()
```

4. Add Space **Secrets** (same keys as Streamlit Cloud).
5. Ensure `data/` is writable (Space persistent storage or mount).

## Docker (existing)

```bash
docker compose up --build
```

Uses `.env.production` — add Phase 49 variables there.

## Stripe setup

### Option A — Payment Link (MVP)

1. Stripe Dashboard → Payment Links → create €5 one-time product.
2. Set `STRIPE_PAYMENT_LINK=https://buy.stripe.com/...`
3. Users return manually or via `?payment=success` after you enable success URL on the link.

### Option B — Checkout Sessions

1. Create Product + Price in Stripe.
2. Set `STRIPE_SECRET_KEY` and `STRIPE_PRICE_ID`.
3. App creates session via REST; success URL: `{APP_PUBLIC_URL}/?payment=success&session_id={CHECKOUT_SESSION_ID}`.

### Manual unlock (MVP)

- User enters payment reference on **Upgrade** page, or
- Developer Mode → **Admin Entitlements** → mark user paid.

## Security notes

- API keys stay in env/secrets — never exposed in UI or client.
- Prediction gate runs **before** API-Football and pipeline calls.
- User login uses a shared invite code (`PUBLIC_ACCESS_CODE`) — not per-user tokens.

## Validation

```bash
python scripts/validate_phase49.py
python main.py gui
```

With `PUBLIC_ACCESS_ENABLED=true`, test: 2 free predictions, 3rd blocked, upgrade page, admin mark paid.
