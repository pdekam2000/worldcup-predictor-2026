#!/usr/bin/env python3
"""Phase 54E — Sportmonks xG feature store quality audit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_ROOT = ROOT / "artifacts" / "phase54e_sportmonks_xg_feature_store"


def main() -> int:
    from worldcup_predictor.feature_store.sportmonks_xg_store import SportmonksXgFeatureStore

    store = SportmonksXgFeatureStore()
    audit = store.quality_audit()
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)

    records = audit.get("records") or {}
    summaries = audit.get("summaries") or {}
    fixture_count = int(records.get("fixture_count") or 0)
    summary_count = int(summaries.get("summary_count") or 0)
    with_rolling = int(summaries.get("with_rolling_xg") or 0)

    report = {
        "postgres_configured": audit.get("configured", False),
        "records_imported": int(records.get("record_count") or 0),
        "fixtures_covered": fixture_count,
        "teams_covered": int(records.get("team_count") or 0),
        "leagues_covered": int(records.get("league_count") or 0),
        "seasons_covered": int(records.get("season_count") or 0),
        "player_xg_records": int(records.get("player_record_count") or 0),
        "fixture_summaries": summary_count,
        "duplicate_groups_sample": audit.get("duplicate_groups_sample") or [],
        "coverage_pct": {
            "fixtures_with_summary": round(100 * summary_count / fixture_count, 2) if fixture_count else 0,
            "summaries_with_rolling_xg": round(100 * with_rolling / summary_count, 2) if summary_count else 0,
        },
        "aggregation_coverage_pct": round(100 * with_rolling / summary_count, 2) if summary_count else 0,
        "raw_audit": audit,
    }
    (ARTIFACT_ROOT / "quality_audit.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
