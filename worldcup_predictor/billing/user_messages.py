"""User-facing billing messages — no secrets."""

from __future__ import annotations

CHECKOUT_INACTIVE_MSG = "Payment checkout is not active yet."
PLAN_UNAVAILABLE_MSG = "This plan is not available yet."
CHECKOUT_FAILED_MSG = "Could not start checkout. Please try again or contact support."
ALREADY_ON_PLAN_MSG = "You already have an active subscription for this plan."
INVALID_UPGRADE_MSG = "Cannot checkout for the same or lower plan tier."
RATE_LIMIT_MSG = "Too many checkout attempts. Please try again later."

_CODE_MESSAGES: dict[str, str] = {
    "checkout_disabled": CHECKOUT_INACTIVE_MSG,
    "stripe_not_configured": CHECKOUT_INACTIVE_MSG,
    "price_not_configured": PLAN_UNAVAILABLE_MSG,
    "stripe_price_invalid": PLAN_UNAVAILABLE_MSG,
    "unknown_plan": PLAN_UNAVAILABLE_MSG,
    "stripe_checkout_failed": CHECKOUT_FAILED_MSG,
    "stripe_customer_failed": CHECKOUT_FAILED_MSG,
    "duplicate_active_plan": ALREADY_ON_PLAN_MSG,
    "invalid_upgrade": INVALID_UPGRADE_MSG,
    "checkout_rate_limited": RATE_LIMIT_MSG,
    "email_verification_required": "Email verification required before checkout.",
    "account_blocked": "Account is not allowed.",
}


def message_for_code(code: str | None, fallback: str | None = None) -> str:
    if fallback and str(fallback).strip():
        mapped = _CODE_MESSAGES.get(code or "")
        if mapped and fallback.strip() != mapped:
            return str(fallback).strip()
    if code and code in _CODE_MESSAGES:
        return _CODE_MESSAGES[code]
    return fallback or CHECKOUT_FAILED_MSG
