"""Migrate JSONL backup stores into SQLite primary database."""

from __future__ import annotations

from dataclasses import dataclass

from worldcup_predictor.accuracy.history_store import PredictionHistoryStore
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.results.match_results_store import MatchResultsStore
from worldcup_predictor.verification.store import VerificationStore


def _ensure_fixture_stub(repo: FootballIntelligenceRepository, record, competition_key: str) -> None:
    from datetime import datetime

    from worldcup_predictor.domain.schedule import TournamentFixture

    kickoff = datetime.utcnow()
    try:
        kickoff = datetime.fromisoformat(record.date)
    except ValueError:
        pass
    fixture = TournamentFixture(
        fixture_id=record.fixture_id,
        kickoff_time=kickoff,
        home_team=record.home_team,
        away_team=record.away_team,
        venue="",
        city="",
        country="",
        group="",
        round="",
        status="FT" if record.source == "live" else "NS",
        is_placeholder=False,
        source="live",  # type: ignore[arg-type]
    )
    repo.upsert_fixture(fixture, competition_key=competition_key)


@dataclass
class MigrationResult:
    predictions_imported: int = 0
    results_imported: int = 0
    verifications_imported: int = 0
    errors: list[str] | None = None

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


def migrate_jsonl_to_db(
    *,
    competition_key: str = "world_cup_2026",
    repository: FootballIntelligenceRepository | None = None,
) -> MigrationResult:
    repo = repository or FootballIntelligenceRepository()
    repo.seed_competitions()
    result = MigrationResult()

    for record in PredictionHistoryStore().load_all():
        try:
            _ensure_fixture_stub(repo, record, competition_key)
            repo.upsert_prediction(
                prediction_id=record.prediction_id,
                fixture_id=record.fixture_id,
                competition_key=competition_key,
                home_team=record.home_team,
                away_team=record.away_team,
                prediction_version=record.prediction_version,
                created_at=record.created_at,
                data_quality=record.data_quality_score,
                prediction_quality=record.data_quality_score,
                confidence=record.confidence_score,
                no_bet_flag=record.no_bet_flag,
                source=record.source,
                lineups_available=record.lineups_available,
                is_preliminary=record.is_preliminary,
                markets={
                    "1x2": record.predicted_1x2,
                    "over_under_2_5": record.predicted_over_under_2_5,
                    "halftime_goals": str(record.predicted_halftime_goals),
                    "first_goal_team": record.predicted_first_goal_team,
                    "scoreline_exact": record.predicted_scoreline or "",
                },
            )
            result.predictions_imported += 1
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"prediction {record.prediction_id}: {exc}")

    for row in MatchResultsStore().load_all():
        try:
            from worldcup_predictor.domain.schedule import TournamentFixture
            from datetime import datetime

            kickoff = datetime.fromisoformat(row.kickoff_utc) if row.kickoff_utc else datetime.utcnow()
            parts = row.final_score.split("-")
            home_g = int(parts[0]) if len(parts) == 2 else None
            away_g = int(parts[1]) if len(parts) == 2 else None
            ht_h, ht_a = None, None
            if row.halftime_score and "-" in row.halftime_score:
                ht_parts = row.halftime_score.split("-")
                ht_h, ht_a = int(ht_parts[0]), int(ht_parts[1])
            fixture = TournamentFixture(
                fixture_id=row.fixture_id,
                kickoff_time=kickoff,
                home_team=row.home_team,
                away_team=row.away_team,
                venue=row.venue or "",
                city="",
                country="",
                group="",
                round="",
                status=row.status,
                is_placeholder=False,
                source="live",  # type: ignore[arg-type]
                home_goals=home_g,
                away_goals=away_g,
                halftime_home_goals=ht_h,
                halftime_away_goals=ht_a,
            )
            repo.upsert_fixture(fixture, competition_key=competition_key)
            if repo.upsert_fixture_result(fixture, competition_key=competition_key):
                result.results_imported += 1
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"result {row.fixture_id}: {exc}")

    for row in VerificationStore().load_all():
        try:
            comp = competition_key
            from worldcup_predictor.domain.schedule import TournamentFixture
            from datetime import datetime

            stub = TournamentFixture(
                fixture_id=row.fixture_id,
                kickoff_time=datetime.utcnow(),
                home_team=row.home_team,
                away_team=row.away_team,
                venue="",
                city="",
                country="",
                group="",
                round="",
                status="FT",
                is_placeholder=False,
                source="live",  # type: ignore[arg-type]
            )
            repo.upsert_fixture(stub, competition_key=comp)
            repo.upsert_verification(
                fixture_id=row.fixture_id,
                prediction_id=row.prediction_id,
                competition_key=comp,
                market=row.market,
                predicted=row.predicted,
                actual=row.actual,
                result=row.result,
                color=row.color,
                verified_at=row.verified_at,
            )
            result.verifications_imported += 1
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"verification {row.fixture_id}/{row.market}: {exc}")

    return result
