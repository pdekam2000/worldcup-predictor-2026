"""EGIE domain models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class EgieRawSaveResult:
    saved: bool
    skipped_duplicate: bool
    raw_id: str | None = None
    provider: str = ""
    resource_type: str = ""
    fixture_id: int | None = None


@dataclass
class EgieIngestRunResult:
    job_key: str
    provider: str
    competition_key: str
    season: int
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    api_calls_live: int = 0
    rows_saved: int = 0
    rows_skipped_duplicate: int = 0
    fixtures_processed: int = 0
    errors: list[str] = field(default_factory=list)
    resource_counts: dict[str, int] = field(default_factory=dict)
    run_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["started_at"] = self.started_at.isoformat()
        if self.finished_at:
            payload["finished_at"] = self.finished_at.isoformat()
        return payload
