"""Shared SMTP email delivery with HTML + text multipart."""

from __future__ import annotations

import json
import logging
import smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from worldcup_predictor.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

_dev_delivery_log = Path("data/dev/email_delivery_log.jsonl")


@dataclass(frozen=True)
class EmailSendResult:
    delivered: bool
    channel: str  # smtp | dev_log | skipped
    error: str | None = None


def smtp_configured(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(
        (settings.smtp_host or "").strip()
        and (settings.smtp_from or settings.smtp_user or "").strip()
    )


def admin_contact_email_configured(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool((settings.admin_contact_email or "").strip())


def _from_address(settings: Settings) -> str:
    return (settings.smtp_from or settings.smtp_user or "noreply@worldcup-predictor.local").strip()


def _log_dev_delivery(
    *,
    to_email: str,
    subject: str,
    text_body: str,
    settings: Settings,
    kind: str,
) -> None:
    if settings.is_production:
        return
    try:
        _dev_delivery_log.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "to": to_email.strip().lower(),
            "subject": subject,
            "preview": text_body[:500],
        }
        with _dev_delivery_log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("dev email delivery log failed: %s", exc)


def send_email(
    *,
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
    reply_to: str | None = None,
    settings: Settings | None = None,
    dev_kind: str = "transactional",
) -> EmailSendResult:
    """Send multipart email via SMTP; dev fallback logs metadata without secrets."""
    settings = settings or get_settings()
    to = to_email.strip()
    if not to:
        return EmailSendResult(delivered=False, channel="skipped", error="missing_recipient")

    if not smtp_configured(settings):
        if settings.is_production:
            logger.warning("email send skipped kind=%s reason=smtp_not_configured", dev_kind)
            return EmailSendResult(delivered=False, channel="skipped", error="email_not_configured")
        _log_dev_delivery(to_email=to, subject=subject, text_body=text_body, settings=settings, kind=dev_kind)
        return EmailSendResult(delivered=False, channel="dev_log", error="email_not_configured")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = _from_address(settings)
    msg["To"] = to
    if reply_to:
        msg["Reply-To"] = reply_to.strip()
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            user = (settings.smtp_user or "").strip()
            password = (settings.smtp_password or "").strip()
            if user and password:
                smtp.login(user, password)
            smtp.send_message(msg)
        return EmailSendResult(delivered=True, channel="smtp")
    except Exception as exc:
        logger.warning("email send failed kind=%s: %s", dev_kind, exc)
        if not settings.is_production:
            _log_dev_delivery(to_email=to, subject=subject, text_body=text_body, settings=settings, kind=dev_kind)
        return EmailSendResult(delivered=False, channel="smtp", error="send_failed")
