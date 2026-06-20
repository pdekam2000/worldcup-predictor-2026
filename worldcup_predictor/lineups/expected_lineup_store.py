"""Expected vs confirmed lineup accuracy history — Phase 22F (trace/benchmark)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_HISTORY_PATH = Path("data/shadow/expected_lineup_accuracy.jsonl")
DEFAULT_MANIFEST_PATH = Path("data/shadow/expected_lineup_manifest.json")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


@dataclass
class ExpectedLineupAccuracyRecord:
    fixture_id: int
    prediction_timestamp: str
    expected_lineup_snapshot: dict[str, Any]
    confirmed_lineup_snapshot: dict[str, Any] | None = None
    comparison_available: bool = False
    player_overlap_pct: float | None = None
    goalkeeper_match: bool | None = None
    formation_match: bool | None = None
    surprise_starters: list[str] = field(default_factory=list)
    missed_expected: list[str] = field(default_factory=list)
    lineup_confidence: float | None = None
    expected_xi_quality: float | None = None
    match_name: str = ""
    phase: str = "22F"

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "prediction_timestamp": self.prediction_timestamp,
            "expected_lineup_snapshot": self.expected_lineup_snapshot,
            "confirmed_lineup_snapshot": self.confirmed_lineup_snapshot,
            "comparison_available": self.comparison_available,
            "player_overlap_pct": self.player_overlap_pct,
            "goalkeeper_match": self.goalkeeper_match,
            "formation_match": self.formation_match,
            "surprise_starters": self.surprise_starters,
            "missed_expected": self.missed_expected,
            "lineup_confidence": self.lineup_confidence,
            "expected_xi_quality": self.expected_xi_quality,
            "match_name": self.match_name,
            "phase": self.phase,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExpectedLineupAccuracyRecord:
        return cls(
            fixture_id=int(data["fixture_id"]),
            prediction_timestamp=str(data["prediction_timestamp"]),
            expected_lineup_snapshot=dict(data.get("expected_lineup_snapshot") or {}),
            confirmed_lineup_snapshot=(
                dict(data["confirmed_lineup_snapshot"])
                if isinstance(data.get("confirmed_lineup_snapshot"), dict)
                else None
            ),
            comparison_available=bool(data.get("comparison_available", False)),
            player_overlap_pct=(
                float(data["player_overlap_pct"])
                if data.get("player_overlap_pct") is not None
                else None
            ),
            goalkeeper_match=(
                bool(data["goalkeeper_match"])
                if data.get("goalkeeper_match") is not None
                else None
            ),
            formation_match=(
                bool(data["formation_match"])
                if data.get("formation_match") is not None
                else None
            ),
            surprise_starters=list(data.get("surprise_starters") or []),
            missed_expected=list(data.get("missed_expected") or []),
            lineup_confidence=(
                float(data["lineup_confidence"])
                if data.get("lineup_confidence") is not None
                else None
            ),
            expected_xi_quality=(
                float(data["expected_xi_quality"])
                if data.get("expected_xi_quality") is not None
                else None
            ),
            match_name=str(data.get("match_name", "")),
            phase=str(data.get("phase", "22F")),
        )


class ExpectedLineupAccuracyStore:
    """Append-only JSONL store — PostgreSQL-compatible JSON shape for future migration."""

    def __init__(
        self,
        path: Path | str = DEFAULT_HISTORY_PATH,
        manifest_path: Path | str = DEFAULT_MANIFEST_PATH,
    ) -> None:
        self._path = Path(path)
        self._manifest_path = Path(manifest_path)

    @property
    def path(self) -> Path:
        return self._path

    def ensure_manifest(self) -> str:
        self._manifest_path.parent.mkdir(parents=True, exist_ok=True)
        if self._manifest_path.exists():
            data = json.loads(self._manifest_path.read_text(encoding="utf-8"))
            return str(data["started_at"])
        started = _utc_now_iso()
        self._manifest_path.write_text(
            json.dumps(
                {
                    "started_at": started,
                    "phase": "22F",
                    "note": "Expected vs confirmed lineup benchmark — trace only",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return started

    def append(self, record: ExpectedLineupAccuracyRecord) -> None:
        self.ensure_manifest()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

    def load_all(self) -> list[ExpectedLineupAccuracyRecord]:
        if not self._path.exists():
            return []
        rows: list[ExpectedLineupAccuracyRecord] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(ExpectedLineupAccuracyRecord.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
        return rows

    def latest_by_fixture(self) -> dict[int, ExpectedLineupAccuracyRecord]:
        latest: dict[int, ExpectedLineupAccuracyRecord] = {}
        for row in self.load_all():
            fid = row.fixture_id
            if fid not in latest or row.prediction_timestamp >= latest[fid].prediction_timestamp:
                latest[fid] = row
        return latest

    def summary_stats(self) -> dict[str, Any]:
        rows = [r for r in self.load_all() if r.comparison_available and r.player_overlap_pct is not None]
        if not rows:
            return {"count": 0, "avg_overlap_pct": None}
        overlaps = [r.player_overlap_pct for r in rows if r.player_overlap_pct is not None]
        return {
            "count": len(rows),
            "avg_overlap_pct": round(sum(overlaps) / len(overlaps), 1) if overlaps else None,
        }
