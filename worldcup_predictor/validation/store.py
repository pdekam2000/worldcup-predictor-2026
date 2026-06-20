"""Phase 26 — persistent real-world validation storage."""

from __future__ import annotations

import json
from pathlib import Path

from worldcup_predictor.validation.models import PromotionContributionStats, RealWorldValidationRecord

DEFAULT_VALIDATION_PATH = Path("data/validation/real_world_validation.jsonl")
DEFAULT_STATS_PATH = Path("data/validation/promotion_contribution_stats.json")


class RealWorldValidationStore:
    """Append-only JSONL store for pre-match captures and post-match outcomes."""

    def __init__(self, path: Path | str = DEFAULT_VALIDATION_PATH) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def _ensure_file_path(self) -> None:
        if self._path.exists() and self._path.is_dir():
            raise IsADirectoryError(f"Validation path is a directory, not a file: {self._path}")
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: RealWorldValidationRecord) -> None:
        self._ensure_file_path()
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

    def load_all(self) -> list[RealWorldValidationRecord]:
        if not self._path.exists():
            return []
        rows: list[RealWorldValidationRecord] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(RealWorldValidationRecord.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
        return rows

    def latest_by_fixture(self) -> dict[int, RealWorldValidationRecord]:
        latest: dict[int, RealWorldValidationRecord] = {}
        for row in sorted(self.load_all(), key=lambda r: r.prediction_timestamp):
            latest[row.fixture_id] = row
        return latest

    def unsettled(self) -> list[RealWorldValidationRecord]:
        return [r for r in self.load_all() if not r.settled]

    def rewrite_all(self, records: list[RealWorldValidationRecord]) -> None:
        self._ensure_file_path()
        with self._path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")


class PromotionContributionStore:
    """Long-term promotion contribution statistics."""

    def __init__(self, path: Path | str = DEFAULT_STATS_PATH) -> None:
        self._path = Path(path)

    def _ensure_file_path(self) -> None:
        if self._path.exists() and self._path.is_dir():
            raise IsADirectoryError(f"Stats path is a directory, not a file: {self._path}")
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, PromotionContributionStats]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        out: dict[str, PromotionContributionStats] = {}
        for key, block in (raw or {}).items():
            if isinstance(block, dict):
                out[key] = PromotionContributionStats(**block)
        return out

    def save(self, stats: dict[str, PromotionContributionStats]) -> None:
        self._ensure_file_path()
        payload = {k: v.to_dict() for k, v in stats.items()}
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
