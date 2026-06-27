"""Phase 39B-1 — billing Pydantic schemas (no secrets)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PaidPlanKey = Literal["starter", "pro"]
StripeModeDisplay = Literal["test", "live", "missing"]


class BillingReadinessResponse(BaseModel):
    status: str = "ok"
    stripe_configured: bool
    stripe_mode: StripeModeDisplay
    stripe_package_available: bool
    starter_price_configured: bool
    pro_price_configured: bool
    webhook_secret_configured: bool
    success_url_configured: bool
    cancel_url_configured: bool
    checkout_enabled: bool = False
    checkout_configured: bool = False
    portal_enabled: bool = False
    message: str | None = None


class PlanPriceMappingError(Exception):
    """Raised when plan cannot be mapped to a Stripe price."""

    def __init__(self, message: str, *, code: str = "invalid_plan") -> None:
        super().__init__(message)
        self.code = code


class CheckoutNotImplementedError(Exception):
    code = "checkout_not_implemented"


class CheckoutSessionRequest(BaseModel):
    plan: str = Field(..., min_length=1)


class CheckoutSessionResponse(BaseModel):
    status: str = "ok"
    checkout_url: str
    session_id: str


class CustomerPortalRequest(BaseModel):
    return_url: str | None = None


class CustomerPortalResponse(BaseModel):
    status: str = "ok"
    portal_url: str


class CheckoutValidationError(Exception):
    def __init__(self, message: str, *, code: str = "checkout_error", status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
