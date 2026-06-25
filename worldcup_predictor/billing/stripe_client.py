"""Phase 39B-2 — Stripe client (checkout session creation)."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from worldcup_predictor.billing.user_messages import PLAN_UNAVAILABLE_MSG
from worldcup_predictor.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

_STRIPE_IMPORT_ERROR: str | None = None

try:
    import stripe  # type: ignore[import-untyped]

    _STRIPE_AVAILABLE = True
except ImportError as exc:
    stripe = None  # type: ignore[assignment,misc]
    _STRIPE_AVAILABLE = False
    _STRIPE_IMPORT_ERROR = str(exc)


class StripeClientError(Exception):
    def __init__(self, message: str, *, code: str = "stripe_error") -> None:
        super().__init__(message)
        self.code = code


class StripeClient:
    """Thin Stripe SDK wrapper."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._api_key = (self._settings.stripe_secret_key or "").strip()
        if _STRIPE_AVAILABLE and stripe is not None and self._api_key:
            stripe.api_key = self._api_key

    @property
    def package_available(self) -> bool:
        return _STRIPE_AVAILABLE

    @property
    def import_error(self) -> str | None:
        return _STRIPE_IMPORT_ERROR

    @property
    def secret_key_present(self) -> bool:
        return bool(self._api_key)

    @property
    def mode(self) -> str:
        return self._settings.stripe_mode_normalized

    def sdk_ready(self) -> bool:
        return _STRIPE_AVAILABLE and self.secret_key_present

    def ping_import(self) -> dict[str, Any]:
        return {
            "package_available": _STRIPE_AVAILABLE,
            "secret_key_present": self.secret_key_present,
            "sdk_ready": self.sdk_ready(),
            "mode": self.mode,
        }

    def _require_sdk(self) -> None:
        if not self.sdk_ready():
            raise StripeClientError("Stripe is not configured", code="stripe_not_configured")

    def create_customer(
        self,
        *,
        email: str,
        name: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str:
        self._require_sdk()
        assert stripe is not None
        try:
            customer = stripe.Customer.create(
                email=email.strip().lower(),
                name=(name or "").strip() or None,
                metadata=metadata or {},
            )
            return str(customer.id)
        except Exception as exc:
            logger.warning("stripe customer create failed: %s", type(exc).__name__)
            raise StripeClientError("Could not create billing customer", code="stripe_customer_failed") from exc

    def validate_price_id(self, price_id: str) -> None:
        """Verify price exists in the configured Stripe account."""
        self._require_sdk()
        assert stripe is not None
        pid = str(price_id or "").strip()
        if not pid:
            raise StripeClientError(PLAN_UNAVAILABLE_MSG, code="stripe_price_invalid")
        try:
            stripe.Price.retrieve(pid)
        except Exception as exc:
            user_msg = str(getattr(exc, "user_message", None) or exc)
            if "No such price" in user_msg:
                raise StripeClientError(PLAN_UNAVAILABLE_MSG, code="stripe_price_invalid") from exc
            logger.warning("stripe price retrieve failed: %s", type(exc).__name__)
            raise StripeClientError("Could not verify Stripe price", code="stripe_price_check_failed") from exc

    def create_checkout_session(
        self,
        *,
        customer_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        metadata: dict[str, str],
    ) -> tuple[str, str]:
        self._require_sdk()
        assert stripe is not None
        try:
            session = stripe.checkout.Session.create(
                customer=customer_id,
                mode="subscription",
                line_items=[{"price": price_id, "quantity": 1}],
                success_url=success_url,
                cancel_url=cancel_url,
                metadata=metadata,
                subscription_data={"metadata": metadata},
            )
            url = str(session.url or "")
            session_id = str(session.id or "")
            if not url or not session_id:
                raise StripeClientError("Invalid checkout session response", code="stripe_session_invalid")
            return url, session_id
        except StripeClientError:
            raise
        except Exception as exc:
            logger.warning("stripe checkout session create failed: %s", type(exc).__name__)
            user_msg = str(getattr(exc, "user_message", None) or exc)
            if "No such price" in user_msg:
                raise StripeClientError(PLAN_UNAVAILABLE_MSG, code="stripe_price_invalid") from exc
            raise StripeClientError("Could not create checkout session", code="stripe_checkout_failed") from exc

    def construct_webhook_event(
        self,
        *,
        payload: bytes,
        signature_header: str,
        webhook_secret: str,
    ) -> dict[str, Any]:
        self._require_sdk()
        assert stripe is not None
        try:
            event = stripe.Webhook.construct_event(payload, signature_header, webhook_secret)
            if hasattr(event, "to_dict"):
                return event.to_dict()
            if isinstance(event, dict):
                return event
            return dict(event)
        except Exception as exc:
            exc_name = type(exc).__name__
            if exc_name == "SignatureVerificationError" or "SignatureVerification" in exc_name:
                logger.warning("stripe webhook signature verification failed")
                raise StripeClientError("Invalid webhook signature", code="invalid_signature") from exc
            logger.warning("stripe webhook construct failed: %s", exc_name)
            raise StripeClientError("Could not parse webhook event", code="webhook_parse_failed") from exc

    def create_portal_session(self, *, customer_id: str, return_url: str) -> str:
        self._require_sdk()
        assert stripe is not None
        try:
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )
            url = str(session.url or "")
            if not url:
                raise StripeClientError("Invalid portal session response", code="stripe_portal_invalid")
            return url
        except StripeClientError:
            raise
        except Exception as exc:
            logger.warning("stripe portal session create failed: %s", type(exc).__name__)
            raise StripeClientError("Could not create customer portal session", code="stripe_portal_failed") from exc


@lru_cache
def get_stripe_client() -> StripeClient:
    return StripeClient(get_settings())
