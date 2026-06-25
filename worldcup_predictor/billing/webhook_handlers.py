"""Phase 39B-3 — Stripe webhook event handlers."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from worldcup_predictor.billing.billing_audit import write_billing_audit_event
from worldcup_predictor.billing.plan_mapping import plan_monthly_amount, price_id_to_plan
from worldcup_predictor.config.settings import Settings
from worldcup_predictor.database.postgres.enums import SubscriptionPlan, SubscriptionStatus
from worldcup_predictor.database.postgres.uow import SaasUnitOfWork

logger = logging.getLogger(__name__)

_ACTIVE_STRIPE_STATUSES = frozenset({"active", "trialing"})
_GRACE_STRIPE_STATUSES = frozenset({"active", "trialing", "past_due"})
_DOWNGRADE_STRIPE_STATUSES = frozenset({"unpaid", "incomplete_expired"})
_CANCELLED_STRIPE_STATUSES = frozenset({"canceled"})


class WebhookProcessingError(Exception):
    def __init__(self, message: str, *, code: str = "webhook_processing_error", recoverable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.recoverable = recoverable


def _stripe_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _cents_to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(int(value))) / Decimal("100")
    except (TypeError, ValueError):
        return None


def _obj_get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _subscription_price_id(sub_obj: Any) -> str | None:
    items = _obj_get(sub_obj, "items")
    data = _obj_get(items, "data") if items is not None else None
    if not data:
        return None
    first = data[0] if isinstance(data, list) and data else None
    if first is None:
        return None
    price = _obj_get(first, "price")
    if price is None:
        return _obj_get(first, "plan", {}).get("id") if isinstance(_obj_get(first, "plan"), dict) else None
    return str(_obj_get(price, "id") or "")


def _resolve_user_id_from_subscription(
    uow: SaasUnitOfWork,
    sub_obj: Any,
) -> uuid.UUID | None:
    sub_id = str(_obj_get(sub_obj, "id") or "").strip()
    customer_id = str(_obj_get(sub_obj, "customer") or "").strip()
    metadata = _obj_get(sub_obj, "metadata") or {}
    user_meta = str(metadata.get("user_id") or "").strip()

    if user_meta:
        try:
            return uuid.UUID(user_meta)
        except ValueError:
            pass

    if sub_id:
        record = uow.subscriptions.get_by_external_subscription_id(sub_id)
        if record is not None:
            return record.user_id

    if customer_id:
        record = uow.subscriptions.get_by_external_customer_id(customer_id)
        if record is not None:
            return record.user_id

    return None


def _should_activate_plan(stripe_status: str) -> bool:
    return stripe_status in _ACTIVE_STRIPE_STATUSES


def _should_preserve_paid_access(stripe_status: str, current_plan: SubscriptionPlan) -> bool:
    if current_plan in (SubscriptionPlan.STARTER, SubscriptionPlan.PRO):
        return stripe_status in _GRACE_STRIPE_STATUSES
    return False


def _apply_subscription_state(
    uow: SaasUnitOfWork,
    user_id: uuid.UUID,
    sub_obj: Any,
    settings: Settings,
    *,
    audit_event: str,
) -> None:
    stripe_status = str(_obj_get(sub_obj, "status") or "").strip().lower()
    customer_id = str(_obj_get(sub_obj, "customer") or "").strip() or None
    sub_id = str(_obj_get(sub_obj, "id") or "").strip() or None
    price_id = _subscription_price_id(sub_obj)
    plan = price_id_to_plan(price_id, settings)
    period_start = _stripe_ts(_obj_get(sub_obj, "current_period_start"))
    period_end = _stripe_ts(_obj_get(sub_obj, "current_period_end"))
    cancel_at_period_end = bool(_obj_get(sub_obj, "cancel_at_period_end", False))

    existing = uow.subscriptions.get_for_user(user_id)
    current_plan = existing.plan if existing else SubscriptionPlan.FREE

    if plan is None and price_id:
        write_billing_audit_event(
            "stripe_webhook_processing_error",
            user_id=str(user_id),
            detail=f"unknown_price_id;status={stripe_status}",
        )
        uow.subscriptions.sync_from_stripe(
            user_id,
            external_customer_id=customer_id,
            external_subscription_id=sub_id,
            external_price_id=price_id,
            billing_status=stripe_status or "unknown_price",
        )
        return

    sync_kwargs: dict[str, Any] = {
        "external_customer_id": customer_id,
        "external_subscription_id": sub_id,
        "external_price_id": price_id,
        "billing_status": stripe_status,
        "current_period_start": period_start,
        "current_period_end": period_end,
        "cancel_at_period_end": cancel_at_period_end,
    }

    if _should_activate_plan(stripe_status) and plan is not None:
        amount = plan_monthly_amount(plan)
        uow.subscriptions.sync_from_stripe(
            user_id,
            plan=plan,
            status=SubscriptionStatus.ACTIVE,
            amount=Decimal(str(amount)) if amount is not None else None,
            start_date=period_start,
            end_date=period_end,
            **sync_kwargs,
        )
        write_billing_audit_event(
            audit_event,
            user_id=str(user_id),
            detail=f"plan={plan.value};status={stripe_status}",
        )
        return

    if stripe_status == "past_due":
        if _should_preserve_paid_access(stripe_status, current_plan):
            uow.subscriptions.sync_from_stripe(
                user_id,
                billing_status="past_due",
                **sync_kwargs,
            )
        else:
            uow.subscriptions.sync_from_stripe(
                user_id,
                billing_status="past_due",
                **sync_kwargs,
            )
        write_billing_audit_event(
            "stripe_subscription_updated",
            user_id=str(user_id),
            detail=f"past_due;plan={current_plan.value}",
        )
        return

    if stripe_status in _CANCELLED_STRIPE_STATUSES:
        if cancel_at_period_end and period_end and period_end > datetime.now(timezone.utc):
            if plan is not None:
                uow.subscriptions.sync_from_stripe(
                    user_id,
                    plan=plan,
                    status=SubscriptionStatus.ACTIVE,
                    start_date=period_start,
                    end_date=period_end,
                    billing_status="cancel_at_period_end",
                    **sync_kwargs,
                )
            else:
                uow.subscriptions.sync_from_stripe(
                    user_id,
                    billing_status="cancel_at_period_end",
                    **sync_kwargs,
                )
            write_billing_audit_event(
                "stripe_subscription_updated",
                user_id=str(user_id),
                detail="cancel_at_period_end",
            )
            return

        uow.subscriptions.downgrade_to_free(user_id, billing_status="canceled", clear_subscription_id=False)
        uow.subscriptions.sync_from_stripe(
            user_id,
            external_customer_id=customer_id,
            billing_status="canceled",
            current_period_start=period_start,
            current_period_end=period_end,
            cancel_at_period_end=False,
        )
        write_billing_audit_event(
            "stripe_subscription_canceled",
            user_id=str(user_id),
            detail=f"status={stripe_status}",
        )
        return

    if stripe_status in _DOWNGRADE_STRIPE_STATUSES or stripe_status == "incomplete":
        if stripe_status == "incomplete":
            uow.subscriptions.sync_from_stripe(
                user_id,
                billing_status="incomplete",
                **sync_kwargs,
            )
            write_billing_audit_event(
                "stripe_subscription_updated",
                user_id=str(user_id),
                detail="incomplete_no_activation",
            )
            return

        uow.subscriptions.downgrade_to_free(user_id, billing_status=stripe_status)
        if customer_id:
            uow.subscriptions.sync_from_stripe(user_id, external_customer_id=customer_id)
        write_billing_audit_event(
            "stripe_subscription_canceled",
            user_id=str(user_id),
            detail=f"status={stripe_status}",
        )
        return

    if plan is not None:
        uow.subscriptions.sync_from_stripe(user_id, plan=plan, **sync_kwargs)
    else:
        uow.subscriptions.sync_from_stripe(user_id, **sync_kwargs)
    write_billing_audit_event(
        "stripe_subscription_updated",
        user_id=str(user_id),
        detail=f"status={stripe_status}",
    )


def handle_checkout_session_completed(
    uow: SaasUnitOfWork,
    session_obj: Any,
    settings: Settings,
) -> None:
    mode = str(_obj_get(session_obj, "mode") or "").strip().lower()
    if mode != "subscription":
        write_billing_audit_event(
            "stripe_webhook_processing_error",
            detail=f"checkout_mode={mode}",
        )
        return

    metadata = _obj_get(session_obj, "metadata") or {}
    user_id_raw = str(metadata.get("user_id") or "").strip()
    if not user_id_raw:
        write_billing_audit_event(
            "stripe_webhook_processing_error",
            detail="checkout_missing_user_metadata",
        )
        return

    try:
        user_id = uuid.UUID(user_id_raw)
    except ValueError:
        write_billing_audit_event(
            "stripe_webhook_processing_error",
            detail="checkout_invalid_user_metadata",
        )
        return

    payment_status = str(_obj_get(session_obj, "payment_status") or "").strip().lower()
    customer_id = str(_obj_get(session_obj, "customer") or "").strip() or None
    subscription_id = str(_obj_get(session_obj, "subscription") or "").strip() or None

    allowed_payment = payment_status in ("paid", "no_payment_required")
    if not allowed_payment and not subscription_id:
        uow.subscriptions.sync_from_stripe(
            user_id,
            external_customer_id=customer_id,
            billing_status=f"checkout_{payment_status or 'pending'}",
        )
        write_billing_audit_event(
            "stripe_subscription_updated",
            user_id=str(user_id),
            detail=f"checkout_pending_payment;status={payment_status}",
        )
        return

    uow.subscriptions.link_checkout_session(
        user_id,
        external_customer_id=customer_id,
        external_subscription_id=subscription_id,
        billing_status="checkout_completed",
    )
    write_billing_audit_event(
        "stripe_subscription_updated",
        user_id=str(user_id),
        detail=f"checkout_completed;subscription={bool(subscription_id)}",
    )


def handle_subscription_event(
    uow: SaasUnitOfWork,
    sub_obj: Any,
    settings: Settings,
    *,
    event_type: str,
) -> None:
    user_id = _resolve_user_id_from_subscription(uow, sub_obj)
    if user_id is None:
        write_billing_audit_event(
            "stripe_webhook_processing_error",
            detail=f"subscription_user_not_found;type={event_type}",
        )
        return

    audit = "stripe_subscription_activated" if event_type == "customer.subscription.created" else "stripe_subscription_updated"
    _apply_subscription_state(uow, user_id, sub_obj, settings, audit_event=audit)


def handle_subscription_deleted(
    uow: SaasUnitOfWork,
    sub_obj: Any,
    settings: Settings,
) -> None:
    user_id = _resolve_user_id_from_subscription(uow, sub_obj)
    if user_id is None:
        write_billing_audit_event(
            "stripe_webhook_processing_error",
            detail="subscription_deleted_user_not_found",
        )
        return

    customer_id = str(_obj_get(sub_obj, "customer") or "").strip() or None
    period_end = _stripe_ts(_obj_get(sub_obj, "current_period_end"))

    uow.subscriptions.downgrade_to_free(user_id, billing_status="deleted", clear_subscription_id=True)
    uow.subscriptions.sync_from_stripe(
        user_id,
        external_customer_id=customer_id,
        current_period_end=period_end,
        start_date=period_end,
        end_date=period_end,
        cancel_at_period_end=False,
    )
    write_billing_audit_event(
        "stripe_subscription_canceled",
        user_id=str(user_id),
        detail="subscription_deleted",
    )


def handle_invoice_event(
    uow: SaasUnitOfWork,
    invoice_obj: Any,
    settings: Settings,
    *,
    succeeded: bool,
) -> None:
    customer_id = str(_obj_get(invoice_obj, "customer") or "").strip()
    sub_id = str(_obj_get(invoice_obj, "subscription") or "").strip() or None
    external_invoice_id = str(_obj_get(invoice_obj, "id") or "").strip()
    if not external_invoice_id:
        write_billing_audit_event("stripe_webhook_processing_error", detail="invoice_missing_id")
        return

    user_id: uuid.UUID | None = None
    sub_record = None
    if sub_id:
        sub_record = uow.subscriptions.get_by_external_subscription_id(sub_id)
        if sub_record is not None:
            user_id = sub_record.user_id
    if user_id is None and customer_id:
        sub_record = uow.subscriptions.get_by_external_customer_id(customer_id)
        if sub_record is not None:
            user_id = sub_record.user_id

    if user_id is None:
        write_billing_audit_event(
            "stripe_webhook_processing_error",
            detail="invoice_user_not_found",
        )
        return

    subscription_uuid = sub_record.id if sub_record else None
    paid_at = _stripe_ts(_obj_get(invoice_obj, "status_transitions", {}).get("paid_at"))
    period_start = _stripe_ts(_obj_get(invoice_obj, "period_start"))
    period_end = _stripe_ts(_obj_get(invoice_obj, "period_end"))
    status = str(_obj_get(invoice_obj, "status") or ("paid" if succeeded else "open"))

    uow.billing_invoices.upsert_from_stripe(
        user_id=user_id,
        subscription_id=subscription_uuid,
        external_invoice_id=external_invoice_id,
        external_subscription_id=sub_id,
        amount_due=_cents_to_decimal(_obj_get(invoice_obj, "amount_due")),
        amount_paid=_cents_to_decimal(_obj_get(invoice_obj, "amount_paid")),
        currency=str(_obj_get(invoice_obj, "currency") or "").upper() or None,
        status=status,
        hosted_invoice_url=str(_obj_get(invoice_obj, "hosted_invoice_url") or "") or None,
        invoice_url=str(_obj_get(invoice_obj, "invoice_pdf") or "") or None,
        period_start=period_start,
        period_end=period_end,
        paid_at=paid_at if succeeded else None,
    )

    if succeeded:
        uow.subscriptions.sync_from_stripe(
            user_id,
            last_payment_status="succeeded",
            last_payment_at=paid_at or datetime.now(timezone.utc),
            billing_status="active",
        )
        write_billing_audit_event(
            "stripe_invoice_paid",
            user_id=str(user_id),
            detail=f"invoice={external_invoice_id[:20]}",
        )
    else:
        existing = uow.subscriptions.get_for_user(user_id)
        current_plan = existing.plan if existing else SubscriptionPlan.FREE
        billing_status = "payment_failed"
        if current_plan in (SubscriptionPlan.STARTER, SubscriptionPlan.PRO):
            billing_status = "past_due"
        else:
            billing_status = "payment_failed"

        uow.subscriptions.sync_from_stripe(
            user_id,
            last_payment_status="failed",
            last_payment_at=datetime.now(timezone.utc),
            billing_status=billing_status,
        )
        write_billing_audit_event(
            "stripe_invoice_failed",
            user_id=str(user_id),
            detail=f"invoice={external_invoice_id[:20]};plan={current_plan.value}",
        )


def dispatch_stripe_event(
    uow: SaasUnitOfWork,
    event: dict[str, Any],
    settings: Settings,
) -> None:
    event_type = str(event.get("type") or "")
    data_obj = event.get("data", {}).get("object")

    if event_type == "checkout.session.completed":
        handle_checkout_session_completed(uow, data_obj, settings)
    elif event_type == "customer.subscription.created":
        handle_subscription_event(uow, data_obj, settings, event_type=event_type)
    elif event_type == "customer.subscription.updated":
        handle_subscription_event(uow, data_obj, settings, event_type=event_type)
    elif event_type == "customer.subscription.deleted":
        handle_subscription_deleted(uow, data_obj, settings)
    elif event_type == "invoice.payment_succeeded":
        handle_invoice_event(uow, data_obj, settings, succeeded=True)
    elif event_type == "invoice.payment_failed":
        handle_invoice_event(uow, data_obj, settings, succeeded=False)
    else:
        write_billing_audit_event(
            "stripe_webhook_received",
            detail=f"ignored_type={event_type}",
        )
