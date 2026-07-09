"""Structured audit logging for GPT Actions (no secrets)."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.I),
    re.compile(r"sk-[A-Za-z0-9]{10,}"),
)


def redact_secrets(text: str) -> str:
    out = str(text)
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub("[REDACTED]", out)
    return out


class GptActionsAuditLogger:
    def __init__(self, log_path: str) -> None:
        self._path = Path(log_path)

    def write(
        self,
        *,
        request_id: str,
        route: str,
        method: str,
        status_code: int,
        duration_ms: int,
        job_id: str | None = None,
        error: str | None = None,
    ) -> None:
        record: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "route": route,
            "method": method,
            "status_code": status_code,
            "duration_ms": duration_ms,
            "job_id": job_id,
            "error": redact_secrets(error) if error else None,
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass


def new_request_id() -> str:
    return str(uuid.uuid4())
