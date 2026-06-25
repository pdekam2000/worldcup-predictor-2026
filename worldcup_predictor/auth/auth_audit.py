"""Phase 41B — auth event audit log (no secrets)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from worldcup_predictor.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)


def _audit_path(settings: Settings) -> Path:
    path = Path(settings.auth_audit_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_auth_audit_event(
    event: str,
    *,
    user_id: str | None = None,
    email: str | None = None,
    ip: str | None = None,
    detail: str | None = None,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "user_id": user_id,
        "email": (email or "").strip().lower() or None,
        "ip": ip,
        "detail": detail,
    }
    try:
        with _audit_path(settings).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("auth audit log write failed: %s", exc)
