"""Parallel Match Center aggregation — Phase A10."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from typing import Any

from worldcup_predictor.api.display_helpers import fixture_to_match_display
from worldcup_predictor.api.match_center_helpers import (
    competition_emoji,
    enrich_match_row,
    list_enabled_competitions,
    load_prediction_payloads,
    load_prediction_summaries,
)
from worldcup_predictor.config.competitions import CompetitionConfig, get_competition
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.domain.schedule import TournamentFixture
from worldcup_predictor.quota.match_schedule_cache import (
    cache_stats as schedule_cache_stats,
    get_schedule_cache,
    set_schedule_cache,
)
from worldcup_predictor.schedule.competition_schedule import build_schedule_service
from worldcup_predictor.schedule.match_center import build_match_center, classify_status
from worldcup_predictor.schedule.season_resolver import resolve_active_season

logger = logging.getLogger(__name__)


def _is_real_fixture(fixture: TournamentFixture) -> bool:
    return not fixture.is_placeholder and fixture.source != "placeholder"


def _load_one_competition(
    comp: CompetitionConfig,
    settings: Settings,
) -> dict[str, Any]:
    season = resolve_active_season(comp.key, settings=settings)
    comp = replace(comp, season=season)

    cached = get_schedule_cache(comp.key, season, settings=settings)
    if cached:
        return {
            "comp": comp,
            "fixtures": cached.fixtures,
            "source_label": cached.source_label,
            "season": season,
            "from_cache": True,
        }

    try:
        service = build_schedule_service(
            settings,
            competition_key=comp.key,
            season=season,
        )
        snapshot = build_match_center(service, settings, enrich_live=False, enrich_finished_limit=0)
        fixtures = [f for f in snapshot.upcoming + snapshot.live + snapshot.finished if _is_real_fixture(f)]
        set_schedule_cache(comp.key, season, fixtures, source_label=snapshot.source_label, settings=settings)
        return {
            "comp": comp,
            "fixtures": fixtures,
            "source_label": snapshot.source_label,
            "season": season,
            "from_cache": False,
        }
    except Exception as exc:
        logger.warning("Schedule load failed for %s: %s", comp.key, exc)
        return {
            "comp": comp,
            "fixtures": [],
            "source_label": None,
            "season": season,
            "from_cache": False,
            "error": str(exc),
        }


def aggregate_all_competitions(
    *,
    settings: Settings | None = None,
    max_workers: int = 8,
    priority_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Load all enabled competitions in parallel with season resolution + cache."""
    settings = settings or get_settings()
    started = time.perf_counter()
    comps = list_enabled_competitions()

    if priority_keys:
        priority_set = set(priority_keys)
        comps.sort(key=lambda c: (0 if c.key in priority_set else 1, c.name))

    results: list[dict[str, Any]] = []
    cache_hits = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_load_one_competition, comp, settings): comp for comp in comps}
        for fut in as_completed(futures):
            row = fut.result()
            if row.get("from_cache"):
                cache_hits += 1
            results.append(row)

    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    return {
        "results": results,
        "load_ms": elapsed_ms,
        "cache_hits": cache_hits,
        "competition_count": len(comps),
        "schedule_cache": schedule_cache_stats(),
    }


def build_match_rows(
    agg: dict[str, Any],
    *,
    settings: Settings | None = None,
    include_summary: bool = True,
    include_insights: bool = True,
    include_owner_meta: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, set[int]], set[int]]:
    settings = settings or get_settings()
    summaries = load_prediction_summaries(settings) if include_summary else {}
    payloads = load_prediction_payloads(settings) if include_insights or include_owner_meta else {}

    rows: list[dict[str, Any]] = []
    pred_by_fixture: dict[str, set[int]] = {}
    predicted_total: set[int] = set()

    from worldcup_predictor.database.repository import FootballIntelligenceRepository

    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    all_eval_rows = repo.list_all_worldcup_prediction_evaluations()
    evaluations_by_fixture = {int(r["fixture_id"]): r for r in all_eval_rows if r.get("fixture_id") is not None}

    for block in agg.get("results") or []:
        comp: CompetitionConfig = block["comp"]
        predicted_ids = {
            int(r["fixture_id"])
            for r in repo.list_worldcup_stored_predictions(competition_key=comp.key, limit=500, offset=0)
            if r.get("fixture_id") is not None
        }
        predicted_total |= predicted_ids
        for fixture in block.get("fixtures") or []:
            pred_by_fixture[fixture.fixture_id] = predicted_ids
            base = {
                **fixture_to_match_display(fixture, league=comp.display_name, season=comp.season),
                "competition_key": comp.key,
                "competition_name": comp.name,
                "competition_emoji": competition_emoji(comp.key),
                "competition_country": comp.country,
                "resolved_season": block.get("season"),
                "has_prediction": fixture.fixture_id in predicted_ids,
                "bucket": classify_status(fixture.status),
            }
            summary = summaries.get(fixture.fixture_id)
            payload = payloads.get(fixture.fixture_id)
            row = enrich_match_row(
                base,
                summary=summary,
                payload=payload,
                include_insights=include_insights,
                include_owner_meta=include_owner_meta,
            )
            if base.get("bucket") == "finished":
                from worldcup_predictor.api.match_evaluation import evaluation_summary_from_row

                eval_summary = evaluation_summary_from_row(evaluations_by_fixture.get(fixture.fixture_id))
                if eval_summary:
                    row["match_evaluation"] = eval_summary
                    row["result_status"] = eval_summary.get("result_status")
                    row["final_score"] = eval_summary.get("final_score") or row.get("final_score")
            rows.append(row)

    return rows, pred_by_fixture, predicted_total
