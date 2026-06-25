"""Contact admin messaging — Phase 38A."""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.notifications.email_delivery import send_email
from worldcup_predictor.notifications.email_templates import contact_admin_notification

logger = logging.getLogger(__name__)

_CONTACT_CATEGORIES = frozenset(
    {"support", "subscription", "billing", "prediction_issue", "feature_request", "other"}
)

_CONTACT_DDL = """
CREATE TABLE IF NOT EXISTS admin_contact_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    user_email TEXT NOT NULL,
    subject TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    email_sent INTEGER NOT NULL DEFAULT 0,
    category TEXT DEFAULT 'other'
)
"""

_RATE_LOCK = threading.Lock()
_rate_buckets: dict[str, list[float]] = {}
MAX_MESSAGES_PER_HOUR = 3
MIN_MESSAGE_INTERVAL_SECONDS = 60


def _audit_path(settings: Settings) -> Path:
    path = Path(getattr(settings, "subscription_audit_log_path", "data/logs/subscription_audit.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_subscription_audit(event: str, *, user_id: str | None = None, detail: str | None = None, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "user_id": user_id,
        "detail": detail,
    }
    try:
        with _audit_path(settings).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("subscription audit write failed: %s", exc)


def _ensure_table(conn) -> None:
    conn.execute(_CONTACT_DDL)
    try:
        conn.execute("ALTER TABLE admin_contact_messages ADD COLUMN category TEXT DEFAULT 'other'")
    except Exception:
        pass
    conn.commit()


def normalize_contact_category(category: str | None) -> str:
    raw = str(category or "other").strip().lower().replace(" ", "_")
    return raw if raw in _CONTACT_CATEGORIES else "other"


def _rate_key(user_id: str, ip: str | None) -> str:
    return f"{user_id}:{ip or 'unknown'}"


def check_contact_rate_limit(user_id: str, ip: str | None = None) -> tuple[bool, int]:
    key = _rate_key(user_id, ip)
    now = time.time()
    with _RATE_LOCK:
        bucket = [t for t in _rate_buckets.get(key, []) if now - t < 3600]
        if bucket and now - bucket[-1] < MIN_MESSAGE_INTERVAL_SECONDS:
            retry = int(MIN_MESSAGE_INTERVAL_SECONDS - (now - bucket[-1]))
            _rate_buckets[key] = bucket
            return False, retry
        if len(bucket) >= MAX_MESSAGES_PER_HOUR:
            retry = int(3600 - (now - bucket[0]))
            _rate_buckets[key] = bucket
            return False, retry
        bucket.append(now)
        _rate_buckets[key] = bucket
        return True, 0


def store_contact_message(
    *,
    user_id: str,
    user_email: str,
    subject: str,
    message: str,
    category: str = "other",
    settings: Settings | None = None,
) -> int:
    settings = settings or get_settings()
    from worldcup_predictor.database.repository import FootballIntelligenceRepository

    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    _ensure_table(repo._conn)
    cat = normalize_contact_category(category)
    cur = repo._conn.execute(
        """
        INSERT INTO admin_contact_messages (user_id, user_email, subject, message, created_at, category)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, user_email, subject, message, datetime.now(timezone.utc).isoformat(), cat),
    )
    repo._conn.commit()
    return int(cur.lastrowid or 0)


def mark_contact_message_sent(message_id: int, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    from worldcup_predictor.database.repository import FootballIntelligenceRepository

    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    _ensure_table(repo._conn)
    repo._conn.execute(
        "UPDATE admin_contact_messages SET email_sent = 1 WHERE id = ?",
        (message_id,),
    )
    repo._conn.commit()


def send_admin_contact_email(
    *,
    user_email: str,
    subject: str,
    message: str,
    category: str = "other",
    settings: Settings | None = None,
) -> bool:
    settings = settings or get_settings()
    admin_to = (settings.admin_contact_email or "").strip()
    if not admin_to:
        logger.info("admin contact email skipped — ADMIN_CONTACT_EMAIL not configured")
        return False

    cat = normalize_contact_category(category)
    subject_line, text, html = contact_admin_notification(
        user_email=user_email,
        subject=subject,
        message=message,
        category=cat,
    )
    result = send_email(
        to_email=admin_to,
        subject=subject_line,
        text_body=text,
        html_body=html,
        reply_to=user_email,
        settings=settings,
        dev_kind="contact_admin",
    )
    return result.delivered


def submit_contact_admin(
    *,
    user_id: str,
    user_email: str,
    subject: str,
    message: str,
    category: str = "other",
    ip: str | None = None,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    ok, retry = check_contact_rate_limit(user_id, ip)
    if not ok:
        write_subscription_audit("contact_admin_rate_limited", user_id=user_id, detail=f"retry={retry}s", settings=settings)
        raise ContactAdminRateLimitError(retry_after_seconds=retry)

    cat = normalize_contact_category(category)
    msg_id = store_contact_message(
        user_id=user_id,
        user_email=user_email,
        subject=subject.strip()[:200],
        message=message.strip()[:4000],
        category=cat,
        settings=settings,
    )
    sent = send_admin_contact_email(
        user_email=user_email,
        subject=subject.strip()[:200],
        message=message.strip()[:4000],
        category=cat,
        settings=settings,
    )
    if sent:
        mark_contact_message_sent(msg_id, settings=settings)
    write_subscription_audit(
        "contact_admin_sent" if sent else "contact_admin_stored",
        user_id=user_id,
        detail=f"message_id={msg_id};category={cat}",
        settings=settings,
    )


class ContactAdminRateLimitError(Exception):
    def __init__(self, *, retry_after_seconds: int = 60) -> None:
        super().__init__("Too many messages. Please try again later.")
        self.retry_after_seconds = retry_after_seconds
