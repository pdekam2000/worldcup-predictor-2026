"""Phase 39B-3 — Stripe webhook orchestration (signature verify + idempotency)."""

from __future__ import annotations

import hashlib
import logging
from functools import lru_cache
from typing import Any

from worldcup_predictor.billing.billing_audit import write_billing_audit_event
from worldcup_predictor.billing.stripe_client import StripeClient, StripeClientError, get_stripe_client
from worldcup_predictor.billing.webhook_handlers import dispatch_stripe_event
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.postgres.session import session_scope
from worldcup_predictor.database.postgres.uow import build_uow
from worldcup_predictor.database.saas_factory import require_postgres

logger = logging.getLogger(__name__)

_SUPPORTED_EVENTS = frozenset(
    {
        "checkout.session.completed",
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "invoice.payment_succeeded",
        "invoice.payment_failed",
    }
)


class WebhookVerificationError(Exception):
    def __init__(self, message: str, *, code: str = "invalid_signature") -> None:
        super().__init__(message)
        self.code = code


class WebhookService:
    def __init__(self, settings: Settings | None = None, client: StripeClient | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = client or StripeClient(self._settings)

    def _payload_hash(self, payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    def verify_and_parse(self, payload: bytes, signature_header: str | None) -> dict[str, Any]:
        secret = (self._settings.stripe_webhook_secret or "").strip()
        if not secret:
            raise WebhookVerificationError("Webhook secret not configured", code="webhook_not_configured")
        if not signature_header:
            raise WebhookVerificationError("Missing Stripe signature", code="missing_signature")
        try:
            return self._client.construct_webhook_event(
                payload=payload,
                signature_header=signature_header,
                webhook_secret=secret,
            )
        except StripeClientError as exc:
            write_billing_audit_event(
                "stripe_webhook_invalid_signature",
                detail=exc.code,
            )
            raise WebhookVerificationError(str(exc), code=exc.code) from exc

    def process_webhook(self, payload: bytes, signature_header: str | None) -> dict[str, Any]:
        event = self.verify_and_parse(payload, signature_header)
        event_id = str(event.get("id") or "").strip()
        event_type = str(event.get("type") or "").strip()

        write_billing_audit_event(
            "stripe_webhook_received",
            detail=f"type={event_type};id={event_id[:24]}",
        )

        if not event_id:
            raise WebhookVerificationError("Missing event id", code="invalid_event")

        require_postgres(self._settings)
        processing_error: str | None = None
        with session_scope(self._settings) as session:
            uow = build_uow(session)
            record, is_duplicate = uow.webhook_events.insert_event(
                stripe_event_id=event_id,
                event_type=event_type or None,
                api_version=str(event.get("api_version") or "") or None,
                livemode=bool(event.get("livemode")) if event.get("livemode") is not None else None,
                payload_hash=self._payload_hash(payload),
            )

            if is_duplicate:
                write_billing_audit_event(
                    "stripe_webhook_duplicate",
                    detail=f"type={event_type};id={event_id[:24]}",
                )
                return {"status": "duplicate", "event_id": event_id}

            try:
                if event_type in _SUPPORTED_EVENTS:
                    dispatch_stripe_event(uow, event, self._settings)
                else:
                    write_billing_audit_event(
                        "stripe_webhook_received",
                        detail=f"unsupported_type={event_type}",
                    )
            except Exception as exc:
                processing_error = f"{type(exc).__name__}: {exc}"
                write_billing_audit_event(
                    "stripe_webhook_processing_error",
                    detail=f"type={event_type};error={type(exc).__name__}",
                )
                logger.warning("stripe webhook processing failed: %s", type(exc).__name__)

            uow.webhook_events.mark_processed(record.id, error=processing_error)

        if processing_error:
            return {"status": "processed_with_error", "event_id": event_id}
        return {"status": "processed", "event_id": event_id}


@lru_cache
def get_webhook_service() -> WebhookService:
    return WebhookService()
