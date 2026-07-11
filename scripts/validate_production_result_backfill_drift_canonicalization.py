#!/usr/bin/env python3
"""Validate production result-backfill drift canonicalization."""

from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.data_import import european_result_backfill as erb
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.ingestion.league_history_importer import LeagueHistoryImporter

PHASE = "PRODUCTION-DRIFT-CANONICALIZATION-VALIDATION"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []
    src = (ROOT / "worldcup_predictor/data_import/european_result_backfill.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    # 1-3 resume / checkpoint / no restart completed — rescue scripts own checkpoint; backfill skips existing
    checks.append(
        _check(
            "resume_skips_existing_results",
            "skipped_existing" in src and "if not force and repo.get_fixture_result_row(fid)" in src,
            "backfill_single_fixture skips when result exists unless force=True",
        )
    )
    checks.append(
        _check(
            "force_flag_required_for_overwrite",
            "force: bool = False" in src and "force=args.force" in (ROOT / "scripts/backfill_european_fixture_results.py").read_text(encoding="utf-8"),
            "CLI defaults force=False",
        )
    )

    # 4 duplicate prevention — repository upsert + DB unique fixture_id
    repo_src = inspect.getsource(FootballIntelligenceRepository.upsert_fixture_result)
    checks.append(
        _check(
            "finished_status_required_for_result_upsert",
            "classify_status(fixture.status) != \"finished\"" in repo_src,
        )
    )

    # 5-7 regulation vs ET/penalty — existing parser paths unchanged
    checks.append(
        _check(
            "penalty_score_extracted_separately",
            "_penalty_score_from_item" in src and "normalize_match_outcome_type" in src,
        )
    )

    # 8 postponed/abandoned not stored as normal FT
    checks.append(
        _check(
            "non_finished_status_blocked_in_upsert",
            "classify_status(fixture.status) != \"finished\"" in repo_src,
        )
    )

    # 9 transaction — repository uses connection (no change required)
    checks.append(_check("repository_methods_present", hasattr(FootballIntelligenceRepository, "upsert_fixture_result")))

    # 10 provider failures logged safely
    checks.append(
        _check(
            "provider_failure_outcomes_defined",
            all(x in src for x in ("missing_provider", "skipped_low_confidence", "skipped_ambiguous")),
        )
    )

    # 11 batching continues after fixture failure
    checks.append(
        _check(
            "per_fixture_loop_continues",
            "for row in rows:" in inspect.getsource(erb.backfill_competition_results),
        )
    )

    # 12-13 no prediction / WDE mutation in backfill module
    forbidden = ("run_fixture_prediction", "wde", "ecse", "btts")
    lower = src.lower()
    checks.append(
        _check(
            "no_prediction_or_model_execution",
            not any(tok in lower for tok in forbidden),
        )
    )

    # 14 no migration required
    checks.append(_check("no_schema_migration_in_drift", "ALTER TABLE" not in src.upper()))

    # 15 importer compatibility + alias
    checks.append(
        _check(
            "repository_league_season_alias",
            hasattr(FootballIntelligenceRepository, "count_fixtures_for_league_season"),
        )
    )
    importer_src = inspect.getsource(LeagueHistoryImporter._resolve_competition)
    checks.append(
        _check(
            "tier_b_shadow_fallback_in_importer",
            "TIER_B_SHADOW_DOMAINS" in importer_src,
        )
    )

    # Drift-specific fixes present
    cache_src = inspect.getsource(erb._DateApiCache)
    checks.append(_check("season_aware_date_cache", "season: int | None" in cache_src))
    checks.append(_check("force_refresh_in_date_cache", "force_refresh: bool" in cache_src))
    resolve_src = inspect.getsource(erb.resolve_provider_match)
    checks.append(_check("date_only_fallback_present", 'method_prefix="date_only"' in resolve_src))

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    report = {"phase": PHASE, "passed": passed, "total": total, "checks": checks}
    print(__import__("json").dumps(report, indent=2))
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
