"""Append-only shadow storage for Rule A harmonization gate (Phase 21A)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_SHADOW_PATH = Path("data/shadow/rule_a_shadow.jsonl")


@dataclass
class RuleAShadowRecord:
    fixture_id: int
    match_name: str
    timestamp: str
    production_prediction: str
    wde_prediction: str
    scoreline_prediction: str
    rule_a_prediction: str
    odds_available: bool
    data_quality_pct: float
    production_scoreline: str = ""
    scoreline_str: str = ""
    rule_a_source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "match_name": self.match_name,
            "timestamp": self.timestamp,
            "production_prediction": self.production_prediction,
            "wde_prediction": self.wde_prediction,
            "scoreline_prediction": self.scoreline_prediction,
            "rule_a_prediction": self.rule_a_prediction,
            "odds_available": self.odds_available,
            "data_quality_pct": self.data_quality_pct,
            "production_scoreline": self.production_scoreline,
            "scoreline_str": self.scoreline_str,
            "rule_a_source": self.rule_a_source,
        }


class RuleAShadowStore:
    def __init__(self, path: Path | str = DEFAULT_SHADOW_PATH) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, record: RuleAShadowRecord) -> None:
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
