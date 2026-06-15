from __future__ import annotations

from datetime import datetime, timezone

from worldcup_predictor.accuracy.models import EvaluatedPrediction, PredictionHistoryRecord
from worldcup_predictor.backtesting.historical_loader import HistoricalMatchRow
from worldcup_predictor.domain.schedule import TournamentFixture
from worldcup_predictor.schedule.match_center import FINISHED_STATUSES, classify_status


def actual_1x2(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "home_win"
    if home_goals < away_goals:
        return "away_win"
    return "draw"


def actual_over_under(home_goals: int, away_goals: int) -> str:
    return "over_2_5" if (home_goals + away_goals) > 2 else "under_2_5"


def _normalize_scoreline(value: str | None) -> str | None:
    if not value:
        return None
    return value.replace(":", "-").strip()


def _first_goal_team_from_scorers(
    goal_scorers: list[str],
    home_team: str,
    away_team: str,
) -> str | None:
    if not goal_scorers:
        return None
    first = goal_scorers[0]
    if "(" not in first or ")" not in first:
        return None
    team_name = first.split("(")[-1].rstrip(")").strip()
    if team_name.lower() == home_team.lower():
        return home_team
    if team_name.lower() == away_team.lower():
        return away_team
    return team_name or None


def is_finished_fixture(fixture: TournamentFixture) -> bool:
    if classify_status(fixture.status) == "finished":
        return True
    return fixture.status.upper() in FINISHED_STATUSES


def evaluate_prediction(
    record: PredictionHistoryRecord,
    fixture: TournamentFixture,
    *,
    evaluated_at: datetime | None = None,
) -> EvaluatedPrediction | None:
    if not is_finished_fixture(fixture):
        return None
    if fixture.home_goals is None or fixture.away_goals is None:
        return None

    home = fixture.home_goals
    away = fixture.away_goals
    actual_x2 = actual_1x2(home, away)
    actual_ou = actual_over_under(home, away)

    predicted_ht_bucket = HistoricalMatchRow.halftime_bucket(record.predicted_halftime_goals)
    actual_ht_bucket: str | None = None
    ht_correct: bool | None = None
    ht_evaluated = (
        fixture.halftime_home_goals is not None and fixture.halftime_away_goals is not None
    )
    if ht_evaluated:
        ht_total = fixture.halftime_home_goals + fixture.halftime_away_goals  # type: ignore[operator]
        actual_ht_bucket = HistoricalMatchRow.halftime_bucket(ht_total)
        ht_correct = predicted_ht_bucket == actual_ht_bucket

    actual_scoreline = f"{home}-{away}"
    predicted_sl = _normalize_scoreline(record.predicted_scoreline)
    scoreline_correct: bool | None = None
    if predicted_sl:
        scoreline_correct = predicted_sl == actual_scoreline

    fg_team = _first_goal_team_from_scorers(fixture.goal_scorers, record.home_team, record.away_team)
    fg_evaluated = fg_team is not None and bool(record.predicted_first_goal_team)
    fg_correct: bool | None = None
    if fg_evaluated:
        fg_correct = record.predicted_first_goal_team.lower() == fg_team.lower()

    stamp = evaluated_at or datetime.now(timezone.utc).replace(tzinfo=None)
    return EvaluatedPrediction(
        fixture_id=record.fixture_id,
        match_name=f"{record.home_team} vs {record.away_team}",
        date=record.date,
        home_team=record.home_team,
        away_team=record.away_team,
        predicted_1x2=record.predicted_1x2,
        actual_1x2=actual_x2,
        one_x_two_correct=record.predicted_1x2 == actual_x2,
        predicted_over_under=record.predicted_over_under_2_5,
        actual_over_under=actual_ou,
        over_under_correct=record.predicted_over_under_2_5 == actual_ou,
        predicted_halftime_bucket=predicted_ht_bucket,
        actual_halftime_bucket=actual_ht_bucket,
        halftime_bucket_correct=ht_correct,
        halftime_evaluated=ht_evaluated,
        predicted_scoreline=predicted_sl,
        actual_scoreline=actual_scoreline,
        scoreline_exact_correct=scoreline_correct,
        predicted_first_goal_team=record.predicted_first_goal_team or None,
        actual_first_goal_team=fg_team,
        first_goal_correct=fg_correct,
        first_goal_evaluated=fg_evaluated,
        first_goal_skipped=not fg_evaluated,
        confidence_score=record.confidence_score,
        no_bet_flag=record.no_bet_flag,
        data_quality_score=record.data_quality_score,
        source=record.source,
        prediction_created_at=record.created_at,
        evaluated_at=stamp.isoformat(),
        final_score=f"{home}-{away}",
    )


def evaluate_all(
    records_by_fixture: dict[int, PredictionHistoryRecord],
    fixtures: list[TournamentFixture],
) -> list[EvaluatedPrediction]:
    fixture_map = {fixture.fixture_id: fixture for fixture in fixtures}
    evaluated: list[EvaluatedPrediction] = []
    for fixture_id, record in records_by_fixture.items():
        fixture = fixture_map.get(fixture_id)
        if fixture is None:
            continue
        result = evaluate_prediction(record, fixture)
        if result is not None:
            evaluated.append(result)
    evaluated.sort(key=lambda item: item.evaluated_at, reverse=True)
    return evaluated
