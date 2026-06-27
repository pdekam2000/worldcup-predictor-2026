"""Match schedule endpoints — Phase A10 parallel aggregation + season resolver."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from worldcup_predictor.api.deps import get_optional_current_user, user_has_owner_access
from worldcup_predictor.api.display_helpers import fixture_to_match_display
from worldcup_predictor.api.match_center_aggregator import (
    aggregate_all_competitions,
    build_match_rows,
)
from worldcup_predictor.api.match_center_helpers import (
    apply_season_override,
    competition_emoji,
    enrich_match_row,
    get_todays_elite_picks,
    list_enabled_competitions,
    load_prediction_payloads,
    load_prediction_summaries,
)
from worldcup_predictor.api.web_auth import WebAuthUser
from worldcup_predictor.config.competitions import DEFAULT_COMPETITION_KEY, get_competition
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.domain.schedule import TournamentFixture
from worldcup_predictor.quota.fixtures_list_cache import get_cached as get_fixtures_list_cached
from worldcup_predictor.quota.fixtures_list_cache import store as store_fixtures_list_cache
from worldcup_predictor.quota.match_schedule_cache import get_schedule_cache, set_schedule_cache
from worldcup_predictor.schedule.competition_schedule import build_schedule_service
from worldcup_predictor.schedule.match_center import build_match_center, classify_status
from worldcup_predictor.schedule.season_resolver import resolve_active_season

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/matches", tags=["matches"])

MatchStatusFilter = Literal["upcoming", "live", "finished", "all", "predicted"]


def _is_real_fixture(fixture: TournamentFixture) -> bool:
    return not fixture.is_placeholder and fixture.source != "placeholder"


def _predicted_fixture_ids(settings, competition_key: str) -> set[int]:
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    rows = repo.list_worldcup_stored_predictions(
        competition_key=competition_key,
        limit=500,
        offset=0,
    )
    return {int(r["fixture_id"]) for r in rows if r.get("fixture_id") is not None}


def _filter_team(fixtures: list[TournamentFixture], team: str | None) -> list[TournamentFixture]:
    if not team or not team.strip():
        return fixtures
    needle = team.strip().lower()
    return [
        f
        for f in fixtures
        if needle in f.home_team.lower() or needle in f.away_team.lower()
    ]


def _bucket_fixtures(
    fixtures: list[TournamentFixture],
    *,
    status: MatchStatusFilter,
    predicted_ids: set[int],
) -> list[TournamentFixture]:
    if status == "predicted":
        return [f for f in fixtures if f.fixture_id in predicted_ids]

    buckets: dict[str, list[TournamentFixture]] = {"upcoming": [], "live": [], "finished": []}
    for fixture in fixtures:
        bucket = classify_status(fixture.status)
        buckets[bucket].append(fixture)

    if status == "all":
        combined = buckets["live"] + buckets["upcoming"] + buckets["finished"]
        combined.sort(key=lambda f: f.kickoff_time, reverse=True)
        return combined
    if status == "upcoming":
        out = buckets["upcoming"]
        out.sort(key=lambda f: f.kickoff_time)
        return out
    if status == "live":
        out = buckets["live"]
        out.sort(key=lambda f: f.kickoff_time)
        return out
    out = buckets["finished"]
    out.sort(key=lambda f: f.kickoff_time, reverse=True)
    return out


def _load_competition_fixtures(
    comp_key: str,
    season: int,
    settings,
) -> tuple[list[TournamentFixture], str | None, bool]:
    cached = get_schedule_cache(comp_key, season, settings=settings)
    if cached:
        return cached.fixtures, cached.source_label, True
    service = build_schedule_service(
        settings,
        competition_key=comp_key,
        season=season,
    )
    snapshot = build_match_center(service, settings, enrich_live=False, enrich_finished_limit=0)
    fixtures = snapshot.upcoming + snapshot.live + snapshot.finished
    fixtures = [f for f in fixtures if _is_real_fixture(f)]
    set_schedule_cache(comp_key, season, fixtures, source_label=snapshot.source_label, settings=settings)
    return fixtures, snapshot.source_label, False


def _resolve_comp(comp, season: int | None, settings):
    if season is not None:
        return apply_season_override(comp, season)
    resolved = resolve_active_season(comp.key, settings=settings)
    return replace(comp, season=resolved)


def _fixture_row(
    fixture: TournamentFixture,
    *,
    comp,
    predicted_ids: set[int],
    summaries: dict[int, dict[str, Any]],
    payloads: dict[int, dict[str, Any]],
    include_summary: bool,
    include_insights: bool,
    include_owner_meta: bool,
) -> dict[str, Any]:
    base = {
        **fixture_to_match_display(fixture, league=comp.display_name, season=comp.season),
        "competition_key": comp.key,
        "competition_name": comp.name,
        "competition_emoji": competition_emoji(comp.key),
        "competition_country": comp.country,
        "resolved_season": comp.season,
        "has_prediction": fixture.fixture_id in predicted_ids,
        "bucket": classify_status(fixture.status),
    }
    summary = summaries.get(fixture.fixture_id) if include_summary else None
    payload = payloads.get(fixture.fixture_id)
    return enrich_match_row(
        base,
        summary=summary,
        payload=payload,
        include_insights=include_insights,
        include_owner_meta=include_owner_meta,
    )


def _apply_row_filters(
    rows: list[dict[str, Any]],
    *,
    has_prediction: bool | None,
    elite_only: bool,
    predicted_total: set[int],
) -> list[dict[str, Any]]:
    out = rows
    if has_prediction is True:
        out = [r for r in out if r.get("fixture_id") in predicted_total or r.get("id") in predicted_total]
    elif has_prediction is False:
        out = [r for r in out if r.get("fixture_id") not in predicted_total and r.get("id") not in predicted_total]
    if elite_only:
        out = [r for r in out if (r.get("prediction_summary") or {}).get("is_elite_pick")]
    return out


def _supplement_finished_evaluated_rows(
    rows: list[dict[str, Any]],
    *,
    settings,
) -> list[dict[str, Any]]:
    """Keep evaluated predicted fixtures visible when schedule no longer lists them as finished."""
    from worldcup_predictor.api.evaluated_results import build_finished_match_row_from_evaluation

    existing = {int(r.get("fixture_id") or r.get("id") or 0) for r in rows}
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    try:
        eval_rows = repo.list_all_worldcup_prediction_evaluations()
    finally:
        repo.close()

    extras: list[dict[str, Any]] = []
    for eval_row in eval_rows:
        fid = int(eval_row.get("fixture_id") or 0)
        if fid <= 0 or fid in existing:
            continue
        synthetic = build_finished_match_row_from_evaluation(eval_row, settings=settings)
        if synthetic:
            extras.append(synthetic)

    if not extras:
        return rows
    merged = rows + extras
    merged.sort(key=lambda r: str(r.get("match_date") or ""), reverse=True)
    return merged


@router.get("")
def list_matches(
    status: MatchStatusFilter = Query(default="upcoming", description="Fixture bucket filter"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    team: str | None = Query(default=None, description="Filter by team name substring"),
    competition: str = Query(default=DEFAULT_COMPETITION_KEY, description="Competition key or 'all'"),
    season: int | None = Query(default=None),
    has_prediction: bool | None = Query(default=None, description="Only fixtures with stored predictions"),
    include_summary: bool = Query(default=True, description="Attach cached prediction summary when available"),
    include_insights: bool = Query(default=True, description="Attach match insight chips from cached payload"),
    country: str | None = Query(default=None, description="Filter by competition country"),
    elite_only: bool = Query(default=False, description="Only fixtures with elite-tier cached picks"),
    user: WebAuthUser | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    """Paginated match listing — parallel aggregation when competition=all."""
    settings = get_settings()
    include_owner_meta = bool(user and user_has_owner_access(user.role))

    if competition.strip().lower() in ("all", "*"):
        comps = list_enabled_competitions()
        if country:
            needle = country.strip().lower()
            comps = [c for c in comps if needle in (c.country or "").lower()]

        priority_keys = [DEFAULT_COMPETITION_KEY, "champions_league", "premier_league"]
        agg = aggregate_all_competitions(
            settings=settings,
            priority_keys=priority_keys,
        )
        all_rows, pred_by_fixture, predicted_total = build_match_rows(
            agg,
            settings=settings,
            include_summary=include_summary,
            include_insights=include_insights,
            include_owner_meta=include_owner_meta,
        )

        if team:
            needle = team.strip().lower()
            all_rows = [
                r
                for r in all_rows
                if needle in str(r.get("home_team", "")).lower()
                or needle in str(r.get("away_team", "")).lower()
            ]

        bucketed: list[dict[str, Any]] = []
        for row in all_rows:
            b = row.get("bucket") or "upcoming"
            if status == "all" or status == b or (status == "predicted" and row.get("has_prediction")):
                bucketed.append(row)

        if status == "upcoming":
            bucketed.sort(key=lambda r: r.get("match_date") or "")
        elif status in ("live", "finished", "all"):
            bucketed.sort(key=lambda r: r.get("match_date") or "", reverse=True)

        filtered = _apply_row_filters(
            bucketed,
            has_prediction=has_prediction,
            elite_only=elite_only and include_summary,
            predicted_total=predicted_total,
        )
        if status == "finished":
            filtered = _supplement_finished_evaluated_rows(filtered, settings=settings)

        total_count = len(filtered)
        start = (page - 1) * page_size
        page_rows = filtered[start : start + page_size]
        elite_picks = get_todays_elite_picks(all_rows, limit=10) if include_summary else []

        return {
            "status": "ok",
            "competition": "all",
            "season": season,
            "filter_status": status,
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total_count + page_size - 1) // page_size) if total_count else 0,
            "count": len(page_rows),
            "matches": page_rows,
            "elite_picks_today": elite_picks,
            "predicted_fixture_count": len(predicted_total),
            "source_label": "Live API",
            "competitions_included": [c.key for c in comps],
            "load_ms": agg.get("load_ms"),
            "cache_hits": agg.get("cache_hits"),
            "schedule_cache": agg.get("schedule_cache"),
        }

    try:
        comp = get_competition(competition)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    comp = _resolve_comp(comp, season, settings)

    try:
        fixtures, source_label, from_cache = _load_competition_fixtures(comp.key, comp.season, settings)
    except Exception as exc:
        logger.exception("Match list API error")
        raise HTTPException(status_code=500, detail="Failed to load matches.") from exc

    predicted_ids = _predicted_fixture_ids(settings, comp.key)
    summaries = load_prediction_summaries(settings, competition_key=comp.key) if include_summary else {}
    payloads = (
        load_prediction_payloads(settings, competition_key=comp.key)
        if include_insights or include_owner_meta
        else {}
    )
    filtered_fixtures = _bucket_fixtures(fixtures, status=status, predicted_ids=predicted_ids)
    filtered_fixtures = _filter_team(filtered_fixtures, team)

    match_rows = [
        _fixture_row(
            fixture,
            comp=comp,
            predicted_ids=predicted_ids,
            summaries=summaries,
            payloads=payloads,
            include_summary=include_summary,
            include_insights=include_insights,
            include_owner_meta=include_owner_meta,
        )
        for fixture in filtered_fixtures
    ]
    if status == "finished":
        from worldcup_predictor.api.match_evaluation import evaluation_summary_from_row

        repo = FootballIntelligenceRepository(settings.sqlite_path or None)
        try:
            eval_map = {
                int(r["fixture_id"]): r
                for r in repo.list_all_worldcup_prediction_evaluations()
                if r.get("fixture_id") is not None
            }
            for row in match_rows:
                if row.get("bucket") != "finished":
                    continue
                summary = evaluation_summary_from_row(eval_map.get(int(row.get("fixture_id") or 0)))
                if summary:
                    row["match_evaluation"] = summary
                    row["result_status"] = summary.get("result_status")
                    row["final_score"] = summary.get("final_score") or row.get("final_score")
        finally:
            repo.close()
        match_rows = _supplement_finished_evaluated_rows(match_rows, settings=settings)

    match_rows = _apply_row_filters(
        match_rows,
        has_prediction=has_prediction,
        elite_only=elite_only and include_summary,
        predicted_total=predicted_ids,
    )

    total_count = len(match_rows)
    start = (page - 1) * page_size
    page_rows = match_rows[start : start + page_size]

    return {
        "status": "ok",
        "competition": comp.key,
        "season": comp.season,
        "resolved_season": comp.season,
        "filter_status": status,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total_count + page_size - 1) // page_size) if total_count else 0,
        "count": len(page_rows),
        "matches": page_rows,
        "elite_picks_today": get_todays_elite_picks(match_rows, limit=10) if include_summary else [],
        "predicted_fixture_count": len(predicted_ids),
        "source_label": source_label,
        "from_cache": from_cache,
    }


@router.get("/elite-picks-today")
def elite_picks_today(
    limit: int = Query(default=10, ge=1, le=20),
    competition: str = Query(default="all"),
) -> dict[str, Any]:
    """Top elite picks kicking off today."""
    settings = get_settings()
    if competition.strip().lower() in ("all", "*"):
        agg = aggregate_all_competitions(settings=settings)
        rows, _, _ = build_match_rows(agg, settings=settings, include_summary=True)
    else:
        comp = get_competition(competition)
        comp = _resolve_comp(comp, None, settings)
        fixtures, _, _ = _load_competition_fixtures(comp.key, comp.season, settings)
        summaries = load_prediction_summaries(settings, competition_key=comp.key)
        payloads = load_prediction_payloads(settings, competition_key=comp.key)
        predicted_ids = _predicted_fixture_ids(settings, comp.key)
        rows = [
            enrich_match_row(
                {
                    **fixture_to_match_display(f, league=comp.display_name, season=comp.season),
                    "competition_key": comp.key,
                    "competition_name": comp.name,
                    "competition_emoji": competition_emoji(comp.key),
                    "has_prediction": f.fixture_id in predicted_ids,
                    "bucket": classify_status(f.status),
                },
                summary=summaries.get(f.fixture_id),
                payload=payloads.get(f.fixture_id),
            )
            for f in fixtures
        ]
    picks = get_todays_elite_picks(rows, limit=limit)
    return {"status": "ok", "count": len(picks), "picks": picks}


@router.get("/upcoming")
def upcoming_matches(
    competition: str = Query(default=DEFAULT_COMPETITION_KEY, description="Competition registry key"),
    season: int | None = Query(default=None, description="Season year override"),
    limit: int = Query(default=0, ge=0, le=200, description="Max fixtures (0 = use app default)"),
) -> dict[str, Any]:
    """Return upcoming fixtures for a competition with auto-resolved season."""
    try:
        comp = get_competition(competition)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    settings = get_settings()
    comp = _resolve_comp(comp, season, settings)

    effective_limit = limit if limit > 0 else settings.upcoming_fixture_limit

    cached = get_fixtures_list_cached(comp.key, comp.season, effective_limit, settings=settings)
    if cached is not None:
        return cached

    try:
        service = build_schedule_service(
            settings,
            competition_key=comp.key,
            season=comp.season,
        )
        fixtures = service.get_upcoming_matches(limit=effective_limit)
    except RuntimeError as exc:
        logger.warning("Upcoming matches API error (runtime): %s", exc)
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "count": 0,
                "matches": [],
                "message": str(exc),
            },
        ) from exc
    except Exception as exc:
        logger.exception("Upcoming matches API error")
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "count": 0,
                "matches": [],
                "message": "Failed to load upcoming matches.",
            },
        ) from exc

    real_fixtures = [fixture for fixture in fixtures if _is_real_fixture(fixture)]
    matches = [
        {
            **fixture_to_match_display(fixture, league=comp.display_name, season=comp.season),
            "competition_key": comp.key,
            "resolved_season": comp.season,
        }
        for fixture in real_fixtures
    ]

    response = {
        "status": "ok",
        "count": len(matches),
        "total_count": len(matches),
        "matches": matches,
        "cache_source": "live",
        "resolved_season": comp.season,
    }
    store_fixtures_list_cache(comp.key, comp.season, effective_limit, response, settings=settings)
    return response


@router.get("/{fixture_id}/evaluation")
def get_match_evaluation(fixture_id: int) -> dict[str, Any]:
    """Public read-only production evaluation summary for a finished fixture."""
    from worldcup_predictor.api.match_evaluation import get_production_evaluation_summary

    summary = get_production_evaluation_summary(fixture_id)
    if not summary:
        return {"status": "pending", "fixture_id": fixture_id, "evaluation": None}
    return {"status": "ok", "fixture_id": fixture_id, "evaluation": summary}
