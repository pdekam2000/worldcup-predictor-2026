"""Stripe Checkout / Payment Link helpers — optional, env-driven."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from worldcup_predictor.access.config import (
    app_public_url,
    stripe_configured,
    stripe_payment_link,
    stripe_price_id,
    stripe_secret_key,
)


@dataclass
class CheckoutResult:
    ok: bool
    checkout_url: str | None = None
    session_id: str | None = None
    error: str | None = None


def create_checkout_session(*, user_id: str, email: str | None = None) -> CheckoutResult:
    """Create Stripe Checkout session or return payment link — never raises."""
    link = stripe_payment_link()
    if link:
        sep = "&" if "?" in link else "?"
        return CheckoutResult(
            ok=True,
            checkout_url=f"{link}{sep}client_reference_id={user_id}",
        )

    secret = stripe_secret_key()
    price = stripe_price_id()
    if not secret or not price:
        return CheckoutResult(ok=False, error="Stripe not configured")

    payload: dict[str, Any] = {
        "mode": "payment",
        "success_url": f"{app_public_url()}/?payment=success&session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{app_public_url()}/?payment=canceled",
        "client_reference_id": user_id,
        "line_items[0][price]": price,
        "line_items[0][quantity]": 1,
    }
    if email:
        payload["customer_email"] = email

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                "https://api.stripe.com/v1/checkout/sessions",
                data=payload,
                auth=(secret, ""),
            )
        if resp.status_code >= 400:
            return CheckoutResult(ok=False, error=f"Stripe HTTP {resp.status_code}")
        data = resp.json()
        return CheckoutResult(
            ok=True,
            checkout_url=data.get("url"),
            session_id=data.get("id"),
        )
    except Exception as exc:
        return CheckoutResult(ok=False, error=str(exc))


def verify_checkout_session(session_id: str) -> tuple[bool, str | None]:
    """Verify paid checkout session — returns (paid, payment_reference)."""
    secret = stripe_secret_key()
    if not secret or not session_id.strip():
        return False, None
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(
                f"https://api.stripe.com/v1/checkout/sessions/{session_id.strip()}",
                auth=(secret, ""),
            )
        if resp.status_code >= 400:
            return False, None
        data = resp.json()
        paid = data.get("payment_status") == "paid" or data.get("status") == "complete"
        ref = data.get("payment_intent") or data.get("id")
        return bool(paid), str(ref) if ref else session_id
    except Exception:
        return False, None


def stripe_ready() -> bool:
    return stripe_configured()
