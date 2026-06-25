#!/usr/bin/env python3
"""Phase 54H-5 pre-run server state check (secret-safe)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54h5_pressure_expansion"
_FINISHED = {5, 7, 8}
_WC_LEAGUE = 732


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    from worldcup_predictor.feature_store.pressure_store.repository import SportmonksPressureRepository
    from worldcup_predictor.feature_store.pressure_store.sportmonks_pressure_store import SportmonksPressureFeatureStore

    repo = SportmonksPressureRepository()
    store = SportmonksPressureFeatureStore()
    audit = repo.audit_coverage()
    records = audit.get("records") or {}
    summaries = audit.get("summaries") or {}

    fixture_count = int(records.get("fixture_count") or 0)
    record_count = int(records.get("record_count") or 0)
    summary_count = int(summaries.get("summary_count") or 0)

    cache_dir = Path("data/feature_store/sportmonks_pressure/raw")
    uefa_cache = Path("data/egie/uefa_club/raw")
    raw_cache_count = len(list(cache_dir.glob("*.json"))) if cache_dir.is_dir() else 0
    uefa_cache_count = len(list(uefa_cache.glob("*.json"))) if uefa_cache.is_dir() else 0

    wc_finished_remaining = 0
    wc_discovered = 0
    imported = repo.imported_pressure_fixture_ids()
    try:
        season = store.resolve_season_id(_WC_LEAGUE)
        fixtures = store.discover_fixtures(league_id=_WC_LEAGUE, season_id=season, max_pages=10)
        wc_discovered = len(fixtures)
        for fx in fixtures:
            sm_id = int(fx.get("id") or 0)
            if sm_id in imported:
                continue
            if int(fx.get("state_id") or 0) in _FINISHED:
                wc_finished_remaining += 1
    except Exception:
        pass

    manifest_stats = repo.manifest_job_stats("phase54h")

    out = {
        "phase": "54H-5",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pressure_fixture_count": fixture_count,
        "pressure_record_count": record_count,
        "pressure_summary_count": summary_count,
        "wc_finished_candidates_remaining": wc_finished_remaining,
        "wc_fixtures_discovered": wc_discovered,
        "raw_cache_count": raw_cache_count,
        "uefa_cache_count": uefa_cache_count,
        "manifest_stats": manifest_stats,
        "tables_ready": bool(audit.get("tables_ready")),
    }
    (ARTIFACT_DIR / "pre_run_state.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
