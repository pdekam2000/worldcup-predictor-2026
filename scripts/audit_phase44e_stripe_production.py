#!/usr/bin/env python3
"""Phase 44E-A/B — production Stripe audit (no secrets printed)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ENV_PATH = Path("/opt/worldcup-predictor/.env.production")
if not ENV_PATH.is_file():
    ENV_PATH = Path(__file__).resolve().parents[1] / ".env.production"

REQUIRED = (
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "STRIPE_STARTER_PRICE_ID",
    "STRIPE_PRO_PRICE_ID",
    "STRIPE_SUCCESS_URL",
    "STRIPE_CANCEL_URL",
    "STRIPE_MODE",
)
OPTIONAL = ("STRIPE_PUBLISHABLE_KEY", "STRIPE_PORTAL_RETURN_URL", "APP_PUBLIC_URL")

STARTER_AMOUNT_CENTS = 500
PRO_AMOUNT_CENTS = 1900
EXPECTED_CURRENCY = "eur"


def _read_env() -> dict[str, str]:
    if not ENV_PATH.is_file():
        return {}
    out: dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _mask_price_id(pid: str) -> str:
    pid = str(pid or "").strip()
    if len(pid) <= 8:
        return "price_***"
    return f"{pid[:8]}…{pid[-4:]}"


def _classify_secret_key(val: str) -> str:
    v = (val or "").strip()
    if not v:
        return "missing"
    if v.startswith("sk_live_"):
        return "present_live"
    if v.startswith("sk_test_"):
        return "present_test"
    return "invalid"


def _classify_price_id(val: str) -> str:
    v = (val or "").strip()
    if not v:
        return "missing"
    if not v.startswith("price_"):
        return "invalid_format"
    return "present"


def _classify_url(val: str) -> str:
    v = (val or "").strip()
    if not v:
        return "missing"
    if v.startswith("http://") or v.startswith("https://"):
        return "present"
    return "invalid"


def _audit_price(stripe, price_id: str, *, plan: str, expected_cents: int) -> dict:
    result = {
        "plan": plan,
        "price_id_masked": _mask_price_id(price_id),
        "env_status": _classify_price_id(price_id),
        "reachable": False,
        "active": False,
        "recurring": False,
        "currency_ok": False,
        "amount_ok": False,
        "issues": [],
    }
    if result["env_status"] != "present":
        result["issues"].append(f"env_{result['env_status']}")
        return result
    try:
        price = stripe.Price.retrieve(price_id)
        result["reachable"] = True
        result["active"] = bool(getattr(price, "active", False))
        recurring = getattr(price, "recurring", None)
        result["recurring"] = recurring is not None
        currency = str(getattr(price, "currency", "") or "").lower()
        unit_amount = int(getattr(price, "unit_amount", 0) or 0)
        result["currency_ok"] = currency == EXPECTED_CURRENCY
        result["amount_ok"] = unit_amount == expected_cents
        if not result["active"]:
            result["issues"].append("not_active")
        if not result["recurring"]:
            result["issues"].append("not_recurring")
        if not result["currency_ok"]:
            result["issues"].append(f"currency_{currency or 'missing'}")
        if not result["amount_ok"]:
            result["issues"].append(f"amount_{unit_amount}_expected_{expected_cents}")
    except Exception as exc:
        msg = str(getattr(exc, "user_message", None) or exc)
        if "No such price" in msg:
            result["issues"].append("no_such_price")
        else:
            result["issues"].append(f"retrieve_{type(exc).__name__}")
    return result


def _list_account_prices(stripe) -> list[dict]:
    """List recurring EUR prices in account — masked IDs only."""
    found: list[dict] = []
    try:
        prices = stripe.Price.list(active=True, limit=20, expand=["data.product"])
        for p in prices.auto_paging_iter():
            if not getattr(p, "recurring", None):
                continue
            currency = str(getattr(p, "currency", "") or "").lower()
            if currency != EXPECTED_CURRENCY:
                continue
            product = getattr(p, "product", None)
            product_name = ""
            if product is not None:
                product_name = str(getattr(product, "name", "") or "")
            found.append({
                "price_id_masked": _mask_price_id(str(p.id)),
                "unit_amount_cents": int(getattr(p, "unit_amount", 0) or 0),
                "interval": str(getattr(getattr(p, "recurring", None), "interval", "") or ""),
                "product_name": product_name[:60] or "(unnamed)",
                "active": bool(getattr(p, "active", False)),
            })
            if len(found) >= 10:
                break
    except Exception as exc:
        found.append({"error": type(exc).__name__})
    return found


def main() -> int:
    env = _read_env()
    report: dict = {"env_file": str(ENV_PATH), "env_exists": ENV_PATH.is_file(), "vars": {}, "prices": {}, "runtime": {}}

    for var in REQUIRED + OPTIONAL:
        val = env.get(var, "")
        if var == "STRIPE_SECRET_KEY":
            status = _classify_secret_key(val)
        elif var.endswith("_PRICE_ID"):
            status = _classify_price_id(val)
        elif "URL" in var:
            status = _classify_url(val)
        elif var == "STRIPE_MODE":
            status = "present" if val.lower() in ("test", "live") else ("missing" if not val else "invalid")
        elif var == "STRIPE_WEBHOOK_SECRET":
            status = "present" if val.startswith("whsec_") else ("missing" if not val else "invalid")
        elif var == "STRIPE_PUBLISHABLE_KEY":
            if not val:
                status = "missing"
            elif val.startswith("pk_live_") or val.startswith("pk_test_"):
                status = "present"
            else:
                status = "invalid"
        else:
            status = "present" if val else "missing"
        report["vars"][var] = status

    sys.path.insert(0, str(ENV_PATH.parent if ENV_PATH.parent.name == "worldcup-predictor" else Path("/opt/worldcup-predictor")))
    root = Path("/opt/worldcup-predictor")
    if not root.is_dir():
        root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))

    try:
        import stripe
        from worldcup_predictor.billing.billing_service import BillingService
        from worldcup_predictor.config.settings import Settings

        s = Settings(_env_file=str(ENV_PATH) if ENV_PATH.is_file() else None)
        if s.stripe_secret_key.strip():
            stripe.api_key = s.stripe_secret_key.strip()

        svc = BillingService(settings=s)
        ready = svc.readiness()
        report["runtime"] = {
            "checkout_enabled": ready.checkout_enabled,
            "portal_enabled": ready.portal_enabled,
            "stripe_mode": ready.stripe_mode,
            "message": ready.message,
            "webhook_secret_configured": ready.webhook_secret_configured,
        }

        if s.stripe_secret_key.strip():
            report["prices"]["starter"] = _audit_price(
                stripe, s.stripe_starter_price_id, plan="starter", expected_cents=STARTER_AMOUNT_CENTS
            )
            report["prices"]["pro"] = _audit_price(
                stripe, s.stripe_pro_price_id, plan="pro", expected_cents=PRO_AMOUNT_CENTS
            )
            report["account_recurring_eur_prices"] = _list_account_prices(stripe)
    except Exception as exc:
        report["runtime"]["error"] = type(exc).__name__

    # Human-readable output (no secrets)
    print("=== PHASE 44E STRIPE PRODUCTION AUDIT ===")
    print(f"env_file_exists: {report['env_exists']}")
    for var in REQUIRED + OPTIONAL:
        print(f"{var}: {report['vars'].get(var, 'missing')}")
    rt = report.get("runtime", {})
    print(f"checkout_enabled: {rt.get('checkout_enabled')}")
    print(f"portal_enabled: {rt.get('portal_enabled')}")
    print(f"stripe_mode: {rt.get('stripe_mode')}")
    if rt.get("message"):
        print(f"readiness_message: {rt['message']}")
    for plan in ("starter", "pro"):
        p = report.get("prices", {}).get(plan)
        if not p:
            continue
        print(f"\n--- {plan.upper()} price ---")
        print(f"  env_status: {p['env_status']}")
        print(f"  price_id_masked: {p['price_id_masked']}")
        print(f"  reachable: {p['reachable']}")
        print(f"  active: {p['active']}")
        print(f"  recurring: {p['recurring']}")
        print(f"  currency_ok: {p['currency_ok']}")
        print(f"  amount_ok: {p['amount_ok']}")
        if p["issues"]:
            print(f"  issues: {', '.join(p['issues'])}")
    acct = report.get("account_recurring_eur_prices") or []
    if acct:
        print("\n--- account recurring EUR prices (masked) ---")
        for row in acct:
            if "error" in row:
                print(f"  list_error: {row['error']}")
            else:
                print(
                    f"  {row['price_id_masked']} amount={row['unit_amount_cents']} "
                    f"interval={row['interval']} product={row['product_name']}"
                )

    out = root / "artifacts" / "phase44e_stripe_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nartifact: {out}")

    ok = (
        report["vars"].get("STRIPE_SECRET_KEY", "").startswith("present")
        and report["vars"].get("STRIPE_STARTER_PRICE_ID") == "present"
        and report["vars"].get("STRIPE_PRO_PRICE_ID") == "present"
        and rt.get("checkout_enabled") is True
    )
    print(f"stripe_fully_operational: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
