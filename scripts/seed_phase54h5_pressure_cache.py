#!/usr/bin/env python3
"""Phase 54H-5 local UEFA pressure cache seed (zero API calls)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54h5_pressure_expansion"
_CACHE_DIRS = (
    Path("data/egie/uefa_club/raw"),
    Path("data/data/egie/uefa_club/raw"),
)


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    from worldcup_predictor.feature_store.pressure_store.sportmonks_pressure_store import SportmonksPressureFeatureStore

    store = SportmonksPressureFeatureStore()
    before = store.repo.audit_coverage()
    before_count = int((before.get("records") or {}).get("fixture_count") or 0)

    existing_dirs = [str(d) for d in _CACHE_DIRS if d.is_dir()]
    if not existing_dirs:
        out = {
            "status": "skipped",
            "reason": "no_uefa_cache_dirs_on_host",
            "fixtures_before": before_count,
            "fixtures_after": before_count,
            "api_calls": 0,
        }
        (ARTIFACT_DIR / "cache_seed_result.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(json.dumps(out, indent=2))
        return 0

    result = store.backfill_from_cache_dir(
        job_key="phase54h5_cache_seed",
        force_reimport=False,
        extra_dirs=existing_dirs,
        source="cache_seed",
    )
    after = store.repo.audit_coverage()
    after_count = int((after.get("records") or {}).get("fixture_count") or 0)

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase": "54H-5",
        "status": "completed",
        "source": "cache_seed",
        "cache_dirs": existing_dirs,
        "fixtures_before": before_count,
        "fixtures_after": after_count,
        "new_fixtures": after_count - before_count,
        "api_calls": 0,
        "backfill": result.to_dict(),
    }
    (ARTIFACT_DIR / "cache_seed_result.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(
        {
            "status": out["status"],
            "new_fixtures": out["new_fixtures"],
            "fixtures_after": after_count,
            "imported": result.fixtures_imported,
            "skipped": result.fixtures_skipped,
            "empty": result.fixtures_empty,
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
