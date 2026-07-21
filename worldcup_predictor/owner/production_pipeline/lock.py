"""Production pipeline file lock (service-user safe, wait-on-busy)."""

from __future__ import annotations

import os
import time
from pathlib import Path


class ProductionPipelineLock:
    """Exclusive lock for pipeline runs.

    - Creates the lock file if missing with mode 0664
    - Falls back to a user-writable sidecar if the canonical path is root-owned
    - Supports blocking wait so 'busy' is not a permanent failure
    """

    def __init__(self, path: Path) -> None:
        self._requested_path = Path(path)
        self._path = self._requested_path
        self._handle = None
        self._acquired = False

    @property
    def acquired(self) -> bool:
        return self._acquired

    @property
    def path(self) -> Path:
        return self._path

    def _resolve_writable_path(self) -> Path:
        primary = self._requested_path
        primary.parent.mkdir(parents=True, exist_ok=True)
        if not primary.exists():
            try:
                fd = os.open(str(primary), os.O_CREAT | os.O_RDWR, 0o664)
                os.close(fd)
            except OSError:
                pass
        # Prefer primary when writable
        if os.access(primary.parent, os.W_OK):
            try:
                with open(primary, "a+", encoding="utf-8"):
                    return primary
            except OSError:
                pass
        # Sidecar for www-data when root left an unwritable lock file
        sidecar = primary.with_name(primary.name + f".u{os.getuid()}")
        try:
            fd = os.open(str(sidecar), os.O_CREAT | os.O_RDWR, 0o664)
            os.close(fd)
        except OSError:
            pass
        return sidecar

    def acquire(self, *, wait_sec: float = 0.0, poll_sec: float = 2.0) -> bool:
        """Acquire exclusive lock. If wait_sec>0, retry until timeout."""
        try:
            import fcntl
        except ImportError:
            self._acquired = True
            return True

        deadline = time.monotonic() + max(0.0, float(wait_sec))
        self._path = self._resolve_writable_path()

        while True:
            try:
                self._handle = open(self._path, "a+", encoding="utf-8")
                flags = fcntl.LOCK_EX | fcntl.LOCK_NB
                fcntl.flock(self._handle.fileno(), flags)
                self._handle.seek(0)
                self._handle.truncate()
                self._handle.write(str(os.getpid()))
                self._handle.flush()
                self._acquired = True
                return True
            except OSError:
                if self._handle:
                    try:
                        self._handle.close()
                    except OSError:
                        pass
                    self._handle = None
                if time.monotonic() >= deadline:
                    return False
                time.sleep(max(0.2, float(poll_sec)))

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
        self._handle = None
        self._acquired = False
