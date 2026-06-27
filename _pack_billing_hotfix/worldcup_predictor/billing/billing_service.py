"""Phase 39B-1/39B-2 — billing service (readiness + checkout session creation)."""

from __future__ import annotations

import threading
import time
import uuid
from functools import lru_cache

from worldcup_predictor.billing.billing_audit import write_billing_audit_event
from worldcup_predictor.billing.checkout_rate_limit import (
    check_checkout_allowed,
    record_checkout_attempt,
)
from worldcup_predictor.billing.schemas import (
    BillingReadinessResponse,
    CheckoutValidationError,
    PlanPriceMappingError,
)
from worldcup_predictor.billing.stripe_client import StripeClient, StripeClientError, get_stripe_client
from worldcup_predictor.billing.user_messages import (
    CHECKOUT_INACTIVE_MSG,
    PLAN_UNAVAILABLE_MSG,
    message_for_code,
)
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.postgres.enums import SubscriptionPlan, SubscriptionStatus
from worldcup_predictor.database.postgres.schemas import SubscriptionRecord
from worldcup_predictor.database.saas_factory import saas_uow

_PAID_PLANS = frozenset({"starter", "pro"})
_PLAN_RANK = {
    SubscriptionPlan.FREE: 0,
    SubscriptionPlan.STARTER: 1,
    SubscriptionPlan.PRO: 2,
    SubscriptionPlan.ELITE: 2,
    SubscriptionPlan.UNLIMITED: 2,
}

_session_lock = threading.Lock()
_recent_sessions: dict[str, dict] = {}
_SESSION_REUSE_SECONDS = 900


