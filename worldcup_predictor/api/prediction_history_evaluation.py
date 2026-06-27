"""Evaluate user prediction history rows against finished match results — Phase 29."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from worldcup_predictor.config.competitions import DEFAULT_COMPETITION_KEY, get_competition
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.postgres.enums import Prediction1x2, PredictionResult
from worldcup_predictor.database.postgres.schemas import PredictionHistoryRecord
from worldcup_predictor.quota.prediction_cache import get_cached_prediction
from worldcup_predictor.quota.prediction_cache_policy import specialist_agent_count
from worldcup_predictor.results.match_results_store import MatchResultsStore
from worldcup_predictor.schedule.match_center import FINISHED_STATUSES, actual_result

ResultStatus = Literal["correct", "wrong", "partial", "pending", "unknown"]

_ACTUAL_TO_PICK: dict[str, Prediction1x2] = {
    "home_win": Prediction1x2.HOME,
    "draw": Prediction1x2.DRAW,
    "away_win": Prediction1x2.AWAY,
}

_PICK_LABEL: dict[Prediction1x2, str] = {
    Prediction1x2.HOME: "home",
    Prediction1x2.DRAW: "draw",
    Prediction1x2.AWAY: "away",
}


@dataclass(frozen=True)
class FixtureOutcome:
    is_finished: bool
    actual_result: str | None
    final_score: str | None
    evaluated_at: str | None
    fixture_status: str | None
    ht_score: str | None = None
    ht_result: str | None = None
    ht_home_goals: int | None = None
    ht_away_goals: int | None = None
    first_goal_team: str | None = None
    first_goal_player: str | None = None
    first_goal_minute: int | None = None
    first_goal_extra_minute: int | None = None
    match_outcome_type: str | None = None
    goal_events: tuple[dict[str, Any], ...] = ()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _parse_score_pair(final_score: str | None) -> tuple[int | None, int | None]:
    if not final_score or "-" not in final_score:
        return None, None
    left, _, right = final_score.partition("-")
    try:
        return int(left.strip()), int(right.strip())
    except ValueError:
        return None, None


def _outcome_from_goals(
    *,
    home_goals: int | None,
    away_goals: int | None,
    final_score: str | None,
    status: str | None,
    finished_at: str | None,
    is_finished: bool,
    result_row: dict[str, Any] | None = None,
    goal_events: list[dict[str, Any]] | None = None,
) -> FixtureOutcome:
    extended = _extended_outcome_fields(result_row, goal_events)
    if not is_finished:
        return FixtureOutcome(
            is_finished=False,
            actual_result=None,
            final_score=None,
            evaluated_at=None,
            fixture_status=status,
            **extended,
        )

    if home_goals is None or away_goals is None:
        home_goals, away_goals = _parse_score_pair(final_score)

    actual = actual_result(home_goals, away_goals)
    score_text = final_score
    if score_text is None and home_goals is not None and away_goals is not None:
        score_text = f"{home_goals}-{away_goals}"

    if actual is None:
        return FixtureOutcome(
            is_finished=True,
            actual_result=None,
            final_score=score_text,
            evaluated_at=finished_at or _utc_now_iso(),
            fixture_status=status,
            **extended,
        )

    return FixtureOutcome(
        is_finished=True,
        actual_result=actual,
        final_score=score_text,
        evaluated_at=finished_at or _utc_now_iso(),
        fixture_status=status,
        **extended,
    )


def _extended_outcome_fields(
    result_row: dict[str, Any] | None,
    goal_events: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    if not result_row:
        events_tuple = tuple(goal_events or ())
        return {
            "ht_score": None,
            "ht_result": None,
            "ht_home_goals": None,
            "ht_away_goals": None,
            "first_goal_team": None,
            "first_goal_player": None,
            "first_goal_minute": None,
            "first_goal_extra_minute": None,
            "match_outcome_type": None,
            "goal_events": events_tuple,
        }
    ht_home = result_row.get("ht_home_goals")
    ht_away = result_row.get("ht_away_goals")
    ht_score = result_row.get("halftime_score")
    if ht_score is None and ht_home is not None and ht_away is not None:
        ht_score = f"{ht_home}-{ht_away}"
    events_tuple = tuple(goal_events if goal_events is not None else [])
    return {
        "ht_score": ht_score,
        "ht_result": result_row.get("ht_result"),
        "ht_home_goals": ht_home,
        "ht_away_goals": ht_away,
        "first_goal_team": result_row.get("first_goal_team"),
        "first_goal_player": result_row.get("first_goal_player"),
        "first_goal_minute": result_row.get("first_goal_minute"),
        "first_goal_extra_minute": result_row.get("first_goal_extra_minute"),
        "match_outcome_type": result_row.get("match_outcome_type"),
        "goal_events": events_tuple,
    }


class FixtureOutcomeResolver:
    """Resolve fixture outcomes from SQLite, JSONL results, and schedule cache."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._jsonl = MatchResultsStore().by_fixture_id()
        self._sqlite_cache: dict[int, FixtureOutcome | None] = {}

    def resolve(self, fixture_id: int) -> FixtureOutcome:
        cached = self._sqlite_cache.get(fixture_id)
        if cached is not None:
            return cached

        outcome = self._resolve_once(fixture_id)
        self._sqlite_cache[fixture_id] = outcome
        return outcome

    def _resolve_once(self, fixture_id: int) -> FixtureOutcome:
        jsonl_row = self._jsonl.get(fixture_id)
        if jsonl_row is not None:
            status = (jsonl_row.status or "FT").upper()
            is_finished = status in FINISHED_STATUSES or classify_finished(jsonl_row.winner)
            home_g, away_g = _parse_score_pair(jsonl_row.final_score)
            return _outcome_from_goals(
                home_goals=home_g,
                away_goals=away_g,
                final_score=jsonl_row.final_score,
                status=status,
                finished_at=jsonl_row.finished_at,
                is_finished=is_finished,
            )

        try:
            from worldcup_predictor.database.repository import FootballIntelligenceRepository

            repo = FootballIntelligenceRepository(self._settings.sqlite_path or None)
            fixture_row = repo.get_fixture_row(fixture_id)
            result_row = repo.get_fixture_result_row(fixture_id)
        except Exception:
            fixture_row = None
            result_row = None

        status = str((fixture_row or {}).get("status") or "NS").upper()
        is_finished = status in FINISHED_STATUSES

        if result_row:
            goal_events = repo.list_fixture_goal_events(fixture_id)
            return _outcome_from_goals(
                home_goals=result_row.get("home_goals"),
                away_goals=result_row.get("away_goals"),
                final_score=result_row.get("final_score"),
                status=status,
                finished_at=result_row.get("finished_at"),
                is_finished=True,
                result_row=result_row,
                goal_events=goal_events,
            )

        return _outcome_from_goals(
            home_goals=None,
            away_goals=None,
            final_score=None,
            status=status,
            finished_at=None,
            is_finished=is_finished,
        )


