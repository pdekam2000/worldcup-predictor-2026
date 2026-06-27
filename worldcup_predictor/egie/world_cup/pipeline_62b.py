"""Phase 62B pipeline — fixture expansion + Sportmonks xG/lineups + feature rebuild."""

from __future__ import annotations

import logging
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.egie.world_cup.config import COMPETITION_TYPE_FINALS, WORLD_CUP_COMPETITION_KEY
from worldcup_predictor.egie.world_cup.coverage import measure_coverage, recommend_phase
from worldcup_predictor.egie.world_cup.mapping_audit import run_mapping_audit
from worldcup_predictor.egie.world_cup.sportmonks_wc_import import import_sportmonks_xg_lineups
from worldcup_predictor.egie.world_cup.sqlite_loader import count_wc_fixtures, import_and_load_sqlite
from worldcup_predictor.egie.world_cup.survival_rebuild import rebuild_survival_artifacts
from worldcup_predictor.egie.world_cup.wc_enriched_features import rebuild_enriched_feature_rows

logger = logging.getLogger(__name__)


def _coverage_before(settings: Settings) -> dict[str, Any]:
    return measure_coverage(settings=settings)


def _load_mapped_fixtures(settings: Settings) -> list[dict[str, Any]]:
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    rows = repo._conn.execute(
        """
        SELECT api_football_fixture_id, sportmonks_fixture_id, mapping_confidence
        FROM wc_fixture_mapping
        WHERE sportmonks_fixture_id IS NOT NULL AND blocked = 0
        ORDER BY mapping_confidence DESC
        """
    ).fetchall()
    return [
        {
            "api_football_fixture_id": int(r[0]),
            "sportmonks_fixture_id": int(r[1]),
            "mapping_confidence": float(r[2] or 0),
        }
        for r in rows
    ]


def _usable_finals_count(settings: Settings) -> int:
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    row = repo._conn.execute(
        """
        SELECT COUNT(1) FROM fixtures f
        JOIN fixture_results fr ON fr.fixture_id = f.fixture_id
        LEFT JOIN (
            SELECT fixture_id, COUNT(*) AS n FROM fixture_goal_events GROUP BY fixture_id
        ) g ON g.fixture_id = f.fixture_id
        WHERE f.competition_key = ?
          AND COALESCE(f.competition_type, 'world_cup_finals') = ?
          AND COALESCE(g.n, 0) > 0
        """,
        (WORLD_CUP_COMPETITION_KEY, COMPETITION_TYPE_FINALS),
    ).fetchone()
    return int(row[0] or 0) if row else 0


def recommend_phase_62b(
    *,
    coverage: dict[str, Any],
    usable_finals: int,
    provider_limit_note: str | None = None,
) -> str:
    if coverage.get("total_fixtures", 0) == 0:
        return "BLOCKED"
    if coverage.get("all_targets_met") and usable_finals >= 500:
        return "READY_FOR_PHASE_61B_RERUN"
    if provider_limit_note and coverage.get("total_fixtures", 0) < 400:
        return "PROVIDER_LIMITED"
    if usable_finals < 500 and coverage.get("total_fixtures", 0) < 500:
        if coverage.get("total_fixtures", 0) < 350:
            return "PROVIDER_LIMITED"
    return "NEED_MORE_IMPORTS"


def run_phase62b_pipeline(
    *,
    settings: Settings | None = None,
    skip_fixture_import: bool = False,
    max_sm_calls: int = 120,
    resume: bool = True,
    progress_every: int = 5,
) -> dict[str, Any]:
    settings = settings or get_settings()
    report: dict[str, Any] = {"steps": {}}

    report["coverage_before"] = _coverage_before(settings)
    report["usable_finals_before"] = _usable_finals_count(settings)
    report["fixture_count_before"] = count_wc_fixtures(settings)

    if not skip_fixture_import:
        report["steps"]["fixture_expansion"] = import_and_load_sqlite(settings=settings)
    else:
        report["steps"]["fixture_expansion"] = {"status": "skipped"}

    report["fixture_count_after_import"] = count_wc_fixtures(settings)
    report["steps"]["mapping_audit"] = run_mapping_audit(settings=settings, finals_only=True)
    mappings = _load_mapped_fixtures(settings)
    report["steps"]["sportmonks_xg_lineups"] = import_sportmonks_xg_lineups(
        mappings,
        settings=settings,
        max_api_calls=max_sm_calls,
        resume=resume,
        progress_every=progress_every,
    )
    report["steps"]["feature_rebuild"] = rebuild_enriched_feature_rows(settings=settings)
    try:
        report["steps"]["survival_rebuild"] = rebuild_survival_artifacts(settings=settings)
    except Exception as exc:
        report["steps"]["survival_rebuild"] = {"status": "error", "error": str(exc)[:200]}

    report["coverage_after"] = _coverage_before(settings)
    report["usable_finals_after"] = _usable_finals_count(settings)
    report["fixture_count_after"] = count_wc_fixtures(settings)

    provider_note = None
    if report["fixture_count_after"] < 400:
        provider_note = "api_football_league_1_historical_ceiling_near_330"

    report["recommendation"] = recommend_phase_62b(
        coverage=report["coverage_after"],
        usable_finals=report["usable_finals_after"],
        provider_limit_note=provider_note,
    )
    return report
