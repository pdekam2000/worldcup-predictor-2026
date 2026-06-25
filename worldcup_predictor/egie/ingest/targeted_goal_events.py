"""EGIE Phase A — targeted Premier League goal-event ingest (events only, quota-safe)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.competitions import get_competition
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.egie.config import PREMIER_LEAGUE_API_FOOTBALL_JOB, PROVIDER_API_FOOTBALL
from worldcup_predictor.egie.guards import ingest_mode
from worldcup_predictor.egie.models import EgieIngestRunResult
from worldcup_predictor.egie.storage.repository import EgieRawStoreRepository

logger = logging.getLogger(__name__)

_PROBE_FIXTURE_ID = 1035553
_FINISHED = ("FT", "AET", "PEN", "FINISHED", "AWD", "WO")


def _egie_event_fixture_ids(settings: Settings) -> set[int]:
    from worldcup_predictor.database.postgres.session import postgres_configured, session_scope

    if not postgres_configured(settings):
        return set()
    with session_scope(settings) as session:
        rows = session.execute(
            text(
                """
                SELECT DISTINCT fixture_id
                FROM egie_provider_raw_responses
                WHERE provider = :provider AND resource_type = 'events'
                  AND fixture_id IS NOT NULL
                """
            ),
            {"provider": PROVIDER_API_FOOTBALL},
        ).fetchall()
    return {int(r[0]) for r in rows if r[0]}


def _sqlite_fixtures_with_events(repo: FootballIntelligenceRepository) -> set[int]:
    conn = repo._conn
    rows = conn.execute(
        "SELECT DISTINCT fixture_id FROM fixture_goal_events WHERE fixture_id IS NOT NULL"
    ).fetchall()
    return {int(r[0]) for r in rows}


def build_target_fixture_ids(
    repo: FootballIntelligenceRepository,
    *,
    probe_fixture_id: int = _PROBE_FIXTURE_ID,
    max_targets: int = 80,
    history_before_kickoff: str = "2024-05-19T15:00:00",
) -> list[int]:
    """Priority: probe fixture, SHU/TOT histories, then recent PL finished matches."""
    ordered: list[int] = []
    seen: set[int] = set()

    def add(fid: int) -> None:
        if fid <= 0 or fid in seen:
            return
        seen.add(fid)
        ordered.append(fid)

    add(int(probe_fixture_id))
    for team in ("Sheffield Utd", "Tottenham"):
        rows = repo.list_team_finished_fixtures_before(
            team_name=team,
            before_kickoff=history_before_kickoff,
            competition_keys=["premier_league"],
            limit=40,
        )
        for row in rows:
            add(int(row["fixture_id"]))
            if len(ordered) >= max_targets:
                return ordered[:max_targets]

    ph = ",".join("?" * len(_FINISHED))
    recent = repo._conn.execute(
        f"""
        SELECT fixture_id FROM fixtures
        WHERE competition_key = 'premier_league' AND is_placeholder = 0
          AND status IN ({ph})
        ORDER BY kickoff_utc DESC
        LIMIT 60
        """,
        _FINISHED,
    ).fetchall()
    for row in recent:
        add(int(row[0]))
        if len(ordered) >= max_targets:
            break
    return ordered[:max_targets]


def coverage_snapshot(repo: FootballIntelligenceRepository) -> dict[str, Any]:
    ph = ",".join("?" * len(_FINISHED))
    finished = repo._conn.execute(
        f"""
        SELECT COUNT(*) FROM fixtures
        WHERE competition_key='premier_league' AND is_placeholder=0 AND status IN ({ph})
        """,
        _FINISHED,
    ).fetchone()[0]
    with_events = repo._conn.execute(
        f"""
        SELECT COUNT(DISTINCT f.fixture_id) FROM fixtures f
        JOIN fixture_goal_events g ON g.fixture_id = f.fixture_id
        WHERE f.competition_key='premier_league' AND f.is_placeholder=0
          AND f.status IN ({ph})
        """,
        _FINISHED,
    ).fetchone()[0]
    finished = int(finished or 0)
    with_events = int(with_events or 0)
    return {
        "finished_pl_fixtures": finished,
        "finished_with_goal_events": with_events,
        "goal_event_coverage_pct": round(100 * with_events / finished, 2) if finished else 0.0,
        "total_goal_event_rows": int(
            repo._conn.execute("SELECT COUNT(*) FROM fixture_goal_events").fetchone()[0] or 0
        ),
    }


def run_targeted_goal_event_ingest(
    *,
    fixture_ids: list[int] | None = None,
    max_api_calls: int = 80,
    probe_fixture_id: int = _PROBE_FIXTURE_ID,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    store = EgieRawStoreRepository(settings)
    client = ApiFootballClient(settings)
    comp = get_competition("premier_league")
    season = int(comp.season) if comp else 2024

    targets = fixture_ids or build_target_fixture_ids(repo, probe_fixture_id=probe_fixture_id)
    egie_has = _egie_event_fixture_ids(settings)
    sqlite_has = _sqlite_fixtures_with_events(repo)

    before_coverage = coverage_snapshot(repo)
    before_probe = _probe_prediction(repo, settings, probe_fixture_id)

    result = EgieIngestRunResult(
        job_key="api_football_premier_league_targeted_events",
        provider=PROVIDER_API_FOOTBALL,
        competition_key="premier_league",
        season=season,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    result.run_id = store.start_ingest_run(
        job_key=result.job_key,
        provider=result.provider,
        competition_key=result.competition_key,
        season=season,
        config={
            "target_fixture_ids": targets,
            "max_api_calls": max_api_calls,
            "resource_types": ["events"],
            "phase": "A",
        },
    )

    api_calls_live = 0
    fixtures_enriched: list[int] = []
    events_imported = 0
    skipped_egie = 0
    skipped_api_cap = 0
    mirrored_only = 0

    with ingest_mode():
        for fid in targets:
            row = repo.get_fixture_row(fid)
            if not row:
                result.errors.append(f"fixture_not_in_sqlite:{fid}")
                continue

            home = str(row.get("home_team") or "")
            away = str(row.get("away_team") or "")

            if fid in egie_has:
                skipped_egie += 1
            elif api_calls_live >= max_api_calls:
                skipped_api_cap += 1
                continue
            else:
                api = client.get_fixture_events(int(fid))
                if getattr(api, "source", None) == "live":
                    api_calls_live += 1
                if api.data is not None:
                    envelope = {
                        "endpoint": "fixtures/events",
                        "params": {"fixture": fid},
                        "response": api.data,
                        "source": api.source,
                        "error": api.error,
                    }
                    save = store.save_raw_response(
                        provider=PROVIDER_API_FOOTBALL,
                        resource_type="events",
                        request_endpoint="fixtures/events",
                        request_params={"fixture": int(fid)},
                        payload_json=envelope,
                        source=str(api.source),
                        competition_key="premier_league",
                        league_id=comp.league_id if comp else 39,
                        season=season,
                        fixture_id=int(fid),
                    )
                    if save.saved or save.skipped_duplicate:
                        egie_has.add(fid)
                        result.resource_counts["events"] = result.resource_counts.get("events", 0) + 1
                        if save.saved:
                            result.rows_saved += 1
                        else:
                            result.rows_skipped_duplicate += 1

            if fid not in sqlite_has:
                from worldcup_predictor.goal_timing.data.api_football_fallback import (
                    ApiFootballGoalTimingFallback,
                )

                fallback = ApiFootballGoalTimingFallback(settings)
                events, source = fallback.ensure_goal_events(
                    int(fid),
                    home_team=home,
                    away_team=away,
                    competition_key="premier_league",
                    persist=True,
                )
                if events:
                    sqlite_has.add(fid)
                    events_imported += len(events)
                    fixtures_enriched.append(fid)
                    if fid in egie_has and source == "egie_postgres":
                        mirrored_only += 1
            elif fid in egie_has:
                fixtures_enriched.append(fid)

        result.api_calls_live = api_calls_live
        result.fixtures_processed = len(set(fixtures_enriched))
        result.status = "completed" if not result.errors else "completed_with_errors"

    result.finished_at = datetime.now(timezone.utc)
    if result.run_id:
        store.finish_ingest_run(
            result.run_id,
            status=result.status,
            stats={
                "api_calls_live": api_calls_live,
                "fixtures_enriched": fixtures_enriched,
                "events_imported": events_imported,
                "skipped_egie_existing": skipped_egie,
                "skipped_api_cap": skipped_api_cap,
                "mirrored_egie_to_sqlite": mirrored_only,
                "resource_counts": result.resource_counts,
            },
            errors=result.errors,
        )

    from worldcup_predictor.goal_timing.service import GoalTimingFeatureService
    from worldcup_predictor.goal_timing.prediction_service import GoalTimingPredictionService

    GoalTimingFeatureService().probe_fixture_report(probe_fixture_id, persist=True)
    after_predict = GoalTimingPredictionService(settings).predict_fixture(probe_fixture_id, persist=True)

    after_coverage = coverage_snapshot(repo)
    after_probe = _probe_prediction(repo, settings, probe_fixture_id)

    return {
        "phase": "A",
        "probe_fixture_id": probe_fixture_id,
        "target_fixture_count": len(targets),
        "target_fixture_ids": targets,
        "ingest": result.to_dict(),
        "api_calls_used": api_calls_live,
        "fixtures_enriched": sorted(set(fixtures_enriched)),
        "fixtures_enriched_count": len(set(fixtures_enriched)),
        "goal_events_imported_rows": events_imported,
        "skipped_egie_existing": skipped_egie,
        "skipped_api_cap": skipped_api_cap,
        "coverage_before": before_coverage,
        "coverage_after": after_coverage,
        "probe_before": before_probe,
        "probe_after": after_probe,
        "prediction_regenerated": after_predict.get("prediction"),
        "prediction_id": after_predict.get("prediction_id"),
        "feature_snapshot_id": after_predict.get("feature_snapshot_id"),
    }


def _probe_prediction(
    repo: FootballIntelligenceRepository,
    settings: Settings,
    fixture_id: int,
) -> dict[str, Any]:
    from worldcup_predictor.goal_timing.config import MIN_DATA_QUALITY_FOR_PREDICTION
    from worldcup_predictor.goal_timing.features.builder import GoalTimingFeatureBuilder
    from worldcup_predictor.goal_timing.data.stored_adapter import StoredGoalTimingAdapter
    from worldcup_predictor.goal_timing.prediction_service import GoalTimingPredictionService

    stored = StoredGoalTimingAdapter(settings)
    builder = GoalTimingFeatureBuilder(stored=stored, max_api_event_fetches=0)
    row = repo.get_fixture_row(fixture_id) or {}
    features = builder.build(
        int(fixture_id),
        competition_key="premier_league",
        context={
            "home_team": row.get("home_team"),
            "away_team": row.get("away_team"),
            "match_date": stored.parse_kickoff(row.get("kickoff_utc")),
        },
    )
    dq = float(features.get("data_quality_score") or 0)
    hist = features.get("history_samples") or {}
    svc = GoalTimingPredictionService(settings)
    stored_pred = svc.repository.get_prediction_by_fixture(fixture_id)
    pred = stored_pred or {}
    return {
        "data_quality_score": dq,
        "would_publish_dq_gate": dq >= MIN_DATA_QUALITY_FOR_PREDICTION,
        "history_samples": hist,
        "provider_manifest": features.get("provider_manifest") or {},
        "stored_prediction": {
            "data_quality_score": float(pred.get("data_quality_score") or 0) if pred else None,
            "no_prediction_flag": bool(pred.get("no_prediction_flag")) if pred else None,
            "confidence_score": float(pred.get("confidence_score") or 0) if pred else None,
            "display_estimated_first_goal_minute": pred.get("display_estimated_first_goal_minute"),
        }
        if pred
        else None,
    }
