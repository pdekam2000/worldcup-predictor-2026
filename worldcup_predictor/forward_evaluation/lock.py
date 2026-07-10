"""Single-process lock for forward evaluation automation."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from worldcup_predictor.config.env_loading import project_root

_LOCK_DIR = project_root() / "data" / "evaluation" / "locks"
_DEFAULT_STALE_SECONDS = 7200


def _lock_path(name: str) -> Path:
    return (_LOCK_DIR / f"{name}.lock").resolve()


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _is_stale(path: Path, stale_seconds: int) -> bool:
    if not path.exists():
        return True
    age = time.time() - path.stat().st_mtime
    return age > stale_seconds


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
