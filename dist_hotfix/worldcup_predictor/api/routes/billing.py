"""Phase 39B-1/39B-2/39B-3 — billing API (readiness + checkout + webhooks)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from worldcup_predictor.api.deps import get_current_user, require_checkout_user
from worldcup_predictor.api.web_auth import WebAuthUser
from worldcup_predictor.billing.billing_service import BillingService, get_billing_service
from worldcup_predictor.billing.schemas import (
    CheckoutSessionRequest,
    CheckoutValidationError,
    CustomerPortalRequest,
    PlanPriceMappingError,
)
from worldcup_predictor.billing.webhook_service import WebhookService, WebhookVerificationError, get_webhook_service

router = APIRouter(prefix="/billing", tags=["billing"])
legacy_router = APIRouter(tags=["billing-legacy"])

_CHECKOUT_INACTIVE_MSG = "Payment checkout is not active yet."


def _legacy_checkout_payload(svc: BillingService) -> dict[str, Any]:
    """Safe JSON for old client paths — never creates a Stripe session."""
    readiness = svc.readiness()
    configured = readiness.checkout_enabled
    return {
        "status": "ok",
        "checkout_configured": configured,
        "checkout_enabled": configured,
        "message": readiness.message or (_CHECKOUT_INACTIVE_MSG if not configured else None),
    }


@router.get("/readiness")
def billing_readiness(
    _user: WebAuthUser = Depends(get_current_user),
    svc: BillingService = Depends(get_billing_service),
) -> dict[str, Any]:
    """Stripe billing readiness — yes/no only, no secrets or price IDs."""
    return svc.readiness().model_dump()


@router.get("/checkout")
@router.post("/checkout")
def billing_checkout_compat(
    svc: BillingService = Depends(get_billing_service),
) -> dict[str, Any]:
    """Legacy /api/billing/checkout — safe placeholder, no Stripe session."""
    return _legacy_checkout_payload(svc)


@legacy_router.get("/subscription/checkout")
@legacy_router.post("/subscription/checkout")
def legacy_subscription_checkout(
    svc: BillingService = Depends(get_billing_service),
) -> dict[str, Any]:
    """Legacy /api/subscription/checkout — avoids 404 from old clients."""
    return _legacy_checkout_payload(svc)


@legacy_router.get("/stripe/create-checkout-session")
@legacy_router.post("/stripe/create-checkout-session")
def legacy_stripe_checkout(
    svc: BillingService = Depends(get_billing_service),
) -> dict[str, Any]:
    """Legacy /api/stripe/create-checkout-session — safe placeholder only."""
    return _legacy_checkout_payload(svc)


@router.post("/create-checkout-session")
def create_checkout_session(
    body: CheckoutSessionRequest,
    user: WebAuthUser = Depends(require_checkout_user),
    svc: BillingService = Depends(get_billing_service),
) -> dict[str, Any]:
    """Create Stripe Checkout session — does not activate plan (webhook authority in 39B-3)."""
    try:
        return svc.create_checkout_session(
            user_id=user.id,
            email=user.email or "",
            plan=body.plan,
        )
    except PlanPriceMappingError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc), "code": exc.code}) from exc
    except CheckoutValidationError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": str(exc), "code": exc.code},
        ) from exc


@router.get("/status")
def billing_status(
    user: WebAuthUser = Depends(get_current_user),
    svc: BillingService = Depends(get_billing_service),
) -> dict[str, Any]:
    """Current user billing status — no secrets."""
    return svc.get_billing_status(user.id)


@router.get("/history")
def billing_history(
    user: WebAuthUser = Depends(get_current_user),
    svc: BillingService = Depends(get_billing_service),
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Invoice history for current user."""
    return svc.get_billing_history(user.id, limit=limit, offset=offset)


@router.post("/customer-portal")
def customer_portal(
    body: CustomerPortalRequest | None = None,
    user: WebAuthUser = Depends(require_checkout_user),
    svc: BillingService = Depends(get_billing_service),
) -> dict[str, Any]:
    """Stripe Customer Portal — manage subscription and payment method."""
    try:
        return svc.create_customer_portal_session(
            user.id,
            return_url=body.return_url if body else None,
        )
    except CheckoutValidationError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": str(exc), "code": exc.code},
        ) from exc


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    svc: WebhookService = Depends(get_webhook_service),
) -> dict[str, Any]:
    """Stripe webhook — no JWT; signature verified via STRIPE_WEBHOOK_SECRET."""
    body = await request.body()
    signature = request.headers.get("Stripe-Signature")
    try:
        return svc.process_webhook(body, signature)
    except WebhookVerificationError as exc:
        raise HTTPException(
            status_code=400,
            detail={"message": str(exc), "code": exc.code},
        ) from exc
