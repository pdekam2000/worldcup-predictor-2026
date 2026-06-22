"""EGIE Phase 1A–1B validation."""

from __future__ import annotations

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    root = Path(__file__).resolve().parents[1]

    record("egie_module", (root / "worldcup_predictor/egie/config.py").is_file())
    record("egie_repository", (root / "worldcup_predictor/egie/storage/repository.py").is_file())
    record("egie_migration", (root / "alembic/versions/008_egie_provider_raw_store.py").is_file())
    record("egie_pl_ingest", (root / "worldcup_predictor/egie/ingest/api_football_premier_league.py").is_file())
    record("egie_cli", (root / "scripts/egie_ingest_api_football_premier_league.py").is_file())

    from worldcup_predictor.egie.config import (
        API_FOOTBALL_RESOURCE_TYPES,
        PREMIER_LEAGUE_API_FOOTBALL_JOB,
        SPORTMONKS_RESOURCE_TYPES,
        get_ingest_job,
    )
    from worldcup_predictor.egie.guards import backtest_mode, external_api_allowed, ingest_mode
    from worldcup_predictor.egie.storage.repository import build_request_fingerprint

    record("manifest_pl_job", PREMIER_LEAGUE_API_FOOTBALL_JOB.competition_key == "premier_league")
    record("api_football_resources", "fixtures" in API_FOOTBALL_RESOURCE_TYPES)
    record("sportmonks_schema_ready", "xg" in SPORTMONKS_RESOURCE_TYPES and "pressure_index" in SPORTMONKS_RESOURCE_TYPES)
    record("get_ingest_job", get_ingest_job("api_football_premier_league").job_key == "api_football_premier_league")

    with backtest_mode():
        record("backtest_blocks_api", not external_api_allowed(operation="test"))
    record("non_ingest_blocks_api", not external_api_allowed(operation="test"))

    with ingest_mode():
        record("ingest_allows_api", external_api_allowed(operation="test"))

    fp = build_request_fingerprint(
        provider="api_football",
        resource_type="fixtures",
        request_endpoint="fixtures",
        request_params={"league": 39, "season": 2024},
    )
    record("fingerprint_stable", len(fp) == 64)

    migration = (root / "alembic/versions/008_egie_provider_raw_store.py").read_text(encoding="utf-8")
    record("migration_raw_table", "egie_provider_raw_responses" in migration)
    record("migration_sportmonks_column", "sportmonks_fixture_id" in migration)
    record("migration_ingest_runs", "egie_ingest_runs" in migration)

    fallback = (root / "worldcup_predictor/goal_timing/data/api_football_fallback.py").read_text(encoding="utf-8")
    record("fallback_uses_guards", "external_api_allowed" in fallback)
    record("fallback_reads_egie", "load_goal_events_from_egie" in fallback)

    builder = (root / "worldcup_predictor/goal_timing/features/builder.py").read_text(encoding="utf-8")
    record("builder_db_only_comment", "No live API" in builder or "no live API" in builder.lower())

    backtest = (root / "worldcup_predictor/goal_timing/backtest/runner.py").read_text(encoding="utf-8")
    record("backtest_db_policy", "db_only" in backtest or "DB-only" in backtest)

    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nEGIE Phase 1A–1B validation: {passed}/{len(checks)} PASS")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print()
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
