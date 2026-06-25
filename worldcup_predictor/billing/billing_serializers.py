"""Phase 39B-4 — billing API serializers (no secrets)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from worldcup_predictor.database.postgres.repositories.billing_invoices import BillingInvoiceListItem
from worldcup_predictor.database.postgres.repositories.subscriptions import SubscriptionBillingDetail


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def mask_stripe_id(value: str | None) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    if len(raw) <= 8:
        return "***"
    return f"{raw[:4]}***{raw[-4:]}"


def billing_status_to_dict(detail: SubscriptionBillingDetail) -> dict[str, Any]:
    billing_status = (detail.billing_status or "").strip().lower()
    checkout_pending = billing_status in (
        "checkout_pending",
        "checkout_completed",
        "incomplete",
    ) and detail.plan.value == "free"
    return {
        "status": "ok",
        "plan": detail.plan.value,
        "subscription_status": detail.status.value,
        "billing_status": detail.billing_status,
        "current_period_start": _iso(detail.current_period_start),
        "current_period_end": _iso(detail.current_period_end),
        "cancel_at_period_end": detail.cancel_at_period_end,
        "last_payment_status": detail.last_payment_status,
        "last_payment_at": _iso(detail.last_payment_at),
        "provider": detail.provider,
        "checkout_pending": checkout_pending,
    }


def admin_billing_to_dict(
    detail: SubscriptionBillingDetail,
    *,
    invoice_count: int,
) -> dict[str, Any]:
    base = billing_status_to_dict(detail)
    base["stripe_customer_id_masked"] = mask_stripe_id(detail.external_customer_id)
    base["invoice_count"] = invoice_count
    return base


def invoice_to_dict(item: BillingInvoiceListItem) -> dict[str, Any]:
    amount = item.amount_paid if item.amount_paid is not None else item.amount_due
    return {
        "date": _iso(item.paid_at or item.created_at),
        "amount_paid": float(amount) if amount is not None else None,
        "currency": (item.currency or "EUR").upper(),
        "status": item.status,
        "period_start": _iso(item.period_start),
        "period_end": _iso(item.period_end),
        "hosted_invoice_url": item.hosted_invoice_url,
    }


def format_invoice_for_legacy_table(item: BillingInvoiceListItem) -> dict[str, str]:
    amount = item.amount_paid if item.amount_paid is not None else item.amount_due
    currency = (item.currency or "EUR").upper()
    amount_str = f"€{float(amount):.2f}" if amount is not None else "—"
    date_str = "—"
    if item.paid_at or item.created_at:
        dt = item.paid_at or item.created_at
        date_str = dt.strftime("%b %d, %Y") if dt else "—"
    return {
        "date": date_str,
        "desc": f"{currency} subscription",
        "amount": amount_str,
        "status": item.status or "—",
        "hosted_invoice_url": item.hosted_invoice_url or "",
    }
