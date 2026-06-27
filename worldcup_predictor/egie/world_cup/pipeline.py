"""Phase 62 World Cup EGIE data expansion pipeline."""

from __future__ import annotations

import logging
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.egie.world_cup.api_football_ingest import ingest_api_football_resources, list_wc_fixture_ids
from worldcup_predictor.egie.world_cup.coverage import measure_coverage, recommend_phase
from worldcup_predictor.egie.world_cup.egie_feature_rows import build_egie_feature_rows
from worldcup_predictor.egie.world_cup.sportmonks_fixture_list import list_sportmonks_wc_fixtures
from worldcup_predictor.egie.world_cup.sportmonks_ingest import ingest_sportmonks_wc_fixtures
from worldcup_predictor.egie.world_cup.sqlite_loader import count_wc_fixtures, import_and_load_sqlite
from worldcup_predictor.egie.world_cup.survival_rebuild import rebuild_survival_artifacts
from worldcup_predictor.research.goal_event_backfill import GoalEventBackfillRunner

logger = logging.getLogger(__name__)


def _run_xg_backfill(settings: Settings, *, max_calls: int) -> dict[str, Any]:
    try:
        from worldcup_predictor.feature_store.sportmonks_xg_store import SportmonksXgFeatureStore
        from worldcup_predictor.egie.world_cup.config import SPORTMONKS_LEAGUE_ID

        store = SportmonksXgFeatureStore(settings)
        if not store.configured:
            return {"status": "skipped", "reason": "xg_store_not_configured"}
        return store.backfill_league(
            league_id=SPORTMONKS_LEAGUE_ID,
            season_id=None,
            max_calls=max_calls,
            finished_only=True,
            use_cache=True,
            force_reimport=False,
        )
    except Exception as exc:
        logger.warning("xg_backfill_failed: %s", exc)
        return {"status": "error", "error": str(exc)}


def run_phase62_pipeline(
    *,
    settings: Settings | None = None,
    skip_api_import: bool = False,
    max_af_calls: int = 120,
    max_sm_calls: int = 60,
    max_goal_backfill_calls: int = 80,
    max_xg_calls: int = 80,
) -> dict[str, Any]:
    settings = settings or get_settings()
    report: dict[str, Any] = {"steps": {}}

    if not skip_api_import:
        report["steps"]["sqlite_import"] = import_and_load_sqlite(settings=settings)
    else:
        report["steps"]["sqlite_import"] = {"status": "skipped"}

    report["wc_fixture_count"] = count_wc_fixtures(settings)
    fixture_ids = list_wc_fixture_ids(settings, limit=600)
    report["fixture_ids_count"] = len(fixture_ids)

    runner = GoalEventBackfillRunner(settings=settings, max_api_calls=max_goal_backfill_calls)
    backfill_out = runner.run()
    report["steps"]["goal_event_backfill"] = {
        "candidates": len(backfill_out.get("candidates") or []),
        "results_count": len(backfill_out.get("results") or []),
        "api_calls_used": backfill_out.get("api_calls_used"),
        "comparison": backfill_out.get("comparison"),
    }

    if fixture_ids:
        report["steps"]["api_football_egie_raw"] = ingest_api_football_resources(
            fixture_ids[:200],
            settings=settings,
            max_api_calls=max_af_calls,
        )

    sm_fixtures = list_sportmonks_wc_fixtures(settings, limit=max_sm_calls)
    report["steps"]["sportmonks_ingest"] = ingest_sportmonks_wc_fixtures(
        sm_fixtures[:max_sm_calls],
        settings=settings,
        max_api_calls=max_sm_calls,
    )

    report["steps"]["sportmonks_xg_backfill"] = _run_xg_backfill(settings, max_calls=max_xg_calls)
    report["steps"]["egie_feature_rows"] = build_egie_feature_rows(settings=settings, limit=600)
    try:
        report["steps"]["survival_rebuild"] = rebuild_survival_artifacts(settings=settings)
    except Exception as exc:
        logger.warning("survival_rebuild_failed: %s", exc)
        report["steps"]["survival_rebuild"] = {"status": "error", "error": str(exc)}
    report["coverage"] = measure_coverage(settings=settings)
    report["recommendation"] = recommend_phase(report["coverage"])
    return report
