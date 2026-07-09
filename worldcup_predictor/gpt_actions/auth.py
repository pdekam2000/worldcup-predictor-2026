"""API key authentication for GPT Actions (header only, constant-time)."""

from __future__ import annotations

import hmac
import secrets
from typing import Any

from fastapi import HTTPException, Request

from worldcup_predictor.gpt_actions.config import GptActionsConfig


class AuthError(Exception):
    pass


def verify_api_key(config: GptActionsConfig, authorization: str | None) -> None:
    expected = config.api_key
    if not expected:
        raise AuthError("GPT_ACTIONS_API_KEY not configured")
    if not authorization:
        raise AuthError("missing Authorization header")
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        raise AuthError("Authorization must use Bearer scheme")
    provided = authorization[len(prefix) :].strip()
    if not provided:
        raise AuthError("empty bearer token")
    if not hmac.compare_digest(provided, expected):
        raise AuthError("invalid API key")


async def require_gpt_actions_auth(request: Request) -> None:
    config: GptActionsConfig = request.app.state.gpt_actions_config
    try:
        verify_api_key(config, request.headers.get("Authorization"))
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    if request.query_params.get("api_key") or request.query_params.get("token"):
        raise HTTPException(status_code=400, detail="API key in query string is not allowed")