class BillingService:
    def __init__(self, settings: Settings | None = None, client: StripeClient | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = client or StripeClient(self._settings)

    def plan_to_price_id(self, plan: str) -> str:
        key = str(plan or "").strip().lower()
        if key == "free":
            raise PlanPriceMappingError("Free plan does not require checkout", code="free_plan")
        if key not in _PAID_PLANS:
            raise PlanPriceMappingError(f"Unknown plan: {plan}", code="unknown_plan")
        price_id = self._settings.stripe_price_id_for_plan(key)
        if not price_id:
            raise PlanPriceMappingError(PLAN_UNAVAILABLE_MSG, code="price_not_configured")
        return price_id

    def reject_checkout_plan(self, plan: str) -> None:
        self.plan_to_price_id(plan)

    def _stripe_prices_valid(self) -> bool:
        if not self._client.sdk_ready() or not self._settings.stripe_starter_price_configured:
            return False
        if not self._settings.stripe_pro_price_configured:
            return False
        try:
            self._client.validate_price_id(self._settings.stripe_starter_price_id)
            self._client.validate_price_id(self._settings.stripe_pro_price_id)
            return True
        except StripeClientError:
            return False

    def readiness(self) -> BillingReadinessResponse:
        s = self._settings
        mode = s.stripe_mode_normalized
        starter_ok = s.stripe_starter_price_configured
        pro_ok = s.stripe_pro_price_configured
        secret_ok = s.stripe_secret_key_configured
        configured = (
            secret_ok
            and starter_ok
            and pro_ok
            and s.stripe_success_url_configured
            and s.stripe_cancel_url_configured
            and self._client.package_available
            and mode in ("test", "live")
        )
        prices_valid = self._stripe_prices_valid() if configured else False
        checkout_enabled = configured and prices_valid and self._client.sdk_ready()
        if checkout_enabled:
            message = None
        elif not secret_ok or not self._client.sdk_ready() or not self._client.package_available:
            message = CHECKOUT_INACTIVE_MSG
        elif not starter_ok or not pro_ok:
            message = PLAN_UNAVAILABLE_MSG
        elif configured and not prices_valid:
            message = PLAN_UNAVAILABLE_MSG
        else:
            message = CHECKOUT_INACTIVE_MSG
        return BillingReadinessResponse(
            stripe_configured=configured,
            stripe_mode=mode if mode in ("test", "live") else "missing",
            stripe_package_available=self._client.package_available,
            starter_price_configured=starter_ok,
            pro_price_configured=pro_ok,
            webhook_secret_configured=s.stripe_webhook_secret_configured,
            success_url_configured=s.stripe_success_url_configured,
            cancel_url_configured=s.stripe_cancel_url_configured,
            checkout_enabled=checkout_enabled,
            checkout_configured=checkout_enabled,
            portal_enabled=(
                checkout_enabled
                and s.stripe_portal_return_url_configured
            ),
            message=message,
        )

    def _normalize_plan(self, plan: SubscriptionPlan) -> SubscriptionPlan:
        if plan in (SubscriptionPlan.ELITE, SubscriptionPlan.UNLIMITED):
            return SubscriptionPlan.PRO
        return plan

    def validate_checkout_upgrade(self, sub: SubscriptionRecord, requested_plan: str) -> None:
        req_key = str(requested_plan or "").strip().lower()
        if req_key == "free":
            raise CheckoutValidationError("Free plan cannot use checkout", code="free_plan")
        if req_key not in _PAID_PLANS:
            raise CheckoutValidationError("Unknown plan", code="unknown_plan")

        current = self._normalize_plan(sub.plan)
        requested = SubscriptionPlan(req_key)
        cur_rank = _PLAN_RANK.get(current, 0)
        req_rank = _PLAN_RANK.get(requested, 0)

        if current == requested and sub.status == SubscriptionStatus.ACTIVE:
            raise CheckoutValidationError(
                "You already have an active subscription for this plan.",
                code="duplicate_active_plan",
                status_code=409,
            )
        if cur_rank >= req_rank and current != SubscriptionPlan.FREE:
            raise CheckoutValidationError(
                "Cannot checkout for the same or lower plan tier.",
                code="invalid_upgrade",
                status_code=409,
            )

    def _session_cache_key(self, user_id: str, plan: str) -> str:
        return f"{user_id}:{plan.strip().lower()}"

    def _get_reusable_session(self, user_id: str, plan: str) -> dict | None:
        key = self._session_cache_key(user_id, plan)
        now = time.time()
        with _session_lock:
            entry = _recent_sessions.get(key)
            if not entry:
                return None
            if now - float(entry.get("created_at", 0)) > _SESSION_REUSE_SECONDS:
                _recent_sessions.pop(key, None)
                return None
            return entry

    def _store_session(self, user_id: str, plan: str, *, checkout_url: str, session_id: str) -> None:
        key = self._session_cache_key(user_id, plan)
        with _session_lock:
            _recent_sessions[key] = {
                "checkout_url": checkout_url,
                "session_id": session_id,
                "created_at": time.time(),
            }

    def create_checkout_session(
        self,
        *,
        user_id: str,
        email: str,
        plan: str,
    ) -> dict[str, str]:
        readiness = self.readiness()
        if not readiness.checkout_enabled:
            raise CheckoutValidationError(
                readiness.message or CHECKOUT_INACTIVE_MSG,
                code="checkout_disabled",
                status_code=503,
            )

        plan_key = str(plan or "").strip().lower()
        price_id = self.plan_to_price_id(plan_key)

        allowed, retry = check_checkout_allowed(user_id=user_id)
        if not allowed:
            raise CheckoutValidationError(
                "Too many checkout attempts. Please try again later.",
                code="checkout_rate_limited",
                status_code=429,
            )

        uid = uuid.UUID(user_id)
        with saas_uow() as uow:
            sub = uow.subscriptions.get_or_create_free(uid)
            self.validate_checkout_upgrade(sub, plan_key)

        reused = self._get_reusable_session(user_id, plan_key)
        if reused:
            write_billing_audit_event(
                "stripe_checkout_reused",
                user_id=user_id,
                detail=f"plan={plan_key};session_id={reused['session_id']}",
            )
            return {
                "status": "ok",
                "checkout_url": reused["checkout_url"],
                "session_id": reused["session_id"],
            }

        with saas_uow() as uow:
            customer_id = uow.subscriptions.get_external_customer_id(uid)

        metadata = {
            "user_id": user_id,
            "email": email.strip().lower(),
            "requested_plan": plan_key,
        }

        if not customer_id:
            customer_id = self._client.create_customer(
                email=email,
                name=email.split("@")[0],
                metadata={"user_id": user_id},
            )
            with saas_uow() as uow:
                uow.subscriptions.set_external_customer_id(uid, customer_id)

        try:
            checkout_url, session_id = self._client.create_checkout_session(
                customer_id=customer_id,
                price_id=price_id,
                success_url=self._settings.stripe_success_url.strip(),
                cancel_url=self._settings.stripe_cancel_url.strip(),
                metadata=metadata,
            )
        except StripeClientError as exc:
            write_billing_audit_event(
                "stripe_checkout_failed",
                user_id=user_id,
                detail=f"plan={plan_key};code={exc.code}",
            )
            status = 400 if exc.code in {"stripe_price_invalid", "stripe_price_check_failed"} else 502
            raise CheckoutValidationError(message_for_code(exc.code, str(exc)), code=exc.code, status_code=status) from exc

        with saas_uow() as uow:
            uow.subscriptions.set_checkout_pending(uid)

        record_checkout_attempt(user_id=user_id)
        self._store_session(user_id, plan_key, checkout_url=checkout_url, session_id=session_id)
        write_billing_audit_event(
            "stripe_checkout_created",
            user_id=user_id,
            detail=f"plan={plan_key};session_id={session_id}",
        )
        return {"status": "ok", "checkout_url": checkout_url, "session_id": session_id}

    def get_billing_status(self, user_id: str) -> dict:
        from worldcup_predictor.billing.billing_serializers import billing_status_to_dict

        uid = uuid.UUID(user_id)
        with saas_uow() as uow:
            detail = uow.subscriptions.get_billing_detail(uid)
            if detail is None:
                uow.subscriptions.get_or_create_free(uid)
                detail = uow.subscriptions.get_billing_detail(uid)
            assert detail is not None
            payload = billing_status_to_dict(detail)
        readiness = self.readiness()
        payload["portal_enabled"] = readiness.portal_enabled and bool(
            detail.external_customer_id if detail else False
        )
        return payload

    def get_billing_history(self, user_id: str, *, limit: int = 50, offset: int = 0) -> dict:
        from worldcup_predictor.billing.billing_serializers import invoice_to_dict

        uid = uuid.UUID(user_id)
        with saas_uow() as uow:
            items = uow.billing_invoices.list_for_user(uid, limit=limit, offset=offset)
        return {"status": "ok", "invoices": [invoice_to_dict(item) for item in items]}

    def get_admin_billing_summary(self, user_id: str) -> dict:
        from worldcup_predictor.billing.billing_serializers import admin_billing_to_dict

        uid = uuid.UUID(user_id)
        with saas_uow() as uow:
            detail = uow.subscriptions.get_billing_detail(uid)
            if detail is None:
                return {
                    "status": "ok",
                    "plan": SubscriptionPlan.FREE.value,
                    "subscription_status": SubscriptionStatus.ACTIVE.value,
                    "billing_status": None,
                    "stripe_customer_id_masked": None,
                    "current_period_end": None,
                    "last_payment_status": None,
                    "last_payment_at": None,
                    "invoice_count": 0,
                }
            count = uow.billing_invoices.count_for_user(uid)
            return admin_billing_to_dict(detail, invoice_count=count)

    def create_customer_portal_session(self, user_id: str, *, return_url: str | None = None) -> dict[str, str]:
        readiness = self.readiness()
        if not readiness.portal_enabled:
            raise CheckoutValidationError("Customer portal is not enabled", code="portal_disabled", status_code=503)

        uid = uuid.UUID(user_id)
        with saas_uow() as uow:
            customer_id = uow.subscriptions.get_external_customer_id(uid)

        if not customer_id:
            raise CheckoutValidationError(
                "No Stripe customer on file. Complete checkout first.",
                code="stripe_customer_missing",
                status_code=409,
            )

        effective_return = (return_url or "").strip() or self._settings.effective_stripe_portal_return_url
        if not effective_return:
            raise CheckoutValidationError("Portal return URL is not configured", code="portal_return_missing", status_code=503)

        try:
            portal_url = self._client.create_portal_session(
                customer_id=customer_id,
                return_url=effective_return,
            )
        except StripeClientError as exc:
            write_billing_audit_event(
                "stripe_portal_failed",
                user_id=user_id,
                detail=f"code={exc.code}",
            )
            raise CheckoutValidationError(str(exc), code=exc.code, status_code=502) from exc

        write_billing_audit_event("stripe_portal_created", user_id=user_id)
        return {"status": "ok", "portal_url": portal_url}


def get_billing_service() -> BillingService:
    return BillingService()