def classify_finished(winner: str | None) -> bool:
    return bool(winner and winner not in {"unknown", "pending", ""})


def evaluate_result_status(
    predicted: Prediction1x2,
    outcome: FixtureOutcome,
) -> tuple[ResultStatus, bool | None]:
    if not outcome.is_finished:
        return "pending", None
    if outcome.actual_result is None:
        return "unknown", None

    expected_pick = _ACTUAL_TO_PICK.get(outcome.actual_result)
    if expected_pick is None:
        return "unknown", None

    is_correct = predicted == expected_pick
    return ("correct" if is_correct else "wrong"), is_correct


def _legacy_result(status: ResultStatus) -> PredictionResult:
    if status == "correct":
        return PredictionResult.CORRECT
    if status == "wrong":
        return PredictionResult.INCORRECT
    return PredictionResult.PENDING


def _cache_metadata(fixture_id: int, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    try:
        comp = get_competition(DEFAULT_COMPETITION_KEY)
        cached = get_cached_prediction(
            fixture_id,
            competition_key=comp.key,
            season=comp.season,
            locale="en",
            settings=settings,
        )
    except Exception:
        cached = None

    if not cached:
        return {
            "data_quality": None,
            "agent_count": None,
            "cache_schema_version": None,
            "predicted_market_keys": [],
        }

    from worldcup_predictor.api.global_prediction_archive import predicted_market_keys_from_payload

    return {
        "data_quality": cached.get("data_quality"),
        "agent_count": cached.get("specialist_agent_count") or specialist_agent_count(cached),
        "cache_schema_version": cached.get("cache_schema_version"),
        "predicted_market_keys": predicted_market_keys_from_payload(cached),
    }


def evaluate_history_record(
    record: PredictionHistoryRecord,
    *,
    resolver: FixtureOutcomeResolver | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Build Phase 29 evaluated history payload for one user history row."""
    settings = settings or get_settings()
    resolver = resolver or FixtureOutcomeResolver(settings=settings)
    outcome = resolver.resolve(record.fixture_id)
    result_status, is_correct = evaluate_result_status(record.prediction_1x2, outcome)
    cache_meta = _cache_metadata(record.fixture_id, settings=settings)
    predicted = _PICK_LABEL.get(record.prediction_1x2, str(record.prediction_1x2.value))

    return {
        "id": str(record.id),
        "fixture_id": record.fixture_id,
        "prediction_id": record.prediction_id,
        "match_date": record.match_date.isoformat() if record.match_date else None,
        "home_team": record.home_team,
        "away_team": record.away_team,
        "league": record.league,
        "predicted_1x2": predicted,
        "predicted_confidence": float(record.confidence) if record.confidence is not None else None,
        "prediction_1x2": predicted,
        "confidence": float(record.confidence) if record.confidence is not None else None,
        "actual_result": outcome.actual_result,
        "final_score": outcome.final_score,
        "is_finished": outcome.is_finished,
        "is_correct": is_correct,
        "evaluated_at": outcome.evaluated_at,
        "result_status": result_status,
        "result": _legacy_result(result_status).value,
        "viewed_at": record.viewed_at.isoformat() if record.viewed_at else None,
        **cache_meta,
    }


def filter_by_result_status(items: list[dict[str, Any]], status_filter: str) -> list[dict[str, Any]]:
    normalized = (status_filter or "all").strip().lower()
    if normalized in {"", "all"}:
        return items
    if normalized == "incorrect":
        normalized = "wrong"
    if normalized == "evaluated":
        return [item for item in items if item.get("result_status") in ("correct", "wrong", "partial")]
    return [item for item in items if item.get("result_status") == normalized]
