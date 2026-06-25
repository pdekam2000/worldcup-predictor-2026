"""Phase 39B-2 — billing audit events (no secrets)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from worldcup_predictor.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)


def write_billing_audit_event(
    event: str,
    *,
    user_id: str | None = None,
    detail: str | None = None,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    path = Path(settings.subscription_audit_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "user_id": user_id,
        "detail": detail,
    }
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("billing audit write failed: %s", exc)
