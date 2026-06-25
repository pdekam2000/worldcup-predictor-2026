"""PostgreSQL billing_invoices repository."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from worldcup_predictor.database.postgres.models import BillingInvoice


@dataclass(frozen=True)
class BillingInvoiceListItem:
    external_invoice_id: str
    amount_due: Decimal | None
    amount_paid: Decimal | None
    currency: str | None
    status: str | None
    hosted_invoice_url: str | None
    period_start: datetime | None
    period_end: datetime | None
    paid_at: datetime | None
    created_at: datetime


@dataclass(frozen=True)
class BillingInvoiceRecord:
    id: uuid.UUID
    user_id: uuid.UUID
    external_invoice_id: str
    status: str | None


class BillingInvoicesRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_from_stripe(
        self,
        *,
        user_id: uuid.UUID,
        subscription_id: uuid.UUID | None,
        external_invoice_id: str,
        external_subscription_id: str | None = None,
        amount_due: Decimal | None = None,
        amount_paid: Decimal | None = None,
        currency: str | None = None,
        status: str | None = None,
        invoice_url: str | None = None,
        hosted_invoice_url: str | None = None,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        paid_at: datetime | None = None,
    ) -> BillingInvoiceRecord:
        row = self._session.scalar(
            select(BillingInvoice).where(BillingInvoice.external_invoice_id == external_invoice_id)
        )
        if row is None:
            row = BillingInvoice(
                user_id=user_id,
                external_invoice_id=external_invoice_id,
                provider="stripe",
            )
            self._session.add(row)

        row.user_id = user_id
        row.subscription_id = subscription_id
        row.external_subscription_id = external_subscription_id
        row.provider = "stripe"
        if amount_due is not None:
            row.amount_due = amount_due
        if amount_paid is not None:
            row.amount_paid = amount_paid
        if currency is not None:
            row.currency = currency
        if status is not None:
            row.status = status
        if invoice_url is not None:
            row.invoice_url = invoice_url
        if hosted_invoice_url is not None:
            row.hosted_invoice_url = hosted_invoice_url
        if period_start is not None:
            row.period_start = period_start
        if period_end is not None:
            row.period_end = period_end
        if paid_at is not None:
            row.paid_at = paid_at

        self._session.flush()
        return BillingInvoiceRecord(
            id=row.id,
            user_id=row.user_id,
            external_invoice_id=row.external_invoice_id,
            status=row.status,
        )

    def list_for_user(self, user_id: uuid.UUID, *, limit: int = 50, offset: int = 0) -> list[BillingInvoiceListItem]:
        rows = self._session.scalars(
            select(BillingInvoice)
            .where(BillingInvoice.user_id == user_id)
            .order_by(BillingInvoice.created_at.desc())
            .limit(max(1, min(limit, 100)))
            .offset(max(0, offset))
        ).all()
        return [
            BillingInvoiceListItem(
                external_invoice_id=row.external_invoice_id,
                amount_due=row.amount_due,
                amount_paid=row.amount_paid,
                currency=row.currency,
                status=row.status,
                hosted_invoice_url=row.hosted_invoice_url,
                period_start=row.period_start,
                period_end=row.period_end,
                paid_at=row.paid_at,
                created_at=row.created_at,
            )
            for row in rows
        ]

    def count_for_user(self, user_id: uuid.UUID) -> int:
        return int(
            self._session.scalar(
                select(func.count()).select_from(BillingInvoice).where(BillingInvoice.user_id == user_id)
            )
            or 0
        )
