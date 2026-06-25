#!/usr/bin/env python3
"""Phase 54H-6 post-UEFA backfill coverage audit and threshold check."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54h6_pressure_threshold"
TARGET_MINIMUM = 150
_FALLBACK_SOURCES = (
    {"league_id": 5, "season_id": 23620, "label": "Europa League 2024/2025"},
    {"league_id": 2286, "season_id": 23616, "label": "Conference League 2024/2025"},
)


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    pre = {}
    pre_path = ARTIFACT_DIR / "pre_run_state.json"
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
    zero_row = 0
    for row in repo.list_fixture_summaries(limit=5000):
        lid = str(row.get("league_id") or "unknown")
        by_league[lid] = by_league.get(lid, 0) + 1
        sid = str(row.get("season_id") or "unknown")
        by_season[sid] = by_season.get(sid, 0) + 1
        if int(row.get("pressure_row_count") or 0) <= 0:
            zero_row += 1

    api_live = api_cached = 0
    batch_result = {}
    backfill_path = ARTIFACT_DIR / "backfill_phase54h6_cl_priorseason.json"
    if backfill_path.is_file():
        blob = json.loads(backfill_path.read_text(encoding="utf-8"))
        batch_result = blob.get("backfill") or {}
        api_live = int(batch_result.get("api_calls_live") or 0)
        api_cached = int(batch_result.get("api_calls_cached") or 0)

    target_met = after_fixtures >= TARGET_MINIMUM
    threshold_status = "PRESSURE_BACKTEST_READY" if target_met else "NEED_MORE_PRESSURE_BACKFILL"
    gap = max(0, TARGET_MINIMUM - after_fixtures)
    next_sources = [] if target_met else [{**s, "remaining_gap": gap} for s in _FALLBACK_SOURCES]

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase": "54H-6",
        "fixtures_before": before_fixtures,
        "fixtures_after": after_fixtures,
        "new_fixtures": after_fixtures - before_fixtures,
        "records_before": before_records,
        "records_after": after_records,
        "new_records": after_records - before_records,
        "avg_rows_per_fixture": round(avg_rows, 2),
        "api_calls_live": api_live,
        "api_calls_cached": api_cached,
        "target_minimum": TARGET_MINIMUM,
        "target_met": target_met,
        "threshold_status": threshold_status,
        "remaining_gap": gap,
        "by_league": by_league,
        "by_season": by_season,
        "fixtures_with_zero_pressure_rows": zero_row,
        "duplicate_groups_sample": audit.get("duplicate_groups_sample") or [],
        "batch_result": batch_result,
        "next_uefa_sources_if_below_threshold": next_sources,
        "manifest_stats": repo.manifest_job_stats("phase54h6"),
    }
    (ARTIFACT_DIR / "coverage_audit.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(
        {
            "fixtures_before": before_fixtures,
            "fixtures_after": after_fixtures,
            "new_fixtures": after_fixtures - before_fixtures,
            "target_met": target_met,
            "threshold_status": threshold_status,
            "api_calls_live": api_live,
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
