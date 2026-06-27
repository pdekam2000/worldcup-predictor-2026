"""Authentication routes for the independent React frontend."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from worldcup_predictor.api.deps import get_current_user
from worldcup_predictor.api.web_auth import (
    WebAuthUser,
    issue_access_token_for_record,
    login_with_password,
    register_with_password,
    revoke_session_token,
)
from worldcup_predictor.auth.auth_audit import write_auth_audit_event
from worldcup_predictor.auth.change_password import change_password_for_user
from worldcup_predictor.auth.auth_rate_limit import (
    check_forgot_password_ip_allowed,
    check_login_allowed,
    check_register_allowed,
    clear_login_failures,
    record_forgot_password_ip,
    record_login_failure,
    record_register_attempt,
)
from worldcup_predictor.auth.email_verification import resend_verification_for_email, verify_email_token
from worldcup_predictor.auth.password_reset import (
    request_password_reset_for_email,
    reset_password_with_token,
)
from worldcup_predictor.database.saas_factory import saas_uow

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=128)
    password: str = Field(..., min_length=1, max_length=256)


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=128)
    password: str = Field(..., min_length=8, max_length=256)
    invite_code: str | None = Field(default=None, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip()


class ResendVerificationRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=128)


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=16, max_length=512)
    password: str = Field(..., min_length=8, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=1, max_length=256)
    confirm_password: str = Field(..., min_length=1, max_length=256)


class ChangePasswordResponse(BaseModel):
    password_changed: bool = True
    relogin_required: bool = True
    message: str = "Password changed successfully."


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class RegisterPendingResponse(BaseModel):
    status: str = "ok"
    message: str
    email: str
    registration_success: bool = True
    email_verification_required: bool = True
    verification_required: bool = True
    verification_email_sent: bool = False
    email_delivery_status: str | None = None


class ResendVerificationResponse(BaseModel):
    status: str = "ok"
    message: str
    verification_email_sent: bool = False
    email_delivery_status: str | None = None
    already_verified: bool = False


class MessageResponse(BaseModel):
    message: str
    status: str = "ok"


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _register_message(*, verification_email_sent: bool, email_delivery_status: str | None) -> str:
    if verification_email_sent:
        return "Account created. Please check your email to verify your account."
    if email_delivery_status == "email_not_configured":
        return (
            "Account created, but verification email could not be sent because email delivery "
            "is not configured. Use Resend verification email or contact support."
        )
    if email_delivery_status == "send_failed":
        return (
            "Account created, but verification email could not be sent. "
            "Please use Resend verification email or contact support."
        )
    return "Account created. Please check your email to verify your account."


def _resend_response(email: str, request: Request) -> ResendVerificationResponse:
    outcome = resend_verification_for_email(email.strip().lower())
    ip = _client_ip(request)
    if outcome.already_verified:
        write_auth_audit_event("verification_resend_already_verified", email=email.strip().lower(), ip=ip)
        return ResendVerificationResponse(
            message="This email address is already verified.",
            already_verified=True,
        )
    if outcome.rate_limited:
        write_auth_audit_event("verification_resend_rate_limited", email=email.strip().lower(), ip=ip)
        return ResendVerificationResponse(
            message="Too many requests. Please wait before requesting another verification email.",
        )
    if not outcome.user_found:
        write_auth_audit_event("verification_resend_generic", email=email.strip().lower(), ip=ip)
        return ResendVerificationResponse(
            message="If that email is registered and unverified, a new link was sent.",
        )
    write_auth_audit_event(
        "verification_resent",
        email=email.strip().lower(),
        ip=ip,
        detail=f"sent={outcome.verification_email_sent};status={outcome.email_delivery_status}",
    )
    if outcome.verification_email_sent:
        message = "Verification email sent. Please check your inbox."
    elif outcome.email_delivery_status == "email_not_configured":
        message = (
            "Verification email could not be sent because email delivery is not configured. "
            "Please contact support."
        )
    elif outcome.email_delivery_status == "send_failed":
        message = "Verification email could not be sent. Please try again later or contact support."
    else:
        message = "If that email is registered and unverified, a new link was sent."
    return ResendVerificationResponse(
        message=message,
        verification_email_sent=outcome.verification_email_sent,
        email_delivery_status=outcome.email_delivery_status,
    )


@router.post("/login")
def login(body: LoginRequest, request: Request) -> dict:
    ip = _client_ip(request)
    email = body.email.strip()
    allowed, retry = check_login_allowed(email=email, ip=ip)
    if not allowed:
        write_auth_audit_event("login_rate_limited", email=email, ip=ip, detail=f"retry={retry}s")
        raise HTTPException(status_code=401, detail={"message": "Invalid email or password.", "code": "login_failed"})

    profile, error, code = login_with_password(email=email, password=body.password)
    if error or profile is None:
        locked, _ = record_login_failure(email=email, ip=ip)
        write_auth_audit_event(
            "login_failed",
            email=email,
            ip=ip,
            detail=f"code={code or 'invalid_credentials'};locked={locked}",
        )
        status = 401
        if code == "banned":
            status = 403
        raise HTTPException(status_code=status, detail={"message": error or "Login failed", "code": code or "login_failed"})

    clear_login_failures(email=email, ip=ip)
    with saas_uow() as uow:
        record = uow.users.get_by_id(uuid.UUID(profile.id))
        if record is None:
            raise HTTPException(status_code=401, detail="Login failed")
        token = issue_access_token_for_record(record)
    write_auth_audit_event("login_success", user_id=profile.id, email=profile.email, ip=ip)
    payload: dict = {"access_token": token, "token_type": "bearer", "user": profile.to_dict()}
    if code == "email_verification_required":
        payload["verification_required"] = True
        payload["message"] = "Please verify your email before logging in."
    return payload


@router.post("/register")
def register(body: RegisterRequest, request: Request) -> RegisterPendingResponse:
    ip = _client_ip(request)
    normalized = body.email.strip().lower()
    with saas_uow() as uow:
        if uow.users.get_by_email(normalized):
            write_auth_audit_event("register_failed", email=normalized, ip=ip, detail="duplicate_email")
            raise HTTPException(status_code=400, detail="Email already registered.")

    allowed, retry = check_register_allowed(ip=ip)
    if not allowed:
        write_auth_audit_event("register_rate_limited", ip=ip, detail=f"retry={retry}s")
        raise HTTPException(status_code=429, detail="Too many registration attempts. Please try again later.")

    profile, error, verification_required, verification_email_sent, email_delivery_status = register_with_password(
        email=body.email,
        password=body.password,
        invite_code=body.invite_code,
    )
    if error or profile is None:
        write_auth_audit_event("register_failed", email=body.email.strip().lower(), ip=ip, detail=error)
        raise HTTPException(status_code=400, detail=error or "Registration failed")
    record_register_attempt(ip=ip)
    write_auth_audit_event(
        "register_success",
        user_id=profile.id,
        email=profile.email,
        ip=ip,
        detail=f"verification_email_sent={verification_email_sent};status={email_delivery_status}",
    )
    return RegisterPendingResponse(
        message=_register_message(
            verification_email_sent=verification_email_sent,
            email_delivery_status=email_delivery_status,
        ),
        email=profile.email or body.email.strip().lower(),
        verification_required=verification_required,
        email_verification_required=verification_required,
        verification_email_sent=verification_email_sent,
        email_delivery_status=email_delivery_status,
    )


@router.get("/verify-email")
def verify_email(request: Request, token: str = Query(..., min_length=16, max_length=512)) -> dict:
    ok, message = verify_email_token(token)
    ip = _client_ip(request)
    if not ok:
        write_auth_audit_event("email_verify_failed", ip=ip, detail="invalid_or_expired")
        raise HTTPException(status_code=400, detail=message)
    write_auth_audit_event("email_verify_success", ip=ip)
    return {"status": "ok", "message": message}


@router.post("/resend-verification", response_model=ResendVerificationResponse)
def resend_verification(body: ResendVerificationRequest, request: Request) -> ResendVerificationResponse:
    return _resend_response(body.email, request)


@router.post("/resend-verification-email", response_model=ResendVerificationResponse)
def resend_verification_email(body: ResendVerificationRequest, request: Request) -> ResendVerificationResponse:
    return _resend_response(body.email, request)


@router.get("/me")
def me(user: WebAuthUser = Depends(get_current_user)) -> dict:
    return {"user": user.to_dict(), "status": "ok"}


@router.post("/logout", response_model=MessageResponse)
def logout(request: Request, authorization: str | None = Header(default=None)) -> MessageResponse:
    token = _extract_bearer(authorization)
    user_id = None
    if token:
        from worldcup_predictor.api.web_auth import resolve_bearer_token

        user = resolve_bearer_token(token)
        if user:
            user_id = user.id
        revoked = revoke_session_token(token)
        write_auth_audit_event(
            "logout",
            user_id=user_id,
            ip=_client_ip(request),
            detail=f"revoked={revoked}",
        )
    else:
        write_auth_audit_event("logout", ip=_client_ip(request), detail="no_token")
    return MessageResponse(message="Logged out")


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(body: ForgotPasswordRequest, request: Request) -> MessageResponse:
    ip = _client_ip(request)
    allowed, retry = check_forgot_password_ip_allowed(ip=ip)
    if not allowed:
        write_auth_audit_event("password_reset_rate_limited", ip=ip, detail=f"retry={retry}s")
        return MessageResponse(message="If that email is registered, password reset instructions were sent.")
    record_forgot_password_ip(ip=ip)
    write_auth_audit_event("password_reset_requested", ip=ip)
    request_password_reset_for_email(body.email.strip().lower())
    return MessageResponse(message="If that email is registered, password reset instructions were sent.")


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(body: ResetPasswordRequest, request: Request) -> MessageResponse:
    ok, message = reset_password_with_token(body.token, body.password)
    if not ok:
        write_auth_audit_event("password_reset_failed", ip=_client_ip(request), detail=message)
        raise HTTPException(status_code=400, detail=message)
    write_auth_audit_event("password_reset_success", ip=_client_ip(request))
    return MessageResponse(message=message)


@router.post("/change-password", response_model=ChangePasswordResponse)
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    user: WebAuthUser = Depends(get_current_user),
) -> ChangePasswordResponse:
    ip = _client_ip(request)
    ok, message, code = change_password_for_user(
        uuid.UUID(user.id),
        current_password=body.current_password,
        new_password=body.new_password,
        confirm_password=body.confirm_password,
    )
    if not ok:
        write_auth_audit_event(
            "password_change_failed",
            user_id=user.id,
            email=user.email,
            ip=ip,
            detail=code,
        )
        status = 400
        if code == "unauthorized":
            status = 401
        raise HTTPException(status_code=status, detail={"message": message, "code": code})

    write_auth_audit_event("password_change_success", user_id=user.id, email=user.email, ip=ip)
    return ChangePasswordResponse()
