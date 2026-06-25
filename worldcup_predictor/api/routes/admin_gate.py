"""Phase 37A — admin gate verification endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from worldcup_predictor.access.admin_gate import (
    attempt_gate_unlock,
    gate_attempt_state,
    gate_configured,
    validate_gate_token,
)
from worldcup_predictor.api.deps import get_current_user, user_has_admin_access, user_has_super_admin_access
from worldcup_predictor.api.web_auth import WebAuthUser

router = APIRouter(prefix="/admin/gate", tags=["admin-gate"])


class GateVerifyRequest(BaseModel):
    access_key: str = Field(min_length=1, max_length=256)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("/status")
def admin_gate_status(
    request: Request,
    user: WebAuthUser = Depends(get_current_user),
    x_admin_gate_token: str | None = Header(default=None, alias="X-Admin-Gate-Token"),
) -> dict:
    if not user_has_admin_access(user.role):
        raise HTTPException(status_code=403, detail="Access denied.")
    configured = gate_configured("admin")
    passed = configured and validate_gate_token(x_admin_gate_token, user_id=user.id, gate="admin")
    state = gate_attempt_state(user.id, "admin", _client_ip(request))
    return {
        "status": "ok",
        "gate_configured": configured,
        "admin_gate_passed": passed,
        "locked": state.locked,
        "retry_after_seconds": state.retry_after_seconds,
    }


@router.post("/verify")
def verify_admin_gate(
    body: GateVerifyRequest,
    request: Request,
    user: WebAuthUser = Depends(get_current_user),
) -> dict:
    if not user_has_admin_access(user.role):
        raise HTTPException(status_code=403, detail="Access denied.")
    ok, message, state, token = attempt_gate_unlock(
        user_id=user.id,
        gate="admin",
        access_key=body.access_key,
        ip=_client_ip(request),
    )
    if not ok:
        raise HTTPException(
            status_code=403,
            detail={
                "message": message,
                "locked": state.locked,
                "retry_after_seconds": state.retry_after_seconds,
            },
        )
    return {
        "status": "ok",
        "admin_gate_passed": True,
        "gate_token": token,
        "expires_in_minutes": 60,
    }


@router.get("/super-admin/status")
def super_admin_gate_status(
    request: Request,
    user: WebAuthUser = Depends(get_current_user),
    x_super_admin_gate_token: str | None = Header(default=None, alias="X-Super-Admin-Gate-Token"),
) -> dict:
    if not user_has_super_admin_access(user.role):
        raise HTTPException(status_code=403, detail="Access denied.")
    configured = gate_configured("super_admin")
    passed = configured and validate_gate_token(x_super_admin_gate_token, user_id=user.id, gate="super_admin")
    state = gate_attempt_state(user.id, "super_admin", _client_ip(request))
    return {
        "status": "ok",
        "gate_configured": configured,
        "super_admin_gate_passed": passed,
        "locked": state.locked,
        "retry_after_seconds": state.retry_after_seconds,
    }


@router.post("/super-admin/verify")
def verify_super_admin_gate(
    body: GateVerifyRequest,
    request: Request,
    user: WebAuthUser = Depends(get_current_user),
) -> dict:
    if not user_has_super_admin_access(user.role):
        raise HTTPException(status_code=403, detail="Access denied.")
    ok, message, state, token = attempt_gate_unlock(
        user_id=user.id,
        gate="super_admin",
        access_key=body.access_key,
        ip=_client_ip(request),
    )
    if not ok:
        raise HTTPException(
            status_code=403,
            detail={
                "message": message,
                "locked": state.locked,
                "retry_after_seconds": state.retry_after_seconds,
            },
        )
    return {
        "status": "ok",
        "super_admin_gate_passed": True,
        "gate_token": token,
        "expires_in_minutes": 60,
    }
