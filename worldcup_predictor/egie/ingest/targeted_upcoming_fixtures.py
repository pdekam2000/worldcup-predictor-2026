"""EGIE Phase B — sync upcoming Premier League fixtures into SQLite (schedule only)."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.competitions import get_competition
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.egie.guards import ingest_mode
from worldcup_predictor.goal_timing.config import MIN_DATA_QUALITY_FOR_PREDICTION
from worldcup_predictor.goal_timing.prediction_service import GoalTimingPredictionService
from worldcup_predictor.integrations.fixture_api_parser import parse_api_fixture_item

logger = logging.getLogger(__name__)

_UPCOMING_STATUSES = frozenset({"NS", "TBD", "SCHEDULED", "TIMED"})
_FINISHED_STATUSES = frozenset({"FT", "AET", "PEN", "FINISHED", "AWD", "WO"})


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _seasons_to_try(reference: datetime | None = None) -> list[int]:
    """Prefer current/next PL season year(s) for API-Football."""
    ref = reference or _utc_now_naive()
    year = ref.year
    if ref.month >= 6:
        return [year, year - 1]
    return [year - 1, year]


def _is_upcoming_item(item: dict[str, Any], *, now: datetime) -> bool:
    fixture = item.get("fixture") or {}
    status = str((fixture.get("status") or {}).get("short") or "").upper()
    if status not in _UPCOMING_STATUSES:
        return False
    date_raw = fixture.get("date")
    if not date_raw:
        return False
    try:
        kickoff = datetime.fromisoformat(str(date_raw).replace("Z", "+00:00")).astimezone(timezone.utc)
        kickoff = kickoff.replace(tzinfo=None)
    except ValueError:
        return False
    return kickoff > now


def _safe_upsert_upcoming(
    repo: FootballIntelligenceRepository,
    *,
    item: dict[str, Any],
    competition_key: str,
    league_id: int,
    season: int,
) -> str:
    """Insert/update upcoming rows; never overwrite finished fixture rows."""
    fixture = parse_api_fixture_item(item, source="live")
    if fixture is None:
        return "parse_failed"

    existing = repo.get_fixture_row(fixture.fixture_id)
    if existing:
        existing_status = str(existing.get("status") or "").upper()
        if existing_status in _FINISHED_STATUSES:
            return "skipped_finished"

    status = str(fixture.status or "").upper()
    if status not in _UPCOMING_STATUSES:
        return "skipped_not_upcoming"

    repo.upsert_fixture(
        fixture,
        competition_key=competition_key,
        league_id=league_id,
        season=season,
    )
    return "imported" if existing is None else "updated"


def _count_live_call(api_result: Any, api_calls: int, max_api_calls: int) -> int:
    if api_calls >= max_api_calls:
        return api_calls
    if getattr(api_result, "source", None) == "live":
        return api_calls + 1
    return api_calls


def fetch_upcoming_pl_schedule(
    client: ApiFootballClient,
    *,
    seasons: list[int],
    max_api_calls: int,
) -> tuple[list[dict[str, Any]], int, list[dict[str, Any]]]:
    """Return (raw upcoming items, api_calls_used, call_log)."""
    now = _utc_now_naive()
    api_calls = 0
    call_log: list[dict[str, Any]] = []
    collected: dict[int, dict[str, Any]] = {}

    comp = get_competition("premier_league")

    if api_calls < max_api_calls:
        params = {"league": comp.league_id, "next": 100}
        api = client._safe_get("fixtures", params, placeholder_factory=lambda: None)  # noqa: SLF001
        api_calls = _count_live_call(api, api_calls, max_api_calls)
        call_log.append({"endpoint": "fixtures", "params": params, "source": api.source, "count": len(api.data or [])})
        if api.ok and isinstance(api.data, list):
            for item in api.data:
                if _is_upcoming_item(item, now=now):
                    fid = int((item.get("fixture") or {}).get("id") or 0)
                    if fid > 0:
                        collected[fid] = item

    for season in seasons:
        if api_calls >= max_api_calls:
            break
        if collected:
            break
        params = {"league": comp.league_id, "season": season}
        api = client.get_historical_fixtures(league_id=comp.league_id, season=season)
        api_calls = _count_live_call(api, api_calls, max_api_calls)
        call_log.append({"endpoint": "fixtures", "params": params, "source": api.source, "count": len(api.data or [])})
        if api.ok and isinstance(api.data, list):
            for item in api.data:
                if _is_upcoming_item(item, now=now):
                    fid = int((item.get("fixture") or {}).get("id") or 0)
                    if fid > 0:
                        collected[fid] = item

    return list(collected.values()), api_calls, call_log


def _no_pick_reasons(prediction: dict[str, Any], features: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    dq = float(prediction.get("data_quality_score") or 0)
    if dq < MIN_DATA_QUALITY_FOR_PREDICTION:
        reasons.append(f"data_quality_below_threshold ({dq:.4f} < {MIN_DATA_QUALITY_FOR_PREDICTION})")

    manifest = features.get("provider_manifest") or {}
    if not manifest.get("stored_goal_events"):
        reasons.append("missing_stored_goal_events")
    if not manifest.get("stored_fixtures"):
        reasons.append("missing_stored_fixtures")

    history = features.get("history_samples") or {}
    if int(history.get("home_with_goal_minutes") or 0) == 0:
        reasons.append("home_no_goal_minute_history")
    if int(history.get("away_with_goal_minutes") or 0) == 0:
        reasons.append("away_no_goal_minute_history")

    dq_agent = (prediction.get("specialist_agent_breakdown") or {}).get("data_quality") or {}
    for field in dq_agent.get("missing_data") or []:
        reasons.append(f"missing_{field}")

    if prediction.get("no_prediction_flag") and not reasons:
        reasons.append("no_prediction_flag_set")
    return reasons


def _missing_manifest_fields(manifest: dict[str, Any]) -> list[str]:
    return [k for k, v in manifest.items() if not v]


def run_targeted_upcoming_fixture_sync(
    *,
    settings: Settings | None = None,
    max_api_calls: int = 10,
) -> dict[str, Any]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    comp = get_competition("premier_league")

    picks_before = GoalTimingPredictionService(settings).list_today_picks(limit=50)
    upcoming_before = repo.list_upcoming_fixtures("premier_league", limit=100)

    api_calls = 0
    import_stats: Counter[str] = Counter()
    imported_ids: list[int] = []

    if not settings.api_football_configured:
        return {
            "phase": "B",
            "status": "failed",
            "error": "API_FOOTBALL_KEY not configured",
            "api_calls_used": 0,
        }

    client = ApiFootballClient(settings)
    seasons = _seasons_to_try()

    with ingest_mode():
        items, api_calls, call_log = fetch_upcoming_pl_schedule(
            client,
            seasons=seasons,
            max_api_calls=max_api_calls,
        )

        for item in items:
            league = item.get("league") or {}
            try:
                season = int(league.get("season") or seasons[0])
            except (TypeError, ValueError):
                season = seasons[0]
            outcome = _safe_upsert_upcoming(
                repo,
                item=item,
                competition_key=comp.key,
                league_id=comp.league_id,
                season=season,
            )
            import_stats[outcome] += 1
            if outcome in {"imported", "updated"}:
                imported_ids.append(int((item.get("fixture") or {}).get("id")))

    repo.upsert_competition(comp)

    upcoming_after = repo.list_upcoming_fixtures("premier_league", limit=100)
    next_ten = [
        {
            "fixture_id": r.get("fixture_id"),
            "home_team": r.get("home_team"),
            "away_team": r.get("away_team"),
            "kickoff_utc": r.get("kickoff_utc"),
            "status": r.get("status"),
            "season": r.get("season"),
        }
        for r in upcoming_after[:10]
    ]

    picks_service = GoalTimingPredictionService(settings)
    pick_outcomes: list[dict[str, Any]] = []
    dq_scores: list[float] = []
    missing_field_counter: Counter[str] = Counter()
    no_pick_counter: Counter[str] = Counter()

    from worldcup_predictor.goal_timing.features.builder import GoalTimingFeatureBuilder
    from worldcup_predictor.goal_timing.data.stored_adapter import StoredGoalTimingAdapter

    builder = GoalTimingFeatureBuilder(stored=StoredGoalTimingAdapter(settings), max_api_event_fetches=0)

    for row in upcoming_after[:50]:
        fid = int(row["fixture_id"])
        features = builder.build(
            fid,
            competition_key="premier_league",
            context={
                "home_team": row.get("home_team"),
                "away_team": row.get("away_team"),
                "match_date": row.get("kickoff_utc"),
            },
        )
        generated = picks_service.predict_fixture(fid, persist=True, competition_key="premier_league")
        pred = generated.get("prediction") or {}
        dq = float(pred.get("data_quality_score") or 0)
        dq_scores.append(dq)
        manifest = features.get("provider_manifest") or {}
        for mf in _missing_manifest_fields(manifest):
            missing_field_counter[mf] += 1

        published = not bool(pred.get("no_prediction_flag"))
        reasons = _no_pick_reasons(pred, features) if not published else []
        for reason in reasons:
            no_pick_counter[reason] += 1

        pick_outcomes.append(
            {
                "fixture_id": fid,
                "home_team": row.get("home_team"),
                "away_team": row.get("away_team"),
                "kickoff_utc": row.get("kickoff_utc"),
                "published": published,
                "data_quality_score": dq,
                "no_prediction_flag": bool(pred.get("no_prediction_flag")),
                "no_pick_reasons": reasons,
            }
        )

    picks_after = picks_service.list_today_picks(limit=50)
    published_count = sum(1 for p in pick_outcomes if p["published"])
    no_pick_count = len(pick_outcomes) - published_count
    avg_dq = round(sum(dq_scores) / len(dq_scores), 4) if dq_scores else 0.0

    finished_preserved = import_stats.get("skipped_finished", 0)
    goal_events_before = repo._conn.execute("SELECT COUNT(*) FROM fixture_goal_events").fetchone()[0]
    goal_events_after = goal_events_before

    return {
        "phase": "B",
        "status": "completed",
        "competition_key": comp.key,
        "seasons_tried": seasons,
        "api_calls_used": api_calls,
        "api_calls_cap": max_api_calls,
        "api_call_log": call_log,
        "upcoming_fixtures_before": len(upcoming_before),
        "upcoming_fixtures_after": len(upcoming_after),
        "upcoming_fixtures_imported": len(imported_ids),
        "import_outcomes": dict(import_stats),
        "imported_fixture_ids": sorted(imported_ids),
        "finished_rows_preserved": finished_preserved,
        "goal_event_rows_unchanged": goal_events_before == goal_events_after,
        "goal_event_row_count": goal_events_after,
        "next_10_upcoming": next_ten,
        "picks_api_count_before": picks_before.get("count", 0),
        "picks_api_count_after": picks_after.get("count", 0),
        "picks_published": published_count,
        "picks_no_pick": no_pick_count,
        "average_data_quality": avg_dq,
        "common_missing_fields": missing_field_counter.most_common(10),
        "no_pick_reason_counts": no_pick_counter.most_common(),
        "pick_outcomes": pick_outcomes,
        "picks_after": picks_after.get("picks", []),
    }
