"""Phase 41A — password reset tokens and delivery."""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from worldcup_predictor.access.config import app_public_url
from worldcup_predictor.auth.passwords import hash_password
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.saas_factory import saas_uow
from worldcup_predictor.notifications.email_delivery import send_email
from worldcup_predictor.notifications.email_templates import password_reset_email

logger = logging.getLogger(__name__)

TOKEN_TTL_HOURS = 1
REQUEST_MAX_PER_HOUR = 3
REQUEST_MIN_INTERVAL_SECONDS = 60

_request_lock = threading.Lock()
_request_buckets: dict[str, list[float]] = {}

_dev_token_path = Path("data/dev/password_reset_tokens.jsonl")


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _store_dev_token(email: str, raw_token: str, settings: Settings) -> None:
    if settings.is_production:
        return
    try:
        _dev_token_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "email": email.strip().lower(),
            "reset_url": f"{app_public_url()}/reset-password?token={raw_token}",
        }
        with _dev_token_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("dev password reset token store failed: %s", exc)


def _send_reset_email(*, to_email: str, raw_token: str, settings: Settings) -> None:
    reset_url = f"{app_public_url()}/reset-password?token={raw_token}"
    subject, text, html = password_reset_email(reset_url=reset_url, ttl_hours=TOKEN_TTL_HOURS)
    result = send_email(
        to_email=to_email,
        subject=subject,
        text_body=text,
        html_body=html,
        settings=settings,
        dev_kind="password_reset",
    )
    if result.channel == "dev_log":
        _store_dev_token(to_email, raw_token, settings)


def check_reset_rate_limit(email: str) -> tuple[bool, int]:
    key = email.strip().lower()
    now = time.time()
    with _request_lock:
        window = [t for t in _request_buckets.get(key, []) if now - t < 3600]
        if window and now - window[-1] < REQUEST_MIN_INTERVAL_SECONDS:
            return False, int(REQUEST_MIN_INTERVAL_SECONDS - (now - window[-1]))
        if len(window) >= REQUEST_MAX_PER_HOUR:
            return False, int(3600 - (now - window[0]))
        window.append(now)
        _request_buckets[key] = window
    return True, 0


def issue_password_reset_token(user_id, *, email: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    raw = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw)
    expires = datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS)
    with saas_uow() as uow:
        uow.password_reset.invalidate_for_user(user_id)
        uow.password_reset.create(user_id=user_id, token_hash=token_hash, expires_at=expires)
    _send_reset_email(to_email=email, raw_token=raw, settings=settings)
    return raw


def request_password_reset_for_email(email: str, settings: Settings | None = None) -> None:
    """Always returns silently — do not reveal whether email exists."""
    settings = settings or get_settings()
    normalized = email.strip().lower()
    if not normalized:
        return
    allowed, _ = check_reset_rate_limit(normalized)
    if not allowed:
        return
    with saas_uow() as uow:
        user = uow.users.get_by_email(normalized)
        if user is None or user.is_banned:
            return
        issue_password_reset_token(user.id, email=user.email, settings=settings)


def reset_password_with_token(raw_token: str, new_password: str) -> tuple[bool, str]:
    token_hash = _hash_token((raw_token or "").strip())
    if not token_hash or len((raw_token or "").strip()) < 16:
        return False, "Invalid or expired reset link."
    if len(new_password or "") < 8:
        return False, "Password must be at least 8 characters."
    with saas_uow() as uow:
        row = uow.password_reset.get_valid_by_hash(token_hash)
        if row is None:
            return False, "Invalid or expired reset link."
        uow.password_reset.mark_used(row.id)
        user = uow.users.get_by_id(row.user_id)
        if user is None:
            return False, "User not found."
        uow.users.update_password_hash(row.user_id, hash_password(new_password))
        uow.users.bump_token_version(row.user_id)
    from worldcup_predictor.auth.auth_audit import write_auth_audit_event

    write_auth_audit_event("password_reset_success", user_id=str(row.user_id))
    return True, "Password updated successfully."
