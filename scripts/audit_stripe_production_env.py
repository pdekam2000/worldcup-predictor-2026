"""Read-only production Stripe configuration audit — no secrets printed."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ENV_PATH = Path("/opt/worldcup-predictor/.env.production")
STRIPE_VARS = (
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "STRIPE_STARTER_PRICE_ID",
    "STRIPE_PRO_PRICE_ID",
    "STRIPE_SUCCESS_URL",
    "STRIPE_CANCEL_URL",
    "STRIPE_PORTAL_RETURN_URL",
    "STRIPE_MODE",
    "APP_PUBLIC_URL",
)


def _var_presence(name: str) -> tuple[bool, bool]:
    if not ENV_PATH.is_file():
        return False, False
    text = ENV_PATH.read_text(encoding="utf-8", errors="replace")
    if not re.search(rf"^{re.escape(name)}=", text, re.MULTILINE):
        return False, False
    for line in text.splitlines():
        if line.startswith(f"{name}="):
            val = line.split("=", 1)[1].strip().strip('"').strip("'")
            return True, bool(val)
    return True, False


def main() -> int:
    print("=== PRODUCTION STRIPE ENV AUDIT (yes/no only) ===")
    print(f"env_file_exists: {ENV_PATH.is_file()}")
    all_required = True
    for var in STRIPE_VARS:
        in_file, non_empty = _var_presence(var)
        print(f"{var}_present: {in_file and non_empty}")
        if var in (
            "STRIPE_SECRET_KEY",
            "STRIPE_WEBHOOK_SECRET",
            "STRIPE_STARTER_PRICE_ID",
            "STRIPE_PRO_PRICE_ID",
            "STRIPE_SUCCESS_URL",
            "STRIPE_CANCEL_URL",
            "STRIPE_MODE",
        ) and not (in_file and non_empty):
            all_required = False

    sys.path.insert(0, "/opt/worldcup-predictor")
    try:
        from worldcup_predictor.billing.billing_service import BillingService
        from worldcup_predictor.config.settings import Settings

        s = Settings(_env_file=str(ENV_PATH) if ENV_PATH.is_file() else None)
        svc = BillingService(settings=s)
        ready = svc.readiness()
        print(f"stripe_billing_configured: {s.stripe_billing_configured}")
        print(f"checkout_enabled: {ready.checkout_enabled}")
        print(f"portal_enabled: {ready.portal_enabled}")
        print(f"webhook_secret_configured: {ready.webhook_secret_configured}")
        print(f"stripe_mode: {ready.stripe_mode}")
    except Exception as exc:
        print(f"runtime_readiness_error: {type(exc).__name__}")
        all_required = False

    print(f"stripe_production_ready: {all_required}")
    return 0 if all_required else 1


if __name__ == "__main__":
    raise SystemExit(main())
