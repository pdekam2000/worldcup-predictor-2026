#!/usr/bin/env python3
"""Phase 44E — ensure Stripe webhook endpoint exists for billing sync."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ENV_PATH = Path("/opt/worldcup-predictor/.env.production")
if not ENV_PATH.is_file():
    ENV_PATH = Path(__file__).resolve().parents[1] / ".env.production"

WEBHOOK_PATH = "/api/billing/webhook"
EVENTS = [
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_succeeded",
    "invoice.payment_failed",
]


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


def _update_env_var(name: str, value: str) -> None:
    text = _read_env_text()
    line = f'{name}="{value}"'
    if re.search(rf"^{re.escape(name)}=", text, re.MULTILINE):
        text = re.sub(rf"^{re.escape(name)}=.*$", line, text, count=1, flags=re.MULTILINE)
    else:
        text = text.rstrip() + "\n" + line + "\n"
    ENV_PATH.write_text(text, encoding="utf-8")


def _webhook_url(env: dict[str, str]) -> str:
    base = (env.get("APP_PUBLIC_URL") or "").strip().rstrip("/")
    if not base:
        success = (env.get("STRIPE_SUCCESS_URL") or "").strip()
        if success:
            from urllib.parse import urlparse, urlunparse

            p = urlparse(success)
            base = urlunparse((p.scheme, p.netloc, "", "", "", ""))
    return f"{base}{WEBHOOK_PATH}" if base else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    env = _read_env()
    secret = env.get("STRIPE_SECRET_KEY", "").strip()
    if not secret.startswith(("sk_test_", "sk_live_")):
        print("STRIPE_SECRET_KEY: invalid_or_missing")
        return 1

    url = _webhook_url(env)
    if not url.startswith("https://"):
        print("webhook_url: invalid_or_missing")
        return 1
    print(f"target_webhook_url: {url}")

    sys.path.insert(0, str(ENV_PATH.parent))
    import stripe

    stripe.api_key = secret

    existing = None
    for ep in stripe.WebhookEndpoint.list(limit=20).auto_paging_iter():
        if str(ep.url or "").rstrip("/") == url.rstrip("/"):
            existing = ep
            break

    if existing:
        print(f"webhook_exists: True")
        print(f"webhook_id: {str(existing.id)[:12]}…")
        events = list(getattr(existing, "enabled_events", []) or [])
        missing = [e for e in EVENTS if e not in events]
        if missing:
            print(f"missing_events: {','.join(missing)}")
        else:
            print("events_complete: True")
        return 0

    print("webhook_exists: False")
    if not args.apply:
        print("dry_run: run with --apply to create webhook endpoint")
        return 1

    endpoint = stripe.WebhookEndpoint.create(url=url, enabled_events=EVENTS)
    signing_secret = str(getattr(endpoint, "secret", "") or "")
    if not signing_secret.startswith("whsec_"):
        print("webhook_created: True")
        print("signing_secret: not_returned — update STRIPE_WEBHOOK_SECRET manually in Stripe dashboard")
        return 1

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = ENV_PATH.with_name(f"env.production.bak-webhook-{ts}")
    backup.write_text(_read_env_text(), encoding="utf-8")
    print(f"env_backup: {backup}")
    _update_env_var("STRIPE_WEBHOOK_SECRET", signing_secret)
    print("updated STRIPE_WEBHOOK_SECRET=whsec_***")
    print(f"webhook_id: {str(endpoint.id)[:12]}…")
    print("WEBHOOK_PROVISION_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
