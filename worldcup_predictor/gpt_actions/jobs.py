"""Async prediction job store (file-based, no DB schema changes)."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

JobStatus = Literal["queued", "running", "completed", "partial", "failed"]

_JOB_LOCK = threading.Lock()
_ACTIVE_JOB_ID: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


class JobStore:
    def __init__(self, root_dir: str, *, max_retained: int = 50) -> None:
        self._root = Path(root_dir)
        self._root.mkdir(parents=True, exist_ok=True)
        self._max_retained = max_retained
        self._idempotency: dict[str, str] = {}

    def _path(self, job_id: str) -> Path:
        return self._root / f"{job_id}.json"

    def get_by_idempotency_key(self, key: str) -> dict[str, Any] | None:
        job_id = self._idempotency.get(key)
        if not job_id:
            return None
        return self.get(job_id)

    def create(
        self,
        *,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        global _ACTIVE_JOB_ID
        with _JOB_LOCK:
            if idempotency_key and idempotency_key in self._idempotency:
                existing_id = self._idempotency[idempotency_key]
                existing = self.get(existing_id)
                if existing:
                    return existing

            if _ACTIVE_JOB_ID:
                active = self.get(_ACTIVE_JOB_ID)
                if active and active.get("status") in ("queued", "running"):
                    raise RuntimeError("job_concurrency_limit")

            job_id = str(uuid.uuid4())
            record = {
                "job_id": job_id,
                "status": "queued",
                "created_at": _utc_now(),
                "updated_at": _utc_now(),
                "idempotency_key": idempotency_key,
                "request": payload,
                "result": None,
                "error": None,
            }
            self._path(job_id).write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            if idempotency_key:
                self._idempotency[idempotency_key] = job_id
            _ACTIVE_JOB_ID = job_id
            self._prune()
            return record

    def get(self, job_id: str) -> dict[str, Any] | None:
        path = self._path(job_id)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def update(self, job_id: str, **fields: Any) -> dict[str, Any] | None:
        record = self.get(job_id)
        if not record:
            return None
        record.update(fields)
        record["updated_at"] = _utc_now()
        self._path(job_id).write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        return record

    def release_active(self, job_id: str) -> None:
        global _ACTIVE_JOB_ID
        with _JOB_LOCK:
            if _ACTIVE_JOB_ID == job_id:
                _ACTIVE_JOB_ID = None

    def _prune(self) -> None:
        files = sorted(self._root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for stale in files[self._max_retained :]:
            try:
                stale.unlink()
            except OSError:
                pass
