"""Production pipeline file lock."""

from __future__ import annotations

import os
from pathlib import Path


class ProductionPipelineLock:
    """Non-blocking exclusive lock for pipeline runs."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._handle = None
        self._acquired = False

    @property
    def acquired(self) -> bool:
        return self._acquired

    def acquire(self) -> bool:
        try:
            import fcntl
        except ImportError:
            self._acquired = True
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
            if self._handle:
                try:
                    self._handle.close()
                except OSError:
                    pass
                self._handle = None
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
        self._handle = None
        self._acquired = False
