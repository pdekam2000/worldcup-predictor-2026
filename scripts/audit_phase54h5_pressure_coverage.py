#!/usr/bin/env python3
"""Phase 54H-5 post-expansion pressure coverage audit."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54h5_pressure_expansion"
CACHE_DIR = Path("data/feature_store/sportmonks_pressure/raw")
_WC = "732"
_UEFA = frozenset({"2", "5", "2286"})


def _load_batch_results() -> tuple[list[dict], int, int, int]:
    batch_results: list[dict] = []
    api_live = api_cached = imported = 0
    for path in sorted(ARTIFACT_DIR.glob("backfill_*.json")):
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        bf = blob.get("backfill") or {}
        batch_results.append(
            {
                "file": path.name,
                "job_key": (blob.get("options") or {}).get("job_key") or bf.get("job_key"),
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
    return batch_results, api_live, api_cached, imported


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    pre_path = ARTIFACT_DIR / "pre_run_state.json"
    before_fixtures = before_records = 0
    if pre_path.is_file():
        pre = json.loads(pre_path.read_text(encoding="utf-8"))
        before_fixtures = int(pre.get("pressure_fixture_count") or 0)
        before_records = int(pre.get("pressure_record_count") or 0)

    from worldcup_predictor.feature_store.pressure_store.repository import SportmonksPressureRepository

    repo = SportmonksPressureRepository()
    audit = repo.audit_coverage()
    after_fixtures = int((audit.get("records") or {}).get("fixture_count") or 0)
    after_records = int((audit.get("records") or {}).get("record_count") or 0)
    avg_rows = float((audit.get("summaries") or {}).get("avg_rows_per_fixture") or 0)

    by_league: dict[str, int] = {}
    by_season: dict[str, int] = {}
    wc_count = uefa_seed_count = 0
    zero_row = 0
    for row in repo.list_fixture_summaries(limit=5000):
        lid = str(row.get("league_id") or "unknown")
        by_league[lid] = by_league.get(lid, 0) + 1
        sid = str(row.get("season_id") or "unknown")
        by_season[sid] = by_season.get(sid, 0) + 1
        if lid == _WC:
            wc_count += 1
        elif lid in _UEFA:
            uefa_seed_count += 1
        if int(row.get("pressure_row_count") or 0) <= 0:
            zero_row += 1

    batch_results, api_live, api_cached, imported_batches = _load_batch_results()
    seed_path = ARTIFACT_DIR / "cache_seed_result.json"
    seed_imported = 0
    if seed_path.is_file():
        seed_imported = int(json.loads(seed_path.read_text(encoding="utf-8")).get("new_fixtures") or 0)

    cache_files = len(list(CACHE_DIR.glob("*.json"))) if CACHE_DIR.is_dir() else 0
    target_met = after_fixtures >= 150
    blocker = None
    if not target_met:
        blocker = (
            f"Coverage {after_fixtures}/150 — need more WC batches or UEFA prior-season backfill "
            f"(WC={wc_count}, UEFA={uefa_seed_count})"
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase": "54H-5",
        "fixtures_before": before_fixtures,
        "fixtures_after": after_fixtures,
        "new_fixtures": after_fixtures - before_fixtures,
        "records_before": before_records,
        "records_after": after_records,
        "new_records": after_records - before_records,
        "avg_rows_per_fixture": round(avg_rows, 2),
        "target_minimum": 150,
        "target_met": target_met,
        "recommendation": "READY_FOR_PRESSURE_BACKTEST_RERUN" if target_met else "NEED_MORE_PRESSURE_BACKFILL",
        "blocker": blocker,
        "by_league": by_league,
        "by_season": by_season,
        "wc_coverage": wc_count,
        "uefa_cache_seed_coverage": uefa_seed_count,
        "fixtures_with_zero_pressure_rows": zero_row,
        "duplicate_groups_sample": audit.get("duplicate_groups_sample") or [],
        "api_calls_live_total": api_live,
        "api_calls_cached_total": api_cached,
        "fixtures_imported_wc_batches": imported_batches,
        "fixtures_imported_cache_seed": seed_imported,
        "cache_files": cache_files,
        "manifest_stats": repo.manifest_job_stats("phase54h5"),
        "batch_results": batch_results,
    }
    (ARTIFACT_DIR / "coverage_audit.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(
        {
            "fixtures_before": before_fixtures,
            "fixtures_after": after_fixtures,
            "new_fixtures": after_fixtures - before_fixtures,
            "target_met": target_met,
            "api_calls_live": api_live,
            "recommendation": report["recommendation"],
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
