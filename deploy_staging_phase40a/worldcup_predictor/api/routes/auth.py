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
from worldcup_predictor.auth.email_verification import resend_verification_for_email, verify_email_token
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


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class RegisterPendingResponse(BaseModel):
    status: str = "ok"
    message: str
    email: str
    verification_required: bool = True


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


@router.post("/login")
def login(body: LoginRequest) -> dict:
    profile, error, code = login_with_password(email=body.email, password=body.password)
    if error or profile is None:
        status = 401
        if code == "banned":
            status = 403
        raise HTTPException(status_code=status, detail={"message": error or "Login failed", "code": code})
    with saas_uow() as uow:
        record = uow.users.get_by_id(uuid.UUID(profile.id))
        if record is None:
            raise HTTPException(status_code=401, detail="Login failed")
        token = issue_access_token_for_record(record)
    payload: dict = {"access_token": token, "token_type": "bearer", "user": profile.to_dict()}
    if code == "email_verification_required":
        payload["verification_required"] = True
        payload["message"] = "Please verify your email to unlock predictions."
    return payload


@router.post("/register")
def register(body: RegisterRequest) -> RegisterPendingResponse:
    profile, error, verification_required = register_with_password(
        email=body.email,
        password=body.password,
        invite_code=body.invite_code,
    )
    if error or profile is None:
        raise HTTPException(status_code=400, detail=error or "Registration failed")
    return RegisterPendingResponse(
        message="Please verify your email. Check your inbox for a verification link.",
        email=profile.email or body.email.strip().lower(),
        verification_required=verification_required,
    )


@router.get("/verify-email")
def verify_email(token: str = Query(..., min_length=16, max_length=512)) -> dict:
    ok, message = verify_email_token(token)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {"status": "ok", "message": message}


@router.post("/resend-verification", response_model=MessageResponse)
def resend_verification(body: ResendVerificationRequest) -> MessageResponse:
    resend_verification_for_email(body.email.strip().lower())
    return MessageResponse(message="If that email is registered and unverified, a new link was sent.")


@router.get("/me")
def me(user: WebAuthUser = Depends(get_current_user)) -> dict:
    return {"user": user.to_dict(), "status": "ok"}


@router.post("/logout", response_model=MessageResponse)
def logout(authorization: str | None = Header(default=None)) -> MessageResponse:
    token = _extract_bearer(authorization)
    if token:
        revoke_session_token(token)
    return MessageResponse(message="Logged out")


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password() -> MessageResponse:
    return MessageResponse(
        message="Password reset is not enabled yet. Contact the administrator.",
    )
