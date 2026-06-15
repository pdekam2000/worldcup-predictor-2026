"""JSONL store for per-market verification rows."""

from __future__ import annotations

import json
from pathlib import Path

from worldcup_predictor.verification.models import VerificationMarketRecord

DEFAULT_VERIFICATION_PATH = Path("data/verification/prediction_verification.jsonl")


class VerificationStore:
    def __init__(self, path: Path | str = DEFAULT_VERIFICATION_PATH) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def load_all(self) -> list[VerificationMarketRecord]:
        if not self._path.exists():
            return []
        rows: list[VerificationMarketRecord] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(VerificationMarketRecord.from_dict(json.loads(stripped)))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
        return rows

    def latest_by_key(self) -> dict[tuple[int, str, str], VerificationMarketRecord]:
        latest: dict[tuple[int, str, str], VerificationMarketRecord] = {}
        for row in self.load_all():
            latest[row.dedupe_key()] = row
        return latest

    def upsert(self, record: VerificationMarketRecord) -> bool:
        """Append if new or changed. Returns True when written."""
        existing = self.latest_by_key().get(record.dedupe_key())
        if existing and existing.result == record.result and existing.actual == record.actual:
            return False
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        return True

    def upsert_many(self, records: list[VerificationMarketRecord]) -> int:
        saved = 0
        known = self.latest_by_key()
        for record in records:
            prior = known.get(record.dedupe_key())
            if prior and prior.result == record.result and prior.actual == record.actual:
                continue
            self.upsert(record)
            known[record.dedupe_key()] = record
            saved += 1
        return saved

    def match_summaries(self) -> list[dict]:
        """Group latest market rows by fixture + prediction."""
        grouped: dict[tuple[int, str], list[VerificationMarketRecord]] = {}
        for row in self.latest_by_key().values():
            key = (row.fixture_id, row.prediction_id)
            grouped.setdefault(key, []).append(row)
        summaries = []
        for (_, _), markets in grouped.items():
            markets.sort(key=lambda m: m.market)
            head = markets[0]
            summaries.append(
                {
                    "fixture_id": head.fixture_id,
                    "prediction_id": head.prediction_id,
                    "match_name": head.match_name,
                    "final_score": head.final_score or "—",
                    "markets": markets,
                }
            )
        summaries.sort(key=lambda s: s["markets"][0].verified_at if s["markets"] else "", reverse=True)
        return summaries
