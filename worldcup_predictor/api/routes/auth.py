"""Authentication routes for the independent React frontend."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

from worldcup_predictor.api.deps import get_current_user
from worldcup_predictor.api.web_auth import (
    WebAuthUser,
    issue_access_token,
    login_with_password,
    register_with_password,
    revoke_session_token,
)

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


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict[str, str]


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


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest) -> AuthResponse:
    profile, error = login_with_password(email=body.email, password=body.password)
    if error or profile is None:
        raise HTTPException(status_code=401, detail=error or "Login failed")
    token = issue_access_token(profile)
    return AuthResponse(access_token=token, user=profile.to_dict())


@router.post("/register", response_model=AuthResponse)
def register(body: RegisterRequest) -> AuthResponse:
    profile, error = register_with_password(
        email=body.email,
        password=body.password,
        invite_code=body.invite_code,
    )
    if error or profile is None:
        raise HTTPException(status_code=400, detail=error or "Registration failed")
    token = issue_access_token(profile)
    return AuthResponse(access_token=token, user=profile.to_dict())


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
