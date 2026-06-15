from __future__ import annotations

import json
from pathlib import Path

from worldcup_predictor.accuracy.models import PredictionHistoryRecord

DEFAULT_HISTORY_PATH = Path("data/predictions/prediction_history.jsonl")


class PredictionHistoryStore:
    """Append-only JSONL store for pre-match prediction records."""

    def __init__(self, path: Path | str = DEFAULT_HISTORY_PATH) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, record: PredictionHistoryRecord) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record.to_dict(), ensure_ascii=False)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def load_all(self) -> list[PredictionHistoryRecord]:
        if not self._path.exists():
            return []
        records: list[PredictionHistoryRecord] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                records.append(PredictionHistoryRecord.from_dict(json.loads(stripped)))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
        return records

    def latest_by_fixture(self) -> dict[int, PredictionHistoryRecord]:
        latest: dict[int, PredictionHistoryRecord] = {}
        for record in sorted(self.load_all(), key=lambda item: item.created_at):
            latest[record.fixture_id] = record
        return latest

    def records_for_fixture(self, fixture_id: int) -> list[PredictionHistoryRecord]:
        return [record for record in self.load_all() if record.fixture_id == fixture_id]

    def latest_for_fixture(self, fixture_id: int) -> PredictionHistoryRecord | None:
        records = self.records_for_fixture(fixture_id)
        if not records:
            return None
        return max(records, key=lambda item: item.created_at)

    def has_version(self, fixture_id: int, version: str) -> bool:
        return any(record.prediction_version == version for record in self.records_for_fixture(fixture_id))

    def latest_with_version(self, fixture_id: int, version: str) -> PredictionHistoryRecord | None:
        matches = [
            record
            for record in self.records_for_fixture(fixture_id)
            if record.prediction_version == version
        ]
        if not matches:
            return None
        return max(matches, key=lambda item: item.created_at)

    def recent(self, limit: int = 20) -> list[PredictionHistoryRecord]:
        records = self.load_all()
        return list(reversed(records[-limit:]))
