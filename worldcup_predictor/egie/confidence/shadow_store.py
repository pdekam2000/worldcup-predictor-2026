"""Persist hybrid confidence shadow predictions (file-based, no production DB)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.egie.confidence.config import HYBRID_SHADOW_PREDICTIONS_PATH


class HybridConfidenceShadowStore:
    """Append-only JSONL store for hybrid confidence shadow outputs."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or HYBRID_SHADOW_PREDICTIONS_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: dict[str, Any]) -> None:
        row = {**record, "recorded_at": datetime.now(timezone.utc).isoformat()}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")

    def write_all(self, records: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as fh:
            for rec in records:
                row = {**rec, "recorded_at": datetime.now(timezone.utc).isoformat()}
                fh.write(json.dumps(row, default=str) + "\n")

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        out: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
        return out
