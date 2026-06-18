"""PostgreSQL subscriptions repository."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from worldcup_predictor.database.postgres.enums import BillingCycle, SubscriptionPlan, SubscriptionStatus
from worldcup_predictor.database.postgres.models import Subscription
from worldcup_predictor.database.postgres.schemas import SubscriptionRecord


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
