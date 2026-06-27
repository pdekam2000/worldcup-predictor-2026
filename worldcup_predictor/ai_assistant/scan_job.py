"""Production alert scan job — Phase A19B (lock, logging, overlap guard)."""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from worldcup_predictor.ai_assistant.scheduler import run_alert_scan

logger = logging.getLogger(__name__)

DEFAULT_LOCK_PATH = Path(
    os.getenv("ASSISTANT_ALERT_SCAN_LOCK", "/run/worldcup/assistant-alert-scan.lock")
)


class _ScanLock:
    """Non-blocking exclusive lock; skipped on platforms without fcntl."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._handle = None
        self._acquired = False

    def acquire(self) -> bool:
        try:
            import fcntl
        except ImportError:
            return True

        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = open(self._path, "w", encoding="utf-8")
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._handle.write(str(os.getpid()))
            self._handle.flush()
            self._acquired = True
            return True
        except OSError:
            return False

    def release(self) -> None:
        if not self._handle or not self._acquired:
            return
        try:
            import fcntl

            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        except (ImportError, OSError):
            pass
        try:
            self._handle.close()
        except OSError:
            pass
        self._acquired = False


def run_alert_scan_job(
    *,
    user_id: str | None = None,
    lock_path: Path | None = None,
) -> dict[str, Any]:
    started = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    lock = _ScanLock(lock_path or DEFAULT_LOCK_PATH)
    if not lock.acquire():
        logger.warning("assistant alert scan skipped: overlapping run in progress")
        return {
            "status": "skipped",
            "reason": "overlap",
            "started_at": started,
            "finished_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        }

    logger.info("assistant alert scan started user_id=%s", user_id or "all")
    try:
        result = run_alert_scan(user_id=user_id)
        result["started_at"] = started
        result["finished_at"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        logger.info(
            "assistant alert scan finished users=%s notifications=%s",
            result.get("users_scanned"),
            result.get("notifications_created"),
        )
        return result
    except Exception as exc:
        logger.exception("assistant alert scan failed")
        return {
            "status": "error",
            "message": str(exc),
            "started_at": started,
            "finished_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        }
    finally:
        lock.release()


def run_assistant_alert_scan_command(
    *,
    user_id: str | None = None,
    stream: TextIO | None = None,
) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [assistant-alert-scan] %(message)s",
        stream=sys.stderr,
    )
    out = stream or sys.stdout
    result = run_alert_scan_job(user_id=user_id)
    out.write("Phase A19B — AI Assistant alert scan\n")
    out.write(f"  Status: {result.get('status')}\n")
    if result.get("reason"):
        out.write(f"  Reason: {result.get('reason')}\n")
    out.write(f"  Users scanned: {result.get('users_scanned', 0)}\n")
    out.write(f"  Notifications created: {result.get('notifications_created', 0)}\n")
    if result.get("started_at"):
        out.write(f"  Started: {result.get('started_at')}\n")
    if result.get("finished_at"):
        out.write(f"  Finished: {result.get('finished_at')}\n")
    if result.get("message"):
        out.write(f"  Error: {result.get('message')}\n")
    status = result.get("status")
    if status == "error":
        return 1
    return 0
