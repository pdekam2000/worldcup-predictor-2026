"""Append-only shadow storage for odds-primary engine (Phase 16)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path("data/shadow/odds_primary_shadow.jsonl")


@dataclass
class OddsPrimaryShadowRecord:
    fixture_id: int
    match_name: str
    timestamp: str
    config_version: str
    production_prediction: str
    shadow_prediction: str
    production_lambda_home: float
    production_lambda_away: float
    shadow_lambda_home: float
    shadow_lambda_away: float
    production_scoreline: str
    shadow_scoreline: str
    actual_result: str | None
    production_correct: bool | None
    shadow_correct: bool | None
    lambda_source: str
    odds_available: bool
    shadow_meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "match_name": self.match_name,
            "timestamp": self.timestamp,
            "config_version": self.config_version,
            "production_prediction": self.production_prediction,
            "shadow_prediction": self.shadow_prediction,
            "production_lambda_home": self.production_lambda_home,
            "production_lambda_away": self.production_lambda_away,
            "shadow_lambda_home": self.shadow_lambda_home,
            "shadow_lambda_away": self.shadow_lambda_away,
            "production_scoreline": self.production_scoreline,
            "shadow_scoreline": self.shadow_scoreline,
            "actual_result": self.actual_result,
            "production_correct": self.production_correct,
            "shadow_correct": self.shadow_correct,
            "lambda_source": self.lambda_source,
            "odds_available": self.odds_available,
            "shadow_meta": self.shadow_meta,
        }


class OddsPrimaryShadowStore:
    def __init__(self, path: Path | str = DEFAULT_PATH) -> None:
        self._path = Path(path)

    def append(self, record: OddsPrimaryShadowRecord) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

    def load_all(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows
