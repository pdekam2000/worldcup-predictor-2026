#!/usr/bin/env python3
"""Phase 54H-4 post-backfill coverage audit."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54h4_pressure_backfill_batch1"
CACHE_DIR = Path("data/feature_store/sportmonks_pressure/raw")


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    prerun_path = ARTIFACT_DIR / "prerun_validation.json"
    before = 0
    if prerun_path.is_file():
        before = int(json.loads(prerun_path.read_text(encoding="utf-8")).get("pre_run_fixture_count") or 0)

    from worldcup_predictor.feature_store.pressure_store.repository import SportmonksPressureRepository

    repo = SportmonksPressureRepository()
    audit = repo.audit_coverage()
    after = int((audit.get("records") or {}).get("fixture_count") or 0)
    record_count = int((audit.get("records") or {}).get("record_count") or 0)
    avg_rows = float((audit.get("summaries") or {}).get("avg_rows_per_fixture") or 0)

    by_league: dict[str, int] = {}
    by_season: dict[str, int] = {}
    zero_row = 0
    for row in repo.list_fixture_summaries(limit=5000):
        lid = str(row.get("league_id") or "unknown")
        by_league[lid] = by_league.get(lid, 0) + 1
        sid = str(row.get("season_id") or "unknown")
        by_season[sid] = by_season.get(sid, 0) + 1
        if int(row.get("pressure_row_count") or 0) <= 0:
            zero_row += 1

    batch_results: list[dict] = []
    api_live = api_cached = imported = 0
    for path in sorted(ARTIFACT_DIR.glob("backfill_*.json")):
        if path.name == "backfill_result.json":
            continue
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        bf = blob.get("backfill") or {}
        batch_results.append(
            {
                "file": path.name,
                "job_key": (blob.get("options") or {}).get("job_key"),
                "fixtures_imported": bf.get("fixtures_imported"),
                "fixtures_empty": bf.get("fixtures_empty"),
                "fixtures_error": bf.get("fixtures_error"),
                "fixtures_skipped": bf.get("fixtures_skipped"),
                "api_calls_live": bf.get("api_calls_live"),
                "api_calls_cached": bf.get("api_calls_cached"),
                "records_written": bf.get("records_written"),
            }
        )
        api_live += int(bf.get("api_calls_live") or 0)
        api_cached += int(bf.get("api_calls_cached") or 0)
        imported += int(bf.get("fixtures_imported") or 0)

    cache_files = len(list(CACHE_DIR.glob("*.json"))) if CACHE_DIR.is_dir() else 0
    manifest_stats = repo.manifest_job_stats("phase54h4")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase": "54H-4",
        "fixtures_before": before,
        "fixtures_after": after,
        "new_fixtures": after - before,
        "target_minimum": 150,
        "target_met": after >= 150,
        "record_count": record_count,
        "avg_rows_per_fixture": round(avg_rows, 2),
        "fixtures_with_zero_pressure_rows": zero_row,
        "by_league": by_league,
        "by_season": by_season,
        "duplicate_groups_sample": audit.get("duplicate_groups_sample") or [],
        "api_calls_live_total": api_live,
        "api_calls_cached_total": api_cached,
        "fixtures_imported_batches": imported,
        "cache_files": cache_files,
        "manifest_stats": manifest_stats,
        "batch_results": batch_results,
    }
    (ARTIFACT_DIR / "coverage_audit.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(
        {
            "fixtures_before": before,
            "fixtures_after": after,
            "new_fixtures": after - before,
            "target_met": after >= 150,
            "api_calls_live": api_live,
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
