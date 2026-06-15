"""Persist finished match results for prediction comparison."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from worldcup_predictor.domain.schedule import TournamentFixture
from worldcup_predictor.schedule.match_center import classify_status, actual_result

DEFAULT_RESULTS_PATH = Path("data/results/match_results.jsonl")


@dataclass
class MatchResultRecord:
    fixture_id: int
    home_team: str
    away_team: str
    final_score: str
    halftime_score: str | None
    winner: str
    over_under_2_5_result: str
    total_goals: int
    status: str
    finished_at: str
    source: str
    venue: str | None = None
    kickoff_utc: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> MatchResultRecord:
        return cls(
            fixture_id=int(data["fixture_id"]),
            home_team=str(data["home_team"]),
            away_team=str(data["away_team"]),
            final_score=str(data["final_score"]),
            halftime_score=data.get("halftime_score"),
            winner=str(data["winner"]),
            over_under_2_5_result=str(data["over_under_2_5_result"]),
            total_goals=int(data["total_goals"]),
            status=str(data["status"]),
            finished_at=str(data["finished_at"]),
            source=str(data["source"]),
            venue=data.get("venue"),
            kickoff_utc=data.get("kickoff_utc"),
        )


class MatchResultsStore:
    """Append-only JSONL store for finished match results (deduped by fixture_id)."""

    def __init__(self, path: Path | str = DEFAULT_RESULTS_PATH) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def load_all(self) -> list[MatchResultRecord]:
        if not self._path.exists():
            return []
        rows: list[MatchResultRecord] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(MatchResultRecord.from_dict(json.loads(stripped)))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
        return rows

    def by_fixture_id(self) -> dict[int, MatchResultRecord]:
        latest: dict[int, MatchResultRecord] = {}
        for row in self.load_all():
            latest[row.fixture_id] = row
        return latest

    def upsert(self, record: MatchResultRecord) -> None:
        existing = self.by_fixture_id()
        if record.fixture_id in existing and existing[record.fixture_id].final_score == record.final_score:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

    def upsert_many(self, records: list[MatchResultRecord]) -> int:
        saved = 0
        known = self.by_fixture_id()
        for record in records:
            prior = known.get(record.fixture_id)
            if prior and prior.final_score == record.final_score:
                continue
            self.upsert(record)
            known[record.fixture_id] = record
            saved += 1
        return saved


def fixture_to_result(fixture: TournamentFixture) -> MatchResultRecord | None:
    if classify_status(fixture.status) != "finished":
        return None
    if fixture.home_goals is None or fixture.away_goals is None:
        return None

    home = fixture.home_goals
    away = fixture.away_goals
    total = home + away
    winner = actual_result(home, away) or "draw"
    ou = "over_2_5" if total > 2 else "under_2_5"
    ht = None
    if fixture.halftime_home_goals is not None and fixture.halftime_away_goals is not None:
        ht = f"{fixture.halftime_home_goals}-{fixture.halftime_away_goals}"

    return MatchResultRecord(
        fixture_id=fixture.fixture_id,
        home_team=fixture.home_team,
        away_team=fixture.away_team,
        final_score=f"{home}-{away}",
        halftime_score=ht,
        winner=winner,
        over_under_2_5_result=ou,
        total_goals=total,
        status=fixture.status,
        finished_at=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        source=str(fixture.source),
        venue=fixture.venue,
        kickoff_utc=fixture.kickoff_time.isoformat() if fixture.kickoff_time else None,
    )


def save_finished_fixtures(fixtures: list[TournamentFixture], store: MatchResultsStore | None = None) -> int:
    target = store or MatchResultsStore()
    records = [row for fixture in fixtures if (row := fixture_to_result(fixture)) is not None]
    return target.upsert_many(records)
