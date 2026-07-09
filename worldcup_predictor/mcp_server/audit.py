"""Structured MCP audit logging with secret redaction."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(api[_-]?key|token|password|secret|authorization)\s*[:=]\s*['\"]?([^\s'\",}]+)", re.I),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.I),
    re.compile(r"sk-[A-Za-z0-9]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----"),
)

_REDACTED = "[REDACTED]"


def redact_secrets(text: str) -> str:
    out = str(text)
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub(_REDACTED, out)
    return out


def sanitize_error(exc: BaseException | str | None) -> str:
    if exc is None:
        return ""
    return redact_secrets(str(exc))[:500]


class AuditLogger:
  def __init__(self, log_path: str) -> None:
      self._path = Path(log_path)

  def write(
      self,
      *,
      tool_name: str,
      caller_mode: str,
      duration_ms: int,
      success: bool,
      fixture_count: int | None = None,
      result_status: str | None = None,
      error: str | None = None,
      request_id: str | None = None,
  ) -> None:
      record: dict[str, Any] = {
          "timestamp": datetime.now(timezone.utc).isoformat(),
          "request_id": request_id or str(uuid.uuid4()),
          "tool_name": tool_name,
          "caller_mode": caller_mode,
          "duration_ms": duration_ms,
          "success": success,
          "fixture_count": fixture_count,
          "result_status": result_status,
          "error": redact_secrets(error) if error else None,
      }
      try:
          self._path.parent.mkdir(parents=True, exist_ok=True)
          with self._path.open("a", encoding="utf-8") as handle:
              handle.write(json.dumps(record, ensure_ascii=False) + "\n")
      except OSError:
          # Audit must never break tool execution.
          pass
