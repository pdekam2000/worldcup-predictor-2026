"""PostgreSQL stripe_webhook_events repository — idempotent webhook storage."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from worldcup_predictor.database.postgres.models import StripeWebhookEvent


@dataclass(frozen=True)
class WebhookEventRecord:
    id: uuid.UUID
    stripe_event_id: str
    event_type: str | None
    processed: bool
    processing_error: str | None


class WebhookEventsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_stripe_event_id(self, stripe_event_id: str) -> WebhookEventRecord | None:
        row = self._session.scalar(
            select(StripeWebhookEvent).where(StripeWebhookEvent.stripe_event_id == stripe_event_id)
        )
        if row is None:
            return None
        return WebhookEventRecord(
            id=row.id,
            stripe_event_id=row.stripe_event_id,
            event_type=row.event_type,
            processed=row.processed,
            processing_error=row.processing_error,
        )

    def insert_event(
        self,
        *,
        stripe_event_id: str,
        event_type: str | None,
        api_version: str | None,
        livemode: bool | None,
        payload_hash: str | None,
    ) -> tuple[WebhookEventRecord, bool]:
        """Insert event row. Returns (record, is_duplicate)."""
        existing = self.get_by_stripe_event_id(stripe_event_id)
        if existing is not None:
            return existing, True

        row = StripeWebhookEvent(
            stripe_event_id=stripe_event_id,
            event_type=event_type,
            api_version=api_version,
            livemode=livemode,
            payload_hash=payload_hash,
            processed=False,
        )
        self._session.add(row)
        self._session.flush()

        return WebhookEventRecord(
            id=row.id,
            stripe_event_id=row.stripe_event_id,
            event_type=row.event_type,
            processed=row.processed,
            processing_error=row.processing_error,
        ), False

    def mark_processed(
        self,
        row_id: uuid.UUID,
        *,
        error: str | None = None,
    ) -> None:
        row = self._session.get(StripeWebhookEvent, row_id)
        if row is None:
            return
        row.processed = True
        row.processed_at = datetime.now(timezone.utc)
        row.processing_error = (error or "")[:2000] or None
        self._session.flush()
