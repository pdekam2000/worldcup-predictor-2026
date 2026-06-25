"""Phase 37A — admin / super-admin access gate, brute-force protection, audit log."""

from __future__ import annotations

import hmac
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import jwt

from worldcup_predictor.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

GateKind = Literal["admin", "super_admin"]
GATE_TOKEN_TTL_MINUTES = 60
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 300

_lock = threading.Lock()
_failed_attempts: dict[str, list[float]] = {}
_lockouts_until: dict[str, float] = {}


@dataclass
class GateAttemptState:
    locked: bool = False
    retry_after_seconds: int = 0
    failures: int = 0


def _audit_path(settings: Settings) -> Path:
    path = Path(getattr(settings, "admin_audit_log_path", "data/logs/admin_audit.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_admin_audit_event(
    event: str,
    *,
    user_id: str | None = None,
    ip: str | None = None,
    detail: str | None = None,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "user_id": user_id,
        "ip": ip,
        "detail": detail,
    }
    try:
        with _audit_path(settings).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("admin audit log write failed: %s", exc)


def _attempt_key(user_id: str, gate: GateKind, ip: str | None) -> str:
    return f"{user_id}:{gate}:{ip or 'unknown'}"


def gate_attempt_state(user_id: str, gate: GateKind, ip: str | None = None) -> GateAttemptState:
    key = _attempt_key(user_id, gate, ip)
    now = time.time()
    with _lock:
        until = _lockouts_until.get(key, 0)
        if until > now:
            return GateAttemptState(locked=True, retry_after_seconds=int(until - now), failures=MAX_FAILED_ATTEMPTS)
        failures = len(_failed_attempts.get(key, []))
        return GateAttemptState(locked=False, retry_after_seconds=0, failures=failures)


def _record_failure(user_id: str, gate: GateKind, ip: str | None) -> GateAttemptState:
    key = _attempt_key(user_id, gate, ip)
    now = time.time()
    with _lock:
        window = [t for t in _failed_attempts.get(key, []) if now - t < LOCKOUT_SECONDS]
        window.append(now)
        _failed_attempts[key] = window
        if len(window) >= MAX_FAILED_ATTEMPTS:
            _lockouts_until[key] = now + LOCKOUT_SECONDS
            return GateAttemptState(locked=True, retry_after_seconds=LOCKOUT_SECONDS, failures=len(window))
        return GateAttemptState(locked=False, retry_after_seconds=0, failures=len(window))


def _clear_failures(user_id: str, gate: GateKind, ip: str | None) -> None:
    key = _attempt_key(user_id, gate, ip)
    with _lock:
        _failed_attempts.pop(key, None)
        _lockouts_until.pop(key, None)


def _expected_key(gate: GateKind, settings: Settings) -> str:
    if gate == "super_admin":
        return (getattr(settings, "super_admin_access_key", "") or "").strip()
    return (getattr(settings, "admin_access_key", "") or "").strip()


def gate_configured(gate: GateKind, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(_expected_key(gate, settings))


def verify_access_key(gate: GateKind, provided: str, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    expected = _expected_key(gate, settings)
    if not expected:
        return False
    supplied = (provided or "").strip()
    if not supplied:
        return False
    return hmac.compare_digest(supplied, expected)


def create_gate_token(*, user_id: str, gate: GateKind, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    secret = (settings.jwt_secret or "").strip()
    if not secret:
        raise ValueError("JWT_SECRET is not configured")
    ttl_minutes = max(5, int(getattr(settings, "admin_gate_ttl_minutes", 60) or 60))
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=ttl_minutes)
    payload = {
        "sub": user_id,
        "type": f"{gate}_gate",
        "gate": gate,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=settings.jwt_algorithm)


def validate_gate_token(token: str | None, *, user_id: str, gate: GateKind, settings: Settings | None = None) -> bool:
    if not token:
        return False
    settings = settings or get_settings()
    if not gate_configured(gate, settings):
        return False
    secret = (settings.jwt_secret or "").strip()
    if not secret:
        return False
    try:
        payload = jwt.decode(token, secret, algorithms=[settings.jwt_algorithm], options={"require": ["exp", "sub", "type"]})
    except jwt.PyJWTError:
        return False
    if payload.get("type") != f"{gate}_gate":
        return False
    if payload.get("gate") != gate:
        return False
    return str(payload.get("sub")) == str(user_id)


def attempt_gate_unlock(
    *,
    user_id: str,
    gate: GateKind,
    access_key: str,
    ip: str | None = None,
    settings: Settings | None = None,
) -> tuple[bool, str, GateAttemptState, str | None]:
    """Return (success, message, attempt_state, gate_token)."""
    settings = settings or get_settings()
    state = gate_attempt_state(user_id, gate, ip)
    if state.locked:
        write_admin_audit_event(
            f"{gate}_gate_failed",
            user_id=user_id,
            ip=ip,
            detail="locked_out",
            settings=settings,
        )
        return False, "Access denied.", state, None

    if not gate_configured(gate, settings):
        write_admin_audit_event(
            f"{gate}_gate_failed",
            user_id=user_id,
            ip=ip,
            detail="gate_not_configured",
            settings=settings,
        )
        return False, "Access denied.", state, None

    if not verify_access_key(gate, access_key, settings):
        state = _record_failure(user_id, gate, ip)
        write_admin_audit_event(
            f"{gate}_gate_failed",
            user_id=user_id,
            ip=ip,
            detail="invalid_key",
            settings=settings,
        )
        return False, "Access denied.", state, None

    _clear_failures(user_id, gate, ip)
    token = create_gate_token(user_id=user_id, gate=gate, settings=settings)
    write_admin_audit_event(
        f"{gate}_gate_success",
        user_id=user_id,
        ip=ip,
        settings=settings,
    )
    return True, "ok", GateAttemptState(locked=False, failures=0), token
