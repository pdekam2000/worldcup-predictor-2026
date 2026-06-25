#!/usr/bin/env python3
"""Phase 44E — provision real Stripe recurring prices (test or live account).

Creates Football Predictor Starter (€5/mo) and Pro (€19/mo) if missing.
Updates .env.production price IDs when --apply is passed.
Never prints secret values.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ENV_PATH = Path("/opt/worldcup-predictor/.env.production")
if not ENV_PATH.is_file():
    ENV_PATH = Path(__file__).resolve().parents[1] / ".env.production"

PLANS = (
    ("starter", "Football Predictor Starter", 500, "STRIPE_STARTER_PRICE_ID"),
    ("pro", "Football Predictor Pro", 1900, "STRIPE_PRO_PRICE_ID"),
)
CURRENCY = "eur"


def _read_env_text() -> str:
    return ENV_PATH.read_text(encoding="utf-8", errors="replace") if ENV_PATH.is_file() else ""


def _read_env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in _read_env_text().splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _mask(pid: str) -> str:
    pid = str(pid or "").strip()
    return f"{pid[:8]}…{pid[-4:]}" if len(pid) > 12 else "price_***"


def _find_matching_price(stripe, *, amount_cents: int) -> str | None:
    for p in stripe.Price.list(active=True, limit=100).auto_paging_iter():
        if not getattr(p, "recurring", None):
            continue
        if str(getattr(p, "currency", "") or "").lower() != CURRENCY:
            continue
        if int(getattr(p, "unit_amount", 0) or 0) != amount_cents:
            continue
        if not getattr(p, "active", False):
            continue
        return str(p.id)
    return None


def _create_price(stripe, *, name: str, amount_cents: int) -> str:
    product = stripe.Product.create(name=name, metadata={"platform": "football_predictor"})
    price = stripe.Price.create(
        product=product.id,
        unit_amount=amount_cents,
        currency=CURRENCY,
        recurring={"interval": "month"},
        metadata={"platform": "football_predictor"},
    )
    return str(price.id)


def _update_env_var(name: str, value: str) -> None:
    text = _read_env_text()
    line = f'{name}="{value}"'
    if re.search(rf"^{re.escape(name)}=", text, re.MULTILINE):
        text = re.sub(rf"^{re.escape(name)}=.*$", line, text, count=1, flags=re.MULTILINE)
    else:
        text = text.rstrip() + "\n" + line + "\n"
    ENV_PATH.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Create prices and update .env.production")
    args = parser.parse_args()

    env = _read_env()
    secret = env.get("STRIPE_SECRET_KEY", "").strip()
    if not secret.startswith(("sk_test_", "sk_live_")):
        print("STRIPE_SECRET_KEY: invalid_or_missing")
        return 1

    sys.path.insert(0, str(ENV_PATH.parent if ENV_PATH.parent.name == "worldcup-predictor" else Path("/opt/worldcup-predictor")))
    import stripe

    stripe.api_key = secret
    mode = "live" if secret.startswith("sk_live_") else "test"
    print(f"stripe_account_mode: {mode}")

    resolved: dict[str, str] = {}
    for plan_key, product_name, amount, env_var in PLANS:
        current = env.get(env_var, "").strip()
        price_id: str | None = None
        if current:
            try:
                p = stripe.Price.retrieve(current)
                ok = (
                    bool(getattr(p, "active", False))
                    and getattr(p, "recurring", None) is not None
                    and str(getattr(p, "currency", "") or "").lower() == CURRENCY
                    and int(getattr(p, "unit_amount", 0) or 0) == amount
                )
                if ok:
                    price_id = current
                    print(f"{plan_key}: existing_valid price_id={_mask(current)}")
            except Exception:
                print(f"{plan_key}: configured_price_invalid price_id={_mask(current)}")

        if not price_id:
            price_id = _find_matching_price(stripe, amount_cents=amount)
            if price_id:
                print(f"{plan_key}: found_existing price_id={_mask(price_id)} amount={amount}")

        if not price_id:
            if not args.apply:
                print(f"{plan_key}: needs_creation amount_cents={amount}")
                continue
            price_id = _create_price(stripe, name=product_name, amount_cents=amount)
            print(f"{plan_key}: created price_id={_mask(price_id)} amount={amount}")

        resolved[env_var] = price_id

    if not args.apply:
        if len(resolved) < len(PLANS):
            print("dry_run: run with --apply to create missing prices and update env")
            return 1
        print("dry_run: all prices valid, no env update needed")
        return 0

    if len(resolved) < len(PLANS):
        print("provision_incomplete: could not resolve all prices")
        return 1

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = ENV_PATH.with_name(f"env.production.bak-phase44e-{ts}")
    backup.write_text(_read_env_text(), encoding="utf-8")
    print(f"env_backup: {backup}")

    for env_var, price_id in resolved.items():
        _update_env_var(env_var, price_id)
        print(f"updated {env_var}={_mask(price_id)}")

    print("PROVISION_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
