"""Live forward-only validation store for Rule A (Phase 21A-LIVE)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_LIVE_PATH = Path("data/shadow/rule_a_live_validation.jsonl")
DEFAULT_MANIFEST_PATH = Path("data/shadow/rule_a_live_manifest.json")


@dataclass
class LiveValidationRecord:
    fixture_id: int
    prediction_timestamp: str
    production_prediction: str
    wde_prediction: str
    scoreline_prediction: str
    rule_a_prediction: str
    odds_available: bool
    data_quality_pct: float
    actual_result: str | None = None
    settled: bool = False
    match_name: str = ""
    settled_timestamp: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "prediction_timestamp": self.prediction_timestamp,
            "production_prediction": self.production_prediction,
            "wde_prediction": self.wde_prediction,
            "scoreline_prediction": self.scoreline_prediction,
            "rule_a_prediction": self.rule_a_prediction,
            "odds_available": self.odds_available,
            "data_quality_pct": self.data_quality_pct,
            "actual_result": self.actual_result,
            "settled": self.settled,
            "match_name": self.match_name,
            "settled_timestamp": self.settled_timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LiveValidationRecord:
        return cls(
            fixture_id=int(data["fixture_id"]),
            prediction_timestamp=str(data["prediction_timestamp"]),
            production_prediction=str(data["production_prediction"]),
            wde_prediction=str(data["wde_prediction"]),
            scoreline_prediction=str(data["scoreline_prediction"]),
            rule_a_prediction=str(data["rule_a_prediction"]),
            odds_available=bool(data["odds_available"]),
            data_quality_pct=float(data["data_quality_pct"]),
            actual_result=data.get("actual_result"),
            settled=bool(data.get("settled", False)),
            match_name=str(data.get("match_name", "")),
            settled_timestamp=data.get("settled_timestamp"),
        )


class LiveValidationStore:
    def __init__(
        self,
        path: Path | str = DEFAULT_LIVE_PATH,
        manifest_path: Path | str = DEFAULT_MANIFEST_PATH,
    ) -> None:
        self._path = Path(path)
        self._manifest_path = Path(manifest_path)

    @property
    def path(self) -> Path:
        return self._path

    def ensure_manifest(self) -> str:
        """Create manifest with started_at on first live tracking."""
        self._manifest_path.parent.mkdir(parents=True, exist_ok=True)
        if self._manifest_path.exists():
            data = json.loads(self._manifest_path.read_text(encoding="utf-8"))
            return str(data["started_at"])
        started = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        self._manifest_path.write_text(
            json.dumps(
                {
                    "started_at": started,
                    "phase": "21A-LIVE",
                    "note": "Forward-only validation; no historical bootstrap",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return started

    def started_at(self) -> str | None:
        if not self._manifest_path.exists():
            return None
        try:
            return str(json.loads(self._manifest_path.read_text(encoding="utf-8"))["started_at"])
        except (json.JSONDecodeError, KeyError):
            return None

    def append(self, record: LiveValidationRecord) -> None:
        self.ensure_manifest()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

    def load_all(self) -> list[LiveValidationRecord]:
        if not self._path.exists():
            return []
        rows: list[LiveValidationRecord] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(LiveValidationRecord.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
        return rows

    def latest_by_fixture(self) -> dict[int, LiveValidationRecord]:
        latest: dict[int, LiveValidationRecord] = {}
        for row in self.load_all():
            fid = row.fixture_id
            if fid not in latest or row.prediction_timestamp >= latest[fid].prediction_timestamp:
                latest[fid] = row
        return latest

    def write_consolidated(self, records: dict[int, LiveValidationRecord]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            json.dumps(records[fid].to_dict(), ensure_ascii=False)
            for fid in sorted(records)
        ]
        self._path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
