"""Phase 40A/41A — email verification tokens and delivery."""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from worldcup_predictor.access.config import app_public_url
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.saas_factory import saas_uow
from worldcup_predictor.notifications.email_delivery import send_email
from worldcup_predictor.notifications.email_templates import verification_email

logger = logging.getLogger(__name__)

TOKEN_TTL_HOURS = 24
RESEND_MAX_PER_HOUR = 3
RESEND_MIN_INTERVAL_SECONDS = 60

EmailDeliveryStatus = Literal["sent", "email_not_configured", "send_failed"]

_resend_lock = threading.Lock()
_resend_buckets: dict[str, list[float]] = {}

_dev_token_path = Path("data/dev/email_verification_tokens.jsonl")


@dataclass(frozen=True)
class VerificationEmailOutcome:
    verification_email_sent: bool
    email_delivery_status: EmailDeliveryStatus | None


@dataclass(frozen=True)
class ResendVerificationOutcome:
    verification_email_sent: bool
    email_delivery_status: EmailDeliveryStatus | None
    already_verified: bool
    rate_limited: bool
    user_found: bool


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
            "verify_url": f"{app_public_url()}/verify-email?token={raw_token}",
        }
        with _dev_token_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("dev verification token store failed: %s", exc)


def _delivery_status_from_result(result) -> EmailDeliveryStatus:
    if result.delivered:
        return "sent"
    if result.channel == "skipped" or result.error == "email_not_configured":
        return "email_not_configured"
    return "send_failed"


def _send_verification_email(*, to_email: str, raw_token: str, settings: Settings) -> VerificationEmailOutcome:
    verify_url = f"{app_public_url()}/verify-email?token={raw_token}"
    subject, text, html = verification_email(verify_url=verify_url, ttl_hours=TOKEN_TTL_HOURS)
    result = send_email(
        to_email=to_email,
        subject=subject,
        text_body=text,
        html_body=html,
        settings=settings,
        dev_kind="verification",
    )
    status = _delivery_status_from_result(result)
    if result.delivered:
        logger.info("verification email sent to=%s", to_email.strip().lower())
    elif status == "email_not_configured":
        logger.warning("verification email not sent reason=email_not_configured to=%s", to_email.strip().lower())
    else:
        logger.warning("verification email send failed to=%s", to_email.strip().lower())
    if result.channel == "dev_log":
        _store_dev_token(to_email, raw_token, settings)
    return VerificationEmailOutcome(
        verification_email_sent=result.delivered,
        email_delivery_status=status,
    )


def issue_verification_token(
    user_id,
    *,
    email: str,
    settings: Settings | None = None,
) -> tuple[str, VerificationEmailOutcome]:
    """Create a single-use verification token and attempt delivery."""
    settings = settings or get_settings()
    raw = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw)
    expires = datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS)
    with saas_uow() as uow:
        uow.email_verification.invalidate_for_user(user_id)
        uow.email_verification.create(user_id=user_id, token_hash=token_hash, expires_at=expires)
    outcome = _send_verification_email(to_email=email, raw_token=raw, settings=settings)
    return raw, outcome


def verify_email_token(raw_token: str) -> tuple[bool, str]:
    token_hash = _hash_token((raw_token or "").strip())
    if not token_hash or len((raw_token or "").strip()) < 16:
        return False, "Invalid or expired verification link."
    with saas_uow() as uow:
        row = uow.email_verification.get_valid_by_hash(token_hash)
        if row is None:
            return False, "Invalid or expired verification link."
        uow.email_verification.mark_used(row.id)
        updated = uow.users.set_email_verified(row.user_id, True)
        if updated is None:
            return False, "User not found."
    return True, "Email verified successfully."


def check_resend_rate_limit(email: str) -> tuple[bool, int]:
    key = email.strip().lower()
    now = time.time()
    with _resend_lock:
        window = [t for t in _resend_buckets.get(key, []) if now - t < 3600]
        if window and now - window[-1] < RESEND_MIN_INTERVAL_SECONDS:
            return False, int(RESEND_MIN_INTERVAL_SECONDS - (now - window[-1]))
        if len(window) >= RESEND_MAX_PER_HOUR:
            return False, int(3600 - (now - window[0]))
        window.append(now)
        _resend_buckets[key] = window
    return True, 0


def reset_verification_rate_limits() -> None:
    """Clear resend buckets (validation / local dev only)."""
    with _resend_lock:
        _resend_buckets.clear()


def resend_verification_for_email(
    email: str,
    settings: Settings | None = None,
) -> ResendVerificationOutcome:
    """Resend verification email; generic outcome when user not found."""
    settings = settings or get_settings()
    normalized = email.strip().lower()
    if not normalized:
        return ResendVerificationOutcome(
            verification_email_sent=False,
            email_delivery_status=None,
            already_verified=False,
            rate_limited=False,
            user_found=False,
        )
    allowed, _ = check_resend_rate_limit(normalized)
    if not allowed:
        return ResendVerificationOutcome(
            verification_email_sent=False,
            email_delivery_status=None,
            already_verified=False,
            rate_limited=True,
            user_found=True,
        )
    with saas_uow() as uow:
        user = uow.users.get_by_email(normalized)
        if user is None:
            return ResendVerificationOutcome(
                verification_email_sent=False,
                email_delivery_status=None,
                already_verified=False,
                rate_limited=False,
                user_found=False,
            )
        if user.is_banned:
            return ResendVerificationOutcome(
                verification_email_sent=False,
                email_delivery_status=None,
                already_verified=False,
                rate_limited=False,
                user_found=False,
            )
        if user.email_verified:
            return ResendVerificationOutcome(
                verification_email_sent=False,
                email_delivery_status=None,
                already_verified=True,
                rate_limited=False,
                user_found=True,
            )
    _, outcome = issue_verification_token(user.id, email=user.email, settings=settings)
    return ResendVerificationOutcome(
        verification_email_sent=outcome.verification_email_sent,
        email_delivery_status=outcome.email_delivery_status,
        already_verified=False,
        rate_limited=False,
        user_found=True,
    )
