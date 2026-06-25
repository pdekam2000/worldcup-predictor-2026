"""PostgreSQL subscriptions repository."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from worldcup_predictor.database.postgres.enums import BillingCycle, SubscriptionPlan, SubscriptionStatus
from worldcup_predictor.database.postgres.models import Subscription
from worldcup_predictor.database.postgres.schemas import SubscriptionRecord


@dataclass(frozen=True)
class SubscriptionBillingDetail:
    plan: SubscriptionPlan
    status: SubscriptionStatus
    provider: str | None
    billing_status: str | None
    external_customer_id: str | None
    current_period_start: datetime | None
    current_period_end: datetime | None
    cancel_at_period_end: bool
    last_payment_status: str | None
    last_payment_at: datetime | None
    start_date: datetime | None
    end_date: datetime | None


def _to_record(row: Subscription) -> SubscriptionRecord:
    return SubscriptionRecord(
        id=row.id,
        user_id=row.user_id,
        plan=row.plan,
        billing_cycle=row.billing_cycle,
        status=row.status,
        amount=row.amount,
        external_subscription_id=row.external_subscription_id,
        start_date=row.start_date,
        end_date=row.end_date,
        provider=row.provider,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SubscriptionsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _get_row(self, user_id: uuid.UUID) -> Subscription | None:
        return self._session.scalar(select(Subscription).where(Subscription.user_id == user_id))

    def get_for_user(self, user_id: uuid.UUID) -> SubscriptionRecord | None:
        row = self._get_row(user_id)
        return _to_record(row) if row else None

    def get_billing_detail(self, user_id: uuid.UUID) -> SubscriptionBillingDetail | None:
        row = self._get_row(user_id)
        if row is None:
            return None
        return SubscriptionBillingDetail(
            plan=row.plan,
            status=row.status,
            provider=row.provider,
            billing_status=row.billing_status,
            external_customer_id=(row.external_customer_id or "").strip() or None,
            current_period_start=row.current_period_start,
            current_period_end=row.current_period_end,
            cancel_at_period_end=bool(row.cancel_at_period_end),
            last_payment_status=row.last_payment_status,
            last_payment_at=row.last_payment_at,
            start_date=row.start_date,
            end_date=row.end_date,
        )

    def get_or_create_free(self, user_id: uuid.UUID) -> SubscriptionRecord:
        row = self._get_row(user_id)
        if row is None:
            row = Subscription(user_id=user_id)
            self._session.add(row)
            self._session.flush()
        return _to_record(row)

    def upsert(
        self,
        user_id: uuid.UUID,
        *,
        plan: SubscriptionPlan | None = None,
        billing_cycle: BillingCycle | None = None,
        status: SubscriptionStatus | None = None,
        amount: Decimal | None = None,
        external_subscription_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        provider: str | None = None,
    ) -> SubscriptionRecord:
        row = self._get_row(user_id)
        if row is None:
            row = Subscription(user_id=user_id)
            self._session.add(row)
        if plan is not None:
            row.plan = plan
        if billing_cycle is not None:
            row.billing_cycle = billing_cycle
        if status is not None:
            row.status = status
        if amount is not None:
            row.amount = amount
        if external_subscription_id is not None:
            row.external_subscription_id = external_subscription_id
        if start_date is not None:
            row.start_date = start_date
        if end_date is not None:
            row.end_date = end_date
        if provider is not None:
            row.provider = provider
        self._session.flush()
        return _to_record(row)

    def get_external_customer_id(self, user_id: uuid.UUID) -> str | None:
        row = self._get_row(user_id)
        if row is None:
            return None
        raw = (row.external_customer_id or "").strip()
        return raw or None

    def set_external_customer_id(self, user_id: uuid.UUID, customer_id: str) -> None:
        row = self._get_row(user_id)
        if row is None:
            row = Subscription(user_id=user_id)
            self._session.add(row)
        row.external_customer_id = customer_id.strip()
        row.provider = row.provider or "stripe"
        self._session.flush()

    def set_checkout_pending(self, user_id: uuid.UUID) -> None:
        """Mark checkout in progress — does not change plan or quota."""
        row = self._get_row(user_id)
        if row is None:
            row = Subscription(user_id=user_id)
            self._session.add(row)
        row.billing_status = "checkout_pending"
        self._session.flush()

    def get_by_external_customer_id(self, customer_id: str) -> SubscriptionRecord | None:
        cid = (customer_id or "").strip()
        if not cid:
            return None
        row = self._session.scalar(
            select(Subscription).where(Subscription.external_customer_id == cid)
        )
        return _to_record(row) if row else None

    def get_by_external_subscription_id(self, subscription_id: str) -> SubscriptionRecord | None:
        sid = (subscription_id or "").strip()
        if not sid:
            return None
        row = self._session.scalar(
            select(Subscription).where(Subscription.external_subscription_id == sid)
        )
        return _to_record(row) if row else None

    def link_checkout_session(
        self,
        user_id: uuid.UUID,
        *,
        external_customer_id: str | None = None,
        external_subscription_id: str | None = None,
        billing_status: str = "checkout_completed",
    ) -> SubscriptionRecord:
        """Link Stripe IDs after checkout — does not activate paid plan."""
        row = self._get_row(user_id)
        if row is None:
            row = Subscription(user_id=user_id)
            self._session.add(row)
        if external_customer_id:
            row.external_customer_id = external_customer_id.strip()
            row.provider = row.provider or "stripe"
        if external_subscription_id:
            row.external_subscription_id = external_subscription_id.strip()
        row.billing_status = billing_status
        row.billing_updated_at = datetime.now(timezone.utc)
        self._session.flush()
        return _to_record(row)

    def sync_from_stripe(
        self,
        user_id: uuid.UUID,
        *,
        plan: SubscriptionPlan | None = None,
        status: SubscriptionStatus | None = None,
        amount: Decimal | None = None,
        external_customer_id: str | None = None,
        external_subscription_id: str | None = None,
        external_price_id: str | None = None,
        billing_status: str | None = None,
        current_period_start: datetime | None = None,
        current_period_end: datetime | None = None,
        cancel_at_period_end: bool | None = None,
        last_payment_status: str | None = None,
        last_payment_at: datetime | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        clear_subscription_id: bool = False,
    ) -> SubscriptionRecord:
        row = self._get_row(user_id)
        if row is None:
            row = Subscription(user_id=user_id)
            self._session.add(row)

        row.provider = "stripe"
        if plan is not None:
            row.plan = plan
        if status is not None:
            row.status = status
        if amount is not None:
            row.amount = amount
        if external_customer_id is not None:
            row.external_customer_id = external_customer_id.strip() or None
        if external_subscription_id is not None:
            row.external_subscription_id = external_subscription_id.strip() or None
        if clear_subscription_id:
            row.external_subscription_id = None
        if external_price_id is not None:
            row.external_price_id = external_price_id.strip() or None
        if billing_status is not None:
            row.billing_status = billing_status
        if current_period_start is not None:
            row.current_period_start = current_period_start
        if current_period_end is not None:
            row.current_period_end = current_period_end
        if cancel_at_period_end is not None:
            row.cancel_at_period_end = cancel_at_period_end
        if last_payment_status is not None:
            row.last_payment_status = last_payment_status
        if last_payment_at is not None:
            row.last_payment_at = last_payment_at
        if start_date is not None:
            row.start_date = start_date
        if end_date is not None:
            row.end_date = end_date
        row.billing_updated_at = datetime.now(timezone.utc)
        self._session.flush()
        return _to_record(row)

    def downgrade_to_free(
        self,
        user_id: uuid.UUID,
        *,
        billing_status: str = "canceled",
        clear_subscription_id: bool = True,
    ) -> SubscriptionRecord:
        row = self._get_row(user_id)
        if row is None:
            row = Subscription(user_id=user_id)
            self._session.add(row)
        row.plan = SubscriptionPlan.FREE
        row.status = SubscriptionStatus.ACTIVE
        row.billing_cycle = BillingCycle.MONTHLY
        row.amount = None
        row.external_price_id = None
        row.billing_status = billing_status
        row.cancel_at_period_end = False
        if clear_subscription_id:
            row.external_subscription_id = None
        row.billing_updated_at = datetime.now(timezone.utc)
        self._session.flush()
        return _to_record(row)
