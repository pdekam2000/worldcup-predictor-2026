#!/usr/bin/env python3
"""Phase 31E — validate team ID + odds backfill."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.backtesting.hybrid_replay import (  # noqa: E402
    HybridReplayStats,
    _hybrid_settings,
    build_hybrid_intelligence_report,
    CacheOnlyApiFootballClient,
)
from worldcup_predictor.backtesting.phase31e_backfill import (  # noqa: E402
    audit_odds_inventory,
    backfill_team_ids,
    backfill_odds_from_cache,
    collect_cached_odds_sources,
)
from worldcup_predictor.cache.api_cache import get_api_cache
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository


def main() -> int:
    db = ROOT / "data" / "football_intelligence.db"
    artifact = ROOT / "artifacts" / "phase31e_odds_backfill_summary.json"
    checks: list[tuple[str, bool, str]] = []

    if not db.exists():
        print("FAIL: database missing")
        return 1

    settings = get_settings()
    disk_cache = get_api_cache(settings.api_cache_dir)
    repo = FootballIntelligenceRepository(path=str(db))

    team_result = backfill_team_ids(repo, disk_cache=disk_cache)
    checks.append(("team_backfill_ran", team_result["rows_scanned"] > 0, f"scanned={team_result['rows_scanned']}"))
    remaining_home = team_result["remaining_nulls"]["home_team_id"]
    checks.append(
        (
            "team_ids_backfilled_when_source_exists",
            team_result["rows_updated"] > 0 or remaining_home < team_result["rows_scanned"],
            f"updated={team_result['rows_updated']} remaining_home_null={remaining_home}",
        )
    )

    inv = audit_odds_inventory(repo, disk_cache=disk_cache)
    checks.append(("odds_cache_detected", inv["unique_fixtures"] > 0, f"fixtures={inv['unique_fixtures']}"))

    odds_result = backfill_odds_from_cache(repo, disk_cache=disk_cache)
    checks.append(
        (
            "odds_snapshots_created_or_exists",
            odds_result["odds_snapshots_created"] > 0 or odds_result["odds_snapshots_skipped_existing"] > 0,
            f"created={odds_result['odds_snapshots_created']}",
        )
    )

    sources = collect_cached_odds_sources(repo, disk_cache=disk_cache)
    test_fid = next(iter(sources), None)
    if test_fid:
        stats = HybridReplayStats()
        client = CacheOnlyApiFootballClient(_hybrid_settings(), stats=stats)
        row = repo.get_fixture_row(test_fid)
        ck = str((row or {}).get("competition_key") or "world_cup_2026")
        report = build_hybrid_intelligence_report(
            test_fid,
            repo=repo,
            api_client=client,
            settings=_hybrid_settings(),
            competition_key=ck,
            stats=stats,
        )
        odds_ok = report.odds is not None and getattr(report.odds, "available", False)
        checks.append(("hybrid_replay_uses_odds", odds_ok, f"fixture={test_fid} available={odds_ok}"))
        checks.append(("no_external_api_calls", stats.live_fetch_attempts + stats.http_calls == 0, str(stats.to_dict())))

    repo.close()

    checks.append(("summary_json_exists", artifact.exists(), str(artifact)))
    if artifact.exists():
        data = json.loads(artifact.read_text(encoding="utf-8"))
        checks.append(("summary_phase_31e", data.get("phase") == "31E", "phase ok"))

    failed = [c for c in checks if not c[1]]
    print("Phase 31E validation")
    print("-" * 40)
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    if failed:
        print(f"\n{len(failed)} check(s) failed")
        return 1
    print("\nAll checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
