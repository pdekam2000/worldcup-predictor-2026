"""Append-only shadow storage for lambda bridge (Phase 12B)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_SHADOW_PATH = Path("data/shadow/lambda_bridge_shadow.jsonl")


@dataclass
class ShadowRecord:
    fixture_id: int
    match_name: str
    timestamp: str
    mode: str
    config_version: str
    production_prediction: str
    shadow_prediction: str
    production_lambda_home: float
    production_lambda_away: float
    shadow_lambda_home: float
    shadow_lambda_away: float
    production_scoreline: str
    shadow_scoreline: str
    wde_selection: str
    bridge_contributors: list[dict[str, Any]] = field(default_factory=list)
    conflict_status: dict[str, Any] = field(default_factory=dict)
    global_cap_applied: bool = False
    data_quality_scale: float = 1.0
    data_quality_pct: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "match_name": self.match_name,
            "timestamp": self.timestamp,
            "mode": self.mode,
            "config_version": self.config_version,
            "production_prediction": self.production_prediction,
            "shadow_prediction": self.shadow_prediction,
            "production_lambda_home": self.production_lambda_home,
            "production_lambda_away": self.production_lambda_away,
            "shadow_lambda_home": self.shadow_lambda_home,
            "shadow_lambda_away": self.shadow_lambda_away,
            "production_scoreline": self.production_scoreline,
            "shadow_scoreline": self.shadow_scoreline,
            "wde_selection": self.wde_selection,
            "bridge_contributors": self.bridge_contributors,
            "conflict_status": self.conflict_status,
            "global_cap_applied": self.global_cap_applied,
            "data_quality_scale": self.data_quality_scale,
            "data_quality_pct": self.data_quality_pct,
        }


class ShadowStore:
    def __init__(self, path: Path | str = DEFAULT_SHADOW_PATH) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, record: ShadowRecord) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record.to_dict(), ensure_ascii=False)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def load_all(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError:
                continue
        return rows
