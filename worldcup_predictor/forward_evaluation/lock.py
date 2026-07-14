"""Single-process lock for forward evaluation automation."""

from __future__ import annotations

import json
import os
import socket
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from worldcup_predictor.config.env_loading import project_root

_LOCK_DIR = project_root() / "data" / "evaluation" / "locks"
_DEFAULT_STALE_SECONDS = 7200
SCHEDULER_LOCK_NAME = "forward_evaluation_cycle"


class SchedulerLockActive(RuntimeError):
    """Another forward evaluation cycle holds the global lock."""

    def __init__(self, name: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(f"FORWARD_EVALUATION_CYCLE_ALREADY_RUNNING:{name}")
        self.name = name
        self.detail = detail or {}


def _lock_path(name: str) -> Path:
    return (_LOCK_DIR / f"{name}.lock").resolve()


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _is_stale(path: Path, stale_seconds: int) -> bool:
    if not path.exists():
        return True
    age = time.time() - path.stat().st_mtime
    return age > stale_seconds


def read_lock_metadata(name: str = SCHEDULER_LOCK_NAME) -> dict[str, Any] | None:
    path = _lock_path(name)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"raw": path.read_text(encoding="utf-8", errors="replace")}


@contextmanager
def evaluation_lock(name: str = "forward_automation", *, stale_seconds: int = _DEFAULT_STALE_SECONDS) -> Iterator[dict]:
    _LOCK_DIR.mkdir(parents=True, exist_ok=True)
    path = _lock_path(name)
    if path.exists() and not _is_stale(path, stale_seconds):
        raise RuntimeError(f"lock_active:{name}")
    if path.exists():
        path.unlink(missing_ok=True)
    path.write_text(f"pid={os.getpid()}\nstarted={_utc_now()}\n", encoding="utf-8")
    acquired = {"name": name, "path": str(path), "pid": os.getpid(), "acquired_at": _utc_now()}
    try:
        yield acquired
    finally:
        path.unlink(missing_ok=True)


@contextmanager
def scheduler_cycle_lock(
    *,
    run_id: str,
    dry_run: bool,
    fixture_limit: int,
    lookback_hours: int,
    scope: str | None,
    stale_seconds: int = _DEFAULT_STALE_SECONDS,
) -> Iterator[dict[str, Any]]:
    """Global single-instance lock for forward evaluation scheduler cycles."""
    _LOCK_DIR.mkdir(parents=True, exist_ok=True)
    path = _lock_path(SCHEDULER_LOCK_NAME)
    if path.exists() and not _is_stale(path, stale_seconds):
        meta = read_lock_metadata(SCHEDULER_LOCK_NAME)
        raise SchedulerLockActive(SCHEDULER_LOCK_NAME, meta)
    if path.exists():
        path.unlink(missing_ok=True)
    acquired: dict[str, Any] = {
        "run_id": run_id,
        "started_at": _utc_now(),
        "host": socket.gethostname(),
        "process_id": os.getpid(),
        "mode": "dry_run" if dry_run else "apply",
        "dry_run": dry_run,
        "fixture_limit": fixture_limit,
        "lookback_hours": lookback_hours,
        "scope": scope or "all",
    }
    path.write_text(json.dumps(acquired, indent=2), encoding="utf-8")
    acquired["path"] = str(path)
    try:
        yield acquired
    finally:
        path.unlink(missing_ok=True)
