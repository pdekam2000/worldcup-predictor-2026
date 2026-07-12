"""Single-instance process locks for long-running background writers."""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_LOCK_ROOT = Path(os.environ.get("WORLDCUP_LOCK_DIR", "artifacts/locks"))


class ProcessLockError(RuntimeError):
    """Another process holds the lock."""


@contextmanager
def single_instance_lock(name: str, *, blocking: bool = False) -> Iterator[None]:
    """Acquire an exclusive lock file; refuse overlap when blocking=False."""
    _LOCK_ROOT.mkdir(parents=True, exist_ok=True)
    path = _LOCK_ROOT / f"{name}.lock"
    fh = open(path, "a+b")
    try:
        if sys.platform == "win32":
            import msvcrt

            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK if not blocking else msvcrt.LK_LOCK, 1)
            except OSError as exc:
                raise ProcessLockError(f"lock busy: {name}") from exc
        else:
            import fcntl

            flags = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
            try:
                fcntl.flock(fh.fileno(), flags)
            except BlockingIOError as exc:
                raise ProcessLockError(f"lock busy: {name}") from exc
        yield
    finally:
        if sys.platform == "win32":
            import msvcrt

            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        else:
            import fcntl

            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        fh.close()
