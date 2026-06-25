#!/usr/bin/env python3
"""Phase 54H-6 pre-run state snapshot (secret-safe)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54h6_pressure_threshold"
TARGET_MINIMUM = 150
_CL_LEAGUE = 2
_CL_SEASON = 23619


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    from worldcup_predictor.feature_store.pressure_store.repository import SportmonksPressureRepository

    repo = SportmonksPressureRepository()
    audit = repo.audit_coverage()
    records = audit.get("records") or {}
    summaries = audit.get("summaries") or {}

    fixture_count = int(records.get("fixture_count") or 0)
    record_count = int(records.get("record_count") or 0)

    by_league: dict[str, int] = {}
    cl_season_count = 0
    for row in repo.list_fixture_summaries(limit=5000):
        lid = str(row.get("league_id") or "unknown")
        by_league[lid] = by_league.get(lid, 0) + 1
        if int(row.get("league_id") or 0) == _CL_LEAGUE and int(row.get("season_id") or 0) == _CL_SEASON:
            cl_season_count += 1

    out = {
        "phase": "54H-6",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pressure_fixture_count": fixture_count,
        "pressure_record_count": record_count,
        "pressure_summary_count": int(summaries.get("summary_count") or 0),
        "gap_to_target": max(0, TARGET_MINIMUM - fixture_count),
        "target_minimum": TARGET_MINIMUM,
        "by_league": by_league,
        "cl_2024_25_already_imported": cl_season_count,
        "target_season": {"league_id": _CL_LEAGUE, "season_id": _CL_SEASON, "label": "2024/2025"},
    }
    (ARTIFACT_DIR / "pre_run_state.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
