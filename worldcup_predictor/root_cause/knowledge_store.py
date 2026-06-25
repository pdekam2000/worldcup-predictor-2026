"""Part E — root cause knowledge store."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.root_cause.config import STORE_DIR
from worldcup_predictor.root_cause.models import KnowledgeRecord


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RootCauseStore:
    """Shadow knowledge store — no production writes."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or STORE_DIR

    def ensure_dirs(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def records_path(self) -> Path:
        return self.base_dir / "knowledge_records.jsonl"

    def append_record(self, record: KnowledgeRecord) -> None:
        self.ensure_dirs()
        payload = {"generated_at": _utc_now(), **record.to_dict()}
        with self.records_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, default=str) + "\n")

    def write_snapshot(self, name: str, payload: dict[str, Any]) -> Path:
        self.ensure_dirs()
        path = self.base_dir / f"{name}.json"
        path.write_text(json.dumps({"generated_at": _utc_now(), **payload}, indent=2, default=str), encoding="utf-8")
        return path

    def save_artifacts(
        self,
        *,
        comparisons_summary: dict[str, Any],
        blame_matrix: dict[str, Any],
        pattern_summary: dict[str, Any],
        failure_breakdown: dict[str, Any],
        priority_actions: list[dict[str, Any]],
    ) -> dict[str, str]:
        self.ensure_dirs()
        paths = {
            "comparisons": self.write_snapshot("comparisons_summary", comparisons_summary),
            "blame_matrix": self.write_snapshot("component_blame_matrix", blame_matrix),
            "patterns": self.write_snapshot("failure_patterns", pattern_summary),
            "failure_breakdown": self.write_snapshot("failure_breakdown", failure_breakdown),
            "priority_actions": self.write_snapshot("priority_actions", {"actions": priority_actions}),
        }
        return {k: str(v) for k, v in paths.items()}
