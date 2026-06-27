"""Phase 40A — email verification tokens and delivery."""

from __future__ import annotations

import hashlib
import logging
import secrets
import smtplib
import threading
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

from worldcup_predictor.access.config import app_public_url
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.saas_factory import saas_uow

logger = logging.getLogger(__name__)

TOKEN_TTL_HOURS = 24
RESEND_MAX_PER_HOUR = 3
RESEND_MIN_INTERVAL_SECONDS = 60

_resend_lock = threading.Lock()
_resend_buckets: dict[str, list[float]] = {}

# Dev-only store when SMTP is not configured (never log raw tokens in production).
_dev_token_path = Path("data/dev/email_verification_tokens.jsonl")


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _smtp_configured(settings: Settings) -> bool:
    return bool((settings.smtp_host or "").strip() and (settings.smtp_from or settings.smtp_user or "").strip())


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
        import json

        with _dev_token_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("dev verification token store failed: %s", exc)


def _send_verification_email(*, to_email: str, raw_token: str, settings: Settings) -> bool:
    if not _smtp_configured(settings):
        _store_dev_token(to_email, raw_token, settings)
        return False
    verify_url = f"{app_public_url()}/verify-email?token={raw_token}"
    msg = EmailMessage()
    msg["Subject"] = "Verify your WorldCup Predictor account"
    msg["From"] = (settings.smtp_from or settings.smtp_user or "").strip()
    msg["To"] = to_email
    msg.set_content(
        "Please verify your email address to activate prediction access.\n\n"
        f"Verification link (expires in {TOKEN_TTL_HOURS} hours):\n{verify_url}\n\n"
        "If you did not create this account, you can ignore this email."
    )
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            user = (settings.smtp_user or "").strip()
            password = (settings.smtp_password or "").strip()
            if user and password:
                smtp.login(user, password)
            smtp.send_message(msg)
        return True
    except Exception as exc:
        logger.warning("verification email send failed: %s", exc)
        _store_dev_token(to_email, raw_token, settings)
        return False


def issue_verification_token(user_id, *, email: str, settings: Settings | None = None) -> str:
    """Create a single-use verification token and optionally send email."""
    settings = settings or get_settings()
    raw = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw)
    expires = datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS)
    with saas_uow() as uow:
        uow.email_verification.invalidate_for_user(user_id)
        uow.email_verification.create(user_id=user_id, token_hash=token_hash, expires_at=expires)
    _send_verification_email(to_email=email, raw_token=raw, settings=settings)
    return raw


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


def resend_verification_for_email(email: str, settings: Settings | None = None) -> None:
    """Always returns silently — do not reveal whether email exists."""
    settings = settings or get_settings()
    normalized = email.strip().lower()
    if not normalized:
        return
    allowed, _ = check_resend_rate_limit(normalized)
    if not allowed:
        return
    with saas_uow() as uow:
        user = uow.users.get_by_email(normalized)
        if user is None or user.email_verified or user.is_banned:
            return
        issue_verification_token(user.id, email=user.email, settings=settings)
